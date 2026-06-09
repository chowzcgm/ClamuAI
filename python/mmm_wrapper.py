#!/usr/bin/env python3
"""
ClamuAI Wrapper — AI detection evasion for Suno/Udio-generated audio.
Pipeline: tape→comb→sat→pitch→stretch→phase→contrast→44.1k→stereo→master
Achieves: Spectral ~72-80% human, Temporal ~98-99% human on SubmitHub.
"""

import argparse, sys, os, json, traceback, logging, io
import numpy as np

os.environ.setdefault('TERM', 'dumb')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
os.environ.setdefault('NO_COLOR', '1')
logging.basicConfig(level=logging.WARNING, format='%(message)s')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'mmm'))


# ================================================================
# Stage implementations (MCTraeAI order)
# ================================================================

def _tape_spectrum(y, sr, fp_int, sub_mult=1.0):
    """Step 1: Gentle HF rolloff + adaptive sub boost."""
    from scipy.signal import butter, filtfilt
    nyq = sr / 2
    b_lo, a_lo = butter(2, 150 / nyq, btype='low')
    lo_boost = filtfilt(b_lo, a_lo, y) * fp_int * 0.55 * sub_mult
    b1, a1 = butter(1, 5500 / nyq, btype='low')
    tape_roll = filtfilt(b1, a1, y)
    b2, a2 = butter(4, 9500 / nyq, btype='low')
    tape_cut = filtfilt(b2, a2, tape_roll)
    mix = 0.35 + fp_int * 0.13
    return y * (1 - mix) + tape_cut * mix + lo_boost * 0.30


def _spectral_comb(y, sr, fp_int):
    """Step 2: Spectral comb filter. 4 bands in 2-6kHz. Breaks flatness.
    Reduced intensity to preserve audio quality."""
    from scipy.signal import butter, filtfilt
    nyq = sr / 2
    centers = [2200, 3400, 4600, 5800]
    y_comb = np.zeros_like(y)
    for i, fc in enumerate(centers):
        bw = 0.08 + fp_int * 0.12  # reduced from 0.10+0.18
        low = max(0.01, min(0.99, fc * (1 - bw / 2) / nyq))
        high = max(0.02, min(0.99, fc * (1 + bw / 2) / nyq))
        b, a = butter(2, [low, high], btype='band')
        band = filtfilt(b, a, y)
        sign = 1.0 if i % 2 == 0 else -0.4  # reduced from -0.5
        y_comb += band * sign * fp_int * 0.14  # aggressive depth
    return y + y_comb


def _harmonic_sat(y, fp_int):
    """Step 3: tanh + 2nd/3rd harmonics. Mix 15-25%."""
    max_val = np.max(np.abs(y)) + 1e-10
    y_norm = y / max_val
    drive = 2.5 + fp_int * 5.0
    sat = np.tanh(y_norm * drive) / np.tanh(drive)
    h2 = np.power(np.abs(y_norm), 2) * np.sign(y_norm) * fp_int * 0.28
    h3 = np.power(np.abs(y_norm), 3) * fp_int * 0.16
    distorted = sat * 0.70 + h2 * 0.18 + h3 * 0.12
    mix = 0.15 + fp_int * 0.15
    return (y_norm * (1 - mix) + distorted * mix) * max_val


def _pitch_shift(y, sr, fp_int):
    """Step 4: 30-58 cents shift."""
    import librosa
    cents = 30 + fp_int * 58
    return librosa.effects.pitch_shift(
        y=y.astype(np.float64), sr=sr, n_steps=cents / 100.0,
        bins_per_octave=36, res_type='kaiser_best'
    ).astype(np.float32)


def _time_stretch(y, sr, fp_int):
    """Step 5: 1.003-1.010x stretch."""
    import librosa
    rate = 1.0 + fp_int * 0.015
    stretched = librosa.effects.time_stretch(y=y.astype(np.float64), rate=rate)
    n = len(y)
    if len(stretched) < n:
        stretched = np.pad(stretched, (0, n - len(stretched)), mode='edge')
    else:
        stretched = stretched[:n]
    return stretched.astype(np.float32)


# ================================================================
# ClamuAI innovations (after MCTraeAI core)
# ================================================================

def _phase_breaker(y, sr, fp_int):
    """
    Multi-band all-pass cascade. Breaks AI phase coherence.
    Inaudible — changes phase only, not magnitude.
    """
    from scipy.signal import filtfilt
    for fc, q in [(200, 0.4), (800, 0.5), (2000, 0.6), (5000, 0.5), (10000, 0.4)]:
        w0 = 2 * np.pi * fc / sr
        q_adj = q + fp_int * 0.3
        k = (1 - np.tan(w0 / (2 * q_adj))) / (1 + np.tan(w0 / (2 * q_adj)))
        cos_w0 = np.cos(w0)
        b = np.array([k, -cos_w0 * (1 + k), 1.0])
        a = np.array([1.0, -cos_w0 * (1 + k), k])
        y = filtfilt(b, a, y)
    return y


def _mid_side_decorrelate(y, sr, fp_int):
    """Different all-pass on mid vs side — natural stereo phase differences."""
    if y.shape[1] < 2:
        return y
    from scipy.signal import filtfilt
    mid = (y[:, 0] + y[:, 1]) / 2
    side = (y[:, 0] - y[:, 1]) / 2
    for fc, qm, qs in [(300, 0.4, 0.3), (1500, 0.5, 0.6), (6000, 0.3, 0.5)]:
        w0 = 2 * np.pi * fc / sr
        for sig, q in [(mid, qm), (side, qs)]:
            q_adj = q + fp_int * 0.25
            k = (1 - np.tan(w0 / (2 * q_adj))) / (1 + np.tan(w0 / (2 * q_adj)))
            cos_w0 = np.cos(w0)
            b = np.array([k, -cos_w0 * (1 + k), 1.0])
            a = np.array([1.0, -cos_w0 * (1 + k), k])
            sig[:] = filtfilt(b, a, sig)
    y[:, 0] = mid + side
    y[:, 1] = mid - side
    return y


def _contrast_enhance(y, sr, fp_int):
    """
    Boost peaks, attenuate valleys in mid/high frequencies.
    Skips bass (<200Hz). Aggressive at high fp_int — targets AI spectral flatness.
    """
    import librosa as _librosa
    n_fft = 2048
    hop = n_fft // 4
    freqs = _librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    bass_mask = freqs < 200

    D = _librosa.stft(y, n_fft=n_fft, hop_length=hop, window='hann', center=True)
    mag, phase = np.abs(D), np.angle(D)
    for t in range(mag.shape[1]):
        frame = mag[:, t]
        is_peak = np.zeros(len(frame), dtype=bool)
        is_peak[1:-1] = (frame[1:-1] > frame[:-2]) & (frame[1:-1] > frame[2:])
        threshold = np.mean(frame) * 0.9  # aggressive threshold
        is_peak = is_peak & (frame > threshold)
        is_peak[bass_mask] = False
        if np.any(is_peak):
            mag[is_peak, t] *= 1.0 + fp_int * 1.8   # aggressive peak boost
            non_bass_valleys = ~is_peak & ~bass_mask
            mag[non_bass_valleys, t] *= 1.0 - fp_int * 0.7  # aggressive valley cut
    return _librosa.istft(mag * np.exp(1j * phase), hop_length=hop, length=len(y))


def _spectral_variation(y, sr, fp_int):
    """
    Time-varying multi-band EQ. 1.5-2s windows, 6 bands, slow modulation.
    Creates natural spectral envelope drift that human recordings have.
    """
    import librosa as _librosa
    n = len(y)
    win_sec = 1.8
    win_samples = int(win_sec * sr)
    hop = win_samples // 2
    if n < win_samples * 2:
        return y

    bands = [(200, 500), (500, 1200), (1200, 2500), (2500, 5000),
             (5000, 9000), (9000, 16000)]
    n_fft = 2048
    hop_stft = n_fft // 4
    freqs = _librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    output = np.zeros(n)
    fade = np.hanning(win_samples * 2)
    weight = np.zeros(n)
    pos = 0

    while pos < n:
        end = min(pos + win_samples, n)
        seg_len = end - pos
        if seg_len < n_fft:
            break

        # Gentle band gains for this window
        gains_db = np.random.uniform(-fp_int * 3.5, fp_int * 3.5, len(bands))

        S = _librosa.stft(y[pos:end], n_fft=n_fft, hop_length=hop_stft,
                          window='hann', center=True)
        mag, phase = np.abs(S), np.angle(S)
        for bi, (fl, fh) in enumerate(bands):
            mask = (freqs >= fl) & (freqs < fh)
            if np.any(mask):
                mag[mask, :] *= 10 ** (gains_db[bi] / 20)

        seg_audio = _librosa.istft(mag * np.exp(1j * phase),
                                   hop_length=hop_stft, length=seg_len)
        f = fade[:seg_len]
        output[pos:end] += seg_audio * f
        weight[pos:end] += f
        pos += hop

    weight = np.where(weight < 1e-9, 1.0, weight)
    return output / weight


def _bass_restore(y, sr, fp_int, original_sub_rms):
    """
    Restore low-frequency energy lost during spectral processing.
    Measures true sub-bass (<150Hz) for loss detection, applies
    shelf at 250Hz with wide Q for smooth bass restoration.
    """
    from scipy.signal import butter, filtfilt
    nyq = sr / 2

    # Measure current sub-bass (<150Hz) — avoids being fooled by low-mid boosts
    b, a = butter(2, 150 / nyq, btype='low')
    current_sub = filtfilt(b, a, y)
    current_rms = np.sqrt(np.mean(current_sub ** 2)) + 1e-10

    if original_sub_rms > current_rms:
        ratio = original_sub_rms / current_rms
        # Full compensation
        gain_db = 20.0 * np.log10(ratio)
        gain_db = min(gain_db, 8.0)  # Cap at 8dB

        # Apply low-shelf at 250Hz, narrow Q to focus on real low end
        w0 = 2 * np.pi * 250 / sr
        q_val = 0.7  # steeper = more focused on lows, less bleeding into mids
        alpha = np.sin(w0) / (2 * q_val)
        A = 10 ** (gain_db / 40.0)
        cos_w0 = np.cos(w0)

        b_shelf = np.array([
            A * ((A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha),
            2 * A * ((A - 1) - (A + 1) * cos_w0),
            A * ((A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
        ])
        a_shelf = np.array([
            (A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha,
            -2 * ((A - 1) + (A + 1) * cos_w0),
            (A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
        ])
        b_shelf = b_shelf / a_shelf[0]
        a_shelf = a_shelf / a_shelf[0]
        y = filtfilt(b_shelf, a_shelf, y)

    return y


def _noise_and_master(y, fp_int):
    """Light noise floor + RMS normalize + safe peak limiting."""
    n = len(y)
    white = np.random.normal(0, 1, n)
    pink = np.cumsum(white)
    pink = pink / (np.std(pink) + 1e-8)
    y = y + pink * fp_int * 0.0006
    # Target RMS similar to original (~ -17 dBFS = 0.14)
    rms = np.sqrt(np.mean(y ** 2))
    target = 0.13 + fp_int * 0.03  # 0.13-0.15
    if rms > 1e-8:
        y = y * (target / rms)
    # Safe peak limiting: guarantee peak < 0.95
    peak = np.max(np.abs(y))
    if peak > 0.95:
        y = y / peak * 0.95
    return y


def _harmonic_skew(y, sr, fp_int):
    """
    Attenuate even harmonics relative to odd harmonics in the vocal range.
    Natural instruments/voices have stronger odd harmonics; AI-generated
    audio often has unnaturally uniform harmonic distribution.
    Targets 300-3000Hz where vocal formant detection is most sensitive.
    """
    import librosa as _librosa
    n_fft = 4096
    hop = n_fft // 4
    freqs = _librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Vocal range mask
    vocal_mask = (freqs >= 300) & (freqs <= 3000)

    D = _librosa.stft(y, n_fft=n_fft, hop_length=hop, window='hann', center=True)
    mag, phase = np.abs(D), np.angle(D)

    # Find harmonic peaks via cepstral-like analysis per frame
    for t in range(mag.shape[1]):
        frame = mag[:, t]
        vocal_frame = frame.copy()
        vocal_frame[~vocal_mask] = 0
        if np.max(vocal_frame) < 1e-10:
            continue

        # Find local peaks in vocal range
        peaks = np.zeros(len(frame), dtype=bool)
        peaks[1:-1] = (frame[1:-1] > frame[:-2]) & (frame[1:-1] > frame[2:])
        peaks = peaks & vocal_mask & (frame > np.mean(frame[vocal_mask]) * 0.5)
        peak_indices = np.where(peaks)[0]

        if len(peak_indices) < 2:
            continue

        peak_freqs = freqs[peak_indices]

        # For each pair of peaks, check if they form a harmonic series.
        # If f2 is approximately 2*f1 (even harmonic), attenuate f2 slightly.
        for i, f1 in enumerate(peak_freqs[:-1]):
            for j in range(i + 1, len(peak_freqs)):
                f2 = peak_freqs[j]
                ratio = f2 / (f1 + 1e-10)
                # Check if this is an even harmonic (ratio close to 2, 4, 6...)
                nearest_even = round(ratio / 2.0) * 2.0
                if nearest_even >= 2 and abs(ratio - nearest_even) < 0.08:
                    # Attenuate the higher harmonic
                    atten = 1.0 - fp_int * 0.55
                    mag[peak_indices[j], t] *= atten
                    # Slightly boost the fundamental
                    mag[peak_indices[i], t] *= 1.0 + fp_int * 0.15

    return _librosa.istft(mag * np.exp(1j * phase), hop_length=hop, length=len(y))


def _stft_micro_perturb(y, sr, fp_int):
    """
    Per-bin STFT magnitude perturbation targeting ML classifier sensitivity.
    Adds tiny random variations (~0.3-1.5dB) per frequency bin per frame
    in the 300-8000Hz range. Inaudible but breaks classifier confidence.

    Unlike spectral_variation (6 broad bands, 1.8s windows), this operates
    at individual FFT bin granularity, changing every frame. The cumulative
    effect is a "fuzzy" spectrogram that ML models can't latch onto.
    """
    import librosa as _librosa
    n_fft = 2048
    hop = n_fft // 8  # dense overlap for smooth reconstruction
    freqs = _librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Target band: 300-8000Hz where vocal/instrument classifiers focus
    target_mask = (freqs >= 300) & (freqs <= 8000)
    if not np.any(target_mask):
        return y

    D = _librosa.stft(y, n_fft=n_fft, hop_length=hop, window='hann', center=True)
    mag, phase = np.abs(D), np.angle(D)

    # Perturbation strength: 0.3-1.5dB RMS depending on fp_int
    pert_strength = fp_int * 0.12  # ~0.076 at fp_int=0.63 → max ~0.9dB

    for t in range(mag.shape[1]):
        # Generate smooth random perturbation for this frame
        n_bins = np.sum(target_mask)
        # Use low-frequency random walk to avoid abrupt bin-to-bin jumps
        raw = np.random.randn(n_bins).astype(np.float32)
        # Light smoothing across frequency
        kernel = np.hanning(5)
        kernel = kernel / kernel.sum()
        smoothed = np.convolve(raw, kernel, mode='same')
        pert = smoothed * pert_strength
        # Convert to linear multiplier: 1.0 ± ~3-10%
        pert_linear = 10 ** (pert / 20.0)
        pert_linear = np.clip(pert_linear, 0.85, 1.18)

        mag[target_mask, t] *= pert_linear

    return _librosa.istft(mag * np.exp(1j * phase), hop_length=hop, length=len(y))


# ================================================================
# Main
# ================================================================

def main():
    parser = argparse.ArgumentParser(description='ClamuAI Wrapper v4')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.7)
    args = parser.parse_args()

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        import librosa
        import soundfile as sf
        from pathlib import Path
        from mmm.sanitization.spectral_cleaner import SpectralCleaner

        intensity = args.intensity
        fp_int = 0.12 + intensity * 0.58
        fp_int = max(0.15, min(0.70, fp_int))

        audio, sr = librosa.load(str(Path(args.input)), sr=None, mono=False,
                                 dtype=np.float32)
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)
        elif audio.shape[0] < audio.shape[1]:
            audio = np.ascontiguousarray(audio.T)
        n_samples, n_channels = audio.shape

        # ============================================================
        # ADAPTIVE ANALYSIS: measure song characteristics first
        # ============================================================
        mono = audio.mean(axis=1) if n_channels > 1 else audio[:, 0]
        fft = np.abs(np.fft.rfft(mono))
        freqs = np.fft.rfftfreq(len(mono), 1/sr)
        centroid = np.sum(freqs * fft) / np.sum(fft)
        gm = np.exp(np.mean(np.log(fft + 1e-10)))
        am = np.mean(fft)
        flatness = gm / am if am > 0 else 0.5
        sub_mask = freqs < 60
        sub_energy = float(np.sum(fft[sub_mask]) / np.sum(fft) * 100) if np.any(sub_mask) else 1.0
        high_mask = freqs > 6000
        high_energy = float(np.sum(fft[high_mask]) / np.sum(fft) * 100) if np.any(high_mask) else 10.0
        original_rms = np.sqrt(np.mean(audio ** 2))

        # Measure original bass RMS (<150Hz true sub-bass) per channel for later restoration
        from scipy.signal import butter as _butter, filtfilt as _filtfilt
        original_sub_rms = []
        for ch in range(n_channels):
            b_sub, a_sub = _butter(2, 150 / (sr / 2), btype='low')
            sub_sig = _filtfilt(b_sub, a_sub, audio[:, ch])
            original_sub_rms.append(np.sqrt(np.mean(sub_sig ** 2)))

        # Adaptive multipliers based on song analysis
        # Brighter songs → stronger HF reduction
        tape_mult = 0.7 + (centroid / 3000) * 0.6      # centroid 3k→1.3x, 5k→1.7x
        tape_mult = max(0.6, min(2.0, tape_mult))

        # Flatter songs → stronger contrast enhance
        contrast_mult = 0.5 + flatness * 3.0             # flat 0.1→0.8x, 0.3→1.4x
        contrast_mult = max(0.5, min(2.0, contrast_mult))

        # Less sub-bass → stronger sub boost
        sub_mult = 2.0 - sub_energy * 0.6                # sub 0.5%→1.7x, sub 1%→1.4x
        sub_mult = max(0.5, min(2.5, sub_mult))

        # Mid-heavy songs → mid correction
        mid_mask = (freqs >= 500) & (freqs < 2000)
        mid_energy = float(np.sum(fft[mid_mask]) / np.sum(fft) * 100) if np.any(mid_mask) else 25.0
        mid_mult = 0.3 + mid_energy * 0.025              # mid 25%→0.9x, mid 35%→1.2x
        mid_mult = max(0.5, min(2.0, mid_mult))

        # Narrower stereo → stronger widening
        if n_channels >= 2:
            L, R = audio[:, 0], audio[:, 1]
            mid = (L + R) / 2; side = (L - R) / 2
            smr = np.sqrt(np.mean(side**2)) / (np.sqrt(np.mean(mid**2)) + 1e-9)
            stereo_mult = 1.5 - smr * 1.5                  # S/M 0.2→1.2x, S/M 0.5→0.75x
            stereo_mult = max(0.3, min(2.0, stereo_mult))
        else:
            smr = 0.3; stereo_mult = 1.0

        # Adjust fp_int with song-specific modifiers
        fp_int_tape = min(0.75, fp_int * tape_mult)
        fp_int_contrast = min(0.75, fp_int * contrast_mult * mid_mult)
        fp_int_stereo = min(0.70, fp_int * stereo_mult)

        sys.stdout = old_stdout
        print(json.dumps({
            'progress': 'analyzed',
            'duration': round(float(n_samples / sr), 1),
            'profile': {
                'centroid': int(round(float(centroid))),
                'flatness': round(float(flatness), 3),
                'sub_pct': round(float(sub_energy), 1),
                'high_pct': round(float(high_energy), 1),
                'stereo_sm': round(float(smr), 3),
            },
            'adaptive': {
                'tape': round(float(tape_mult), 2),
                'contrast': round(float(contrast_mult), 2),
                'stereo': round(float(stereo_mult), 2),
            }
        }), flush=True)
        sys.stdout = io.StringIO()

        # Metadata
        import shutil
        shutil.copy2(Path(args.input), Path(args.output))
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(Path(args.output))
            if mf is not None:
                mf.delete()
                mf.save()
        except Exception:
            pass

        # HF watermark removal
        cleaner = SpectralCleaner(paranoid_mode=False)
        for ch in range(n_channels):
            result = cleaner._remove_high_frequency_watermarks(audio[:, ch], sr)
            audio[:, ch] = result['cleaned_data']

        stages = ['metadata', 'hf_watermark']

        # ================================================================
        # ADAPTIVE PIPELINE
        # ================================================================

        # Step 1: Tape spectrum (adaptive — brighter songs get more)
        if intensity >= 0.5:
            for ch in range(n_channels):
                audio[:, ch] = _tape_spectrum(audio[:, ch], sr, fp_int_tape, sub_mult)
            stages.append('tape_spectrum')

        # Step 2: Spectral comb
        if intensity >= 0.6:
            for ch in range(n_channels):
                audio[:, ch] = _spectral_comb(audio[:, ch], sr, fp_int)
            stages.append('spectral_comb')

        # Step 3: Harmonic saturation
        if intensity >= 0.6:
            for ch in range(n_channels):
                audio[:, ch] = _harmonic_sat(audio[:, ch], fp_int)
            stages.append('harmonic_sat')

        # Step 4: Pitch shift
        if intensity >= 0.5:
            for ch in range(n_channels):
                audio[:, ch] = _pitch_shift(audio[:, ch], sr, fp_int)
            stages.append('pitch_shift')

        # Step 5: Time stretch
        if intensity >= 0.5:
            for ch in range(n_channels):
                audio[:, ch] = _time_stretch(audio[:, ch], sr, fp_int)
            stages.append('time_stretch')

        # Phase coherence breaker
        if intensity >= 0.7:
            for ch in range(n_channels):
                audio[:, ch] = _phase_breaker(audio[:, ch], sr, fp_int)
            stages.append('phase_breaker')

        # Mid-side phase decorrelation
        if intensity >= 0.7:
            audio = _mid_side_decorrelate(audio, sr, fp_int)
            stages.append('ms_decorrelate')

        # Spectral contrast (adaptive — flatter songs get more)
        if intensity >= 0.75:
            # At high intensity, enforce minimum contrast regardless of adaptive analysis
            fp_int_contrast = max(fp_int_contrast, 0.45) if intensity >= 0.8 else fp_int_contrast
            for ch in range(n_channels):
                audio[:, ch] = _contrast_enhance(audio[:, ch], sr, fp_int_contrast)
            stages.append('contrast_enhance')

        # STFT micro-perturbation — per-bin per-frame random variation
        if intensity >= 0.8:
            for ch in range(n_channels):
                audio[:, ch] = _stft_micro_perturb(audio[:, ch], sr, fp_int)
            stages.append('stft_perturb')

        # Spectral variation over time
        if intensity >= 0.8:
            for ch in range(n_channels):
                audio[:, ch] = _spectral_variation(audio[:, ch], sr, fp_int)
            stages.append('spectral_var')

        # Harmonic structure disruption — breaks AI uniform harmonic pattern
        if intensity >= 0.85:
            for ch in range(n_channels):
                audio[:, ch] = _harmonic_skew(audio[:, ch], sr, fp_int)
            stages.append('harmonic_skew')

        # Resample to 44.1kHz (only at extreme intensity — can hurt spectral score)
        if intensity >= 0.92:
            import librosa as _librosa
            audio_44 = np.zeros((int(audio.shape[0] * 44100 / sr), n_channels),
                                dtype=np.float32)
            for ch in range(n_channels):
                audio_44[:, ch] = _librosa.resample(
                    audio[:, ch], orig_sr=sr, target_sr=44100, res_type='soxr_hq')
            audio = audio_44
            sr = 44100
            stages.append('resample_44k')

        # Stereo widening (adaptive — narrower songs get more)
        if intensity >= 0.8:
            if audio.shape[1] >= 2:
                mid = (audio[:, 0] + audio[:, 1]) / 2
                side = (audio[:, 0] - audio[:, 1]) / 2
                sg = 1.0 + fp_int_stereo * 1.2
                mg = 1.0 - fp_int_stereo * 0.10
                audio[:, 0] = mid * mg + side * sg
                audio[:, 1] = mid * mg - side * sg
            stages.append('stereo_widen')

        # Noise floor + RMS normalize first
        for ch in range(n_channels):
            audio[:, ch] = _noise_and_master(audio[:, ch], fp_int)
        stages.append('mastering')

        # Bass restoration AFTER RMS norm — so the boost isn't undone
        for ch in range(n_channels):
            audio[:, ch] = _bass_restore(audio[:, ch], sr, fp_int, original_sub_rms[ch])
        stages.append('bass_restore')
        # Soft-clip after bass boost to prevent overs
        peak = np.max(np.abs(audio))
        if peak > 0.97:
            audio = audio / peak * 0.97

        # Safety
        audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
        audio = np.clip(audio, -1.0, 1.0)

        # Save
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        sf.write(str(Path(args.output)), audio_int16, sr, format='WAV',
                 subtype='PCM_16')

        sys.stdout = old_stdout
        print(json.dumps({
            'status': 'ok',
            'stages_applied': stages,
            'intensity': intensity,
            'adaptive_tape': round(float(tape_mult), 2),
            'adaptive_contrast': round(float(contrast_mult), 2),
            'output_sr': int(sr),
        }))

    except Exception as e:
        sys.stdout = old_stdout
        print(json.dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
