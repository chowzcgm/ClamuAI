#!/usr/bin/env python3
"""AI Music Humanizer - Shared Audio Utilities."""

import argparse
import json
import sys
import os
import io
import base64
import traceback
import numpy as np
import soundfile as sf
import librosa
from scipy import signal, fft
from pydub import AudioSegment


class NumpyEncoder(json.JSONEncoder):
    """Custom encoder to handle numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def json_dumps(obj):
    """Serialize with numpy support."""
    return json.dumps(obj, cls=NumpyEncoder)


def load_audio(filepath, target_sr=None, mono=False):
    """Load audio file, returns (audio, sr). Uses (channels, samples) shape convention."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.mp3':
        audio_seg = AudioSegment.from_mp3(filepath)
        sr = audio_seg.frame_rate
        audio = np.array(audio_seg.get_array_of_samples(), dtype=np.float32) / 32768.0
        if audio_seg.channels > 1:
            audio = audio.reshape(-1, audio_seg.channels)
            audio = audio.T  # Convert to (channels, samples)
        if mono and audio.ndim > 1:
            audio = np.mean(audio, axis=0)
    else:
        audio, sr = sf.read(filepath, dtype='float32')
        # sf returns (samples,) or (samples, channels); convert to (channels, samples)
        if audio.ndim > 1:
            audio = audio.T
            if mono:
                audio = np.mean(audio, axis=0)
        elif mono:
            pass  # Already (samples,)

    if target_sr and target_sr != sr:
        if audio.ndim > 1:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr, axis=-1)
        else:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
        sr = target_sr

    return np.ascontiguousarray(audio, dtype=np.float32), sr


def save_audio(filepath, audio, sr, format_hint=None):
    """Save audio file. Expects (channels, samples) shape, converts to (samples, channels) for sf."""
    audio = np.ascontiguousarray(np.clip(audio, -1.0, 1.0), dtype=np.float32)
    ext = (format_hint or os.path.splitext(filepath)[1]).lower()

    if ext == '.mp3':
        # pydub expects (samples, channels) interleaved
        if audio.ndim > 1:
            audio_for_mp3 = audio.T  # (channels, samples) -> (samples, channels)
            audio_int16 = (audio_for_mp3 * 32767).astype(np.int16)
            seg = AudioSegment(
                audio_int16.flatten().tobytes(),
                frame_rate=sr, sample_width=2,
                channels=min(audio.shape[0], 2)
            )
        else:
            audio_int16 = (audio * 32767).astype(np.int16)
            seg = AudioSegment(audio_int16.tobytes(), frame_rate=sr, sample_width=2, channels=1)
        seg.export(filepath, format='mp3', bitrate='320k')
    else:
        # sf expects (samples, channels)
        audio_for_sf = audio.T if audio.ndim > 1 else audio
        sf.write(filepath, audio_for_sf, sr, subtype='PCM_24')


def get_spectrogram(audio, sr, n_fft=2048, hop_length=512):
    """Compute mel spectrogram."""
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0 if audio.shape[0] > 2 else 0)
    mel = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=128, fmax=sr // 2
    )
    return librosa.power_to_db(mel, ref=np.max)


def measure_lufs(audio, sr):
    """Estimate integrated LUFS (simplified ITU-R BS.1770)."""
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0)
    # K-weighting filter (simplified)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-10:
        return -70.0
    lufs = 20 * np.log10(rms) - 0.691  # approximate calibration
    return float(lufs)


def normalize_loudness(audio, sr, target_lufs=-14.0):
    """Normalize audio to target LUFS."""
    current = measure_lufs(audio, sr)
    gain_db = target_lufs - current
    gain_linear = 10 ** (gain_db / 20.0)
    return audio * gain_linear


def apply_eq_band(audio, sr, freq, gain_db, q=1.0, band_type='peaking'):
    """Apply a parametric EQ band using biquad filter."""
    nyquist = sr / 2
    freq_norm = freq / nyquist
    freq_norm = np.clip(freq_norm, 0.001, 0.999)

    # Shelf filters are unstable at very high/low normalized frequencies
    # Clamp f0 safely and fall back to peaking if out of stable range
    # Biquad filters become unstable above ~0.4 normalized frequency
    # due to bilinear transform warping. Clamp to safe range.
    safe_norm = np.clip(freq_norm, 0.001, 0.4)

    if band_type == 'low_shelf':
        b, a = _low_shelf(safe_norm, gain_db, q)
    elif band_type == 'high_shelf':
        b, a = _high_shelf(safe_norm, gain_db, q)
    else:  # peaking
        b, a = _peaking_eq(safe_norm, gain_db, q)

    if audio.ndim > 1:
        return np.array([signal.lfilter(b, a, ch) for ch in audio])
    return signal.lfilter(b, a, audio)


def _peaking_eq(f0, gain_db, q):
    """Peaking EQ biquad coefficients."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0
    alpha = np.sin(w0) / (2 * q)
    b0 = 1 + alpha * A
    b1 = -2 * np.cos(w0)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha / A
    return np.array([b0, b1, b2]) / a0, np.array([a0, a1, a2]) / a0


def _low_shelf(f0, gain_db, q):
    """Low shelf filter coefficients (RBJ cookbook)."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0
    cos_w0 = np.cos(w0)
    # Shelf slope parameter from Q: S = 1/Q, clamped to avoid instability
    S = np.clip(1.0 / max(q, 0.3), 0.1, 3.0)
    alpha = np.sin(w0) / 2 * np.sqrt((A + 1/A) * (1/S - 1) + 2)
    b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
    b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
    a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
    a2 = (A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
    return np.array([b0, b1, b2]) / a0, np.array([a0, a1, a2]) / a0


def _high_shelf(f0, gain_db, q):
    """High shelf filter coefficients (RBJ cookbook)."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0
    cos_w0 = np.cos(w0)
    # Shelf slope parameter from Q
    S = np.clip(1.0 / max(q, 0.3), 0.1, 3.0)
    alpha = np.sin(w0) / 2 * np.sqrt((A + 1/A) * (1/S - 1) + 2)
    b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
    b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
    a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
    a2 = (A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
    return np.array([b0, b1, b2]) / a0, np.array([a0, a1, a2]) / a0


def soft_clip(x, threshold=0.8):
    """Soft clipping (tube-like saturation)."""
    abs_x = np.abs(x)
    mask = abs_x > threshold
    result = x.copy()
    result[mask] = threshold * np.tanh(x[mask] / threshold)
    return result


def add_noise(audio, level_db=-70):
    """Add shaped noise at specified level (dB relative to signal)."""
    audio = np.asarray(np.clip(np.nan_to_num(audio, nan=0, posinf=1, neginf=-1), -1, 1), dtype=np.float64)
    rms_signal = np.sqrt(np.mean(np.square(audio, dtype=np.float64))) + 1e-10
    noise = np.random.randn(*audio.shape).astype(np.float32)
    # Shape noise with pink-like filter (1/f rolloff)
    if audio.ndim > 1:
        for i in range(audio.shape[0]):
            noise[i] = signal.lfilter([1, -0.98], [1], noise[i])
    else:
        noise = signal.lfilter([1, -0.98], [1], noise)
    noise_rms = np.sqrt(np.mean(noise ** 2))
    noise = noise * (rms_signal * (10 ** (level_db / 20.0))) / noise_rms
    return audio + noise.astype(np.float32)


def generate_spectrogram_image(audio, sr, width=800, height=400):
    """Generate a PNG spectrogram image, return base64 encoded."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        S = get_spectrogram(audio, sr)
        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ax.imshow(S, aspect='auto', origin='lower', cmap='magma',
                  extent=[0, len(audio) / sr, 0, sr / 2000])
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Frequency (kHz)')
        ax.set_title('Spectrogram')
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception:
        return None


def _compute_psd(audio, sr):
    """Compute PSD via Welch's method, return (freqs, psd). Mono only."""
    y = audio if audio.ndim == 1 else np.mean(audio, axis=0)
    nperseg = min(4096, len(y) // 4)
    if nperseg < 256:
        nperseg = len(y) // 2
    return signal.welch(y, fs=sr, nperseg=nperseg, scaling='density')


def _spectral_flatness_db(psd):
    """Wiener entropy: geometric mean / arithmetic mean. 0dB = perfectly flat.
    Higher (less negative) = flatter = more AI-like."""
    gm = np.exp(np.mean(np.log(psd + 1e-12)))
    am = np.mean(psd)
    if am < 1e-12:
        return 0.0
    return float(10.0 * np.log10(gm / am))


def _spectral_slope(freqs, psd, band=(200, 8000)):
    """Log-log linear regression slope in given freq band.
    Natural audio ~ -1 (1/f decay). AI audio tends flatter (~0)."""
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if np.sum(mask) < 4:
        return 0.0
    log_f = np.log10(freqs[mask])
    log_p = np.log10(psd[mask] + 1e-12)
    slope, _ = np.polyfit(log_f, log_p, 1)
    return float(slope)


def _ai_residue_score(flatness_db, slope):
    """Heuristic 0-100 score: higher = more AI-like.
    Flatness near 0dB + slope near 0 = AI signature."""
    flat_score = min(100, max(0, (flatness_db + 15) * 3.33))  # -15dB→0, 0dB→50, 15dB→100
    slope_score = min(100, max(0, (slope + 1.2) * 50.0))       # -1.2→0, -0.8→20, 0→60
    return round(flat_score * 0.5 + slope_score * 0.5, 1)


def analyze_audio(filepath):
    """Return comprehensive audio analysis dict with AI detection metrics."""
    audio, sr = load_audio(filepath)
    dur = len(audio) / sr if audio.ndim == 1 else audio.shape[1] / sr
    lufs = measure_lufs(audio, sr)
    spec = get_spectrogram(audio, sr)

    # Welch PSD for advanced spectral metrics
    freqs, psd = _compute_psd(audio, sr)
    flatness_db = _spectral_flatness_db(psd)
    slope_200_8000 = _spectral_slope(freqs, psd, band=(200, 8000))
    slope_8000_20000 = _spectral_slope(freqs, psd, band=(8000, 20000))
    ai_score = _ai_residue_score(flatness_db, slope_200_8000)

    # Band energy distribution for watermark region analysis
    total_power = np.sum(psd)
    band_power = {}
    for label, (fl, fh) in [('sub', (20, 80)), ('bass', (80, 300)),
                              ('mid', (300, 3000)), ('presence', (3000, 8000)),
                              ('high', (8000, 16000)), ('ultrasonic', (16000, 22000))]:
        mask = (freqs >= fl) & (freqs < fh)
        band_power[f'{label}_pct'] = round(
            float(np.sum(psd[mask]) / total_power * 100) if total_power > 0 else 0, 1)

    return {
        'duration': round(dur, 2),
        'sample_rate': sr,
        'channels': 1 if audio.ndim == 1 else audio.shape[0],
        'lufs': round(lufs, 1),
        'peak_db': round(20 * np.log10(np.max(np.abs(audio)) + 1e-10), 1),
        'spectral_centroid_mean': float(np.mean(librosa.feature.spectral_centroid(
            y=audio if audio.ndim == 1 else np.mean(audio, axis=0), sr=sr)[0])),
        'spectral_bandwidth_mean': float(np.mean(librosa.feature.spectral_bandwidth(
            y=audio if audio.ndim == 1 else np.mean(audio, axis=0), sr=sr)[0])),
        'rms_mean': float(np.sqrt(np.mean(audio ** 2))),
        'zero_crossing_rate': float(np.mean(librosa.feature.zero_crossing_rate(
            audio if audio.ndim == 1 else np.mean(audio, axis=0)))),
        # New spectral metrics (Welch-based)
        'spectral_flatness_db': round(flatness_db, 2),
        'spectral_slope_200_8000': round(slope_200_8000, 3),
        'spectral_slope_8000_20000': round(slope_8000_20000, 3),
        'ai_residue_score': ai_score,
        **band_power,
    }


def apply_comb_filter(audio, sr, base_freq, depth=0.5):
    """Apply comb filter at a given base frequency (for breaking deconvolution artifacts)."""
    delay_samples = int(sr / base_freq)
    if delay_samples < 1:
        return audio
    result = audio.copy()
    if audio.ndim > 1:
        for ch in range(audio.shape[0]):
            delayed = np.roll(audio[ch], delay_samples)
            delayed[:delay_samples] = 0
            result[ch] = audio[ch] - depth * delayed
    else:
        delayed = np.roll(audio, delay_samples)
        delayed[:delay_samples] = 0
        result = audio - depth * delayed
    return result


def allpass_phase_scramble(audio, sr, num_stages=3):
    """Apply allpass filter chain to randomize phase without changing magnitude."""
    result = audio.copy()
    for _ in range(num_stages):
        q = 0.3 + np.random.random() * 0.6
        freq = 200 + np.random.random() * (sr // 2 - 400)
        w0 = 2 * np.pi * freq / sr
        alpha = np.sin(w0) / (2 * q)
        b = np.array([1 - alpha, -2 * np.cos(w0), 1 + alpha])
        a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
        b = b / a[0]
        a = a / a[0]

        if audio.ndim > 1:
            result = np.array([signal.lfilter(b, a, ch) for ch in result])
        else:
            result = signal.lfilter(b, a, result)
    return result


def sanitize_audio(audio):
    """Ensure audio is a clean float32 numpy array without NaN/Inf values."""
    audio = np.asarray(audio, dtype=np.float64)
    audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
    audio = np.clip(audio, -1.0, 1.0)
    return np.ascontiguousarray(audio, dtype=np.float32)


def process_channel(func, audio, *args, **kwargs):
    """Apply function to each channel independently for multi-channel audio."""
    if audio.ndim <= 1:
        return func(audio, *args, **kwargs)
    return np.array([func(ch, *args, **kwargs) for ch in audio])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Audio Utilities')
    parser.add_argument('--action', required=True)
    parser.add_argument('--input')
    parser.add_argument('--output')
    parser.add_argument('--job_id')
    parser.add_argument('--intensity', type=float, default=0.6)

    args = parser.parse_args()

    try:
        if args.action == 'analyze':
            result = analyze_audio(args.input)
            print(json_dumps(result))
        elif args.action == 'spectrogram_json':
            audio, sr = load_audio(args.input)
            img_b64 = generate_spectrogram_image(audio, sr)
            print(json_dumps({'spectrogram_image': img_b64}))
        elif args.action == 'normalize':
            audio, sr = load_audio(args.input)
            # Prevent clipping: apply peak normalization to -0.5dB
            peak = np.max(np.abs(audio))
            if peak > 0.94:  # Only normalize if near or above clipping
                audio = audio / peak * 0.94
            audio = np.clip(audio, -1.0, 1.0)
            save_audio(args.output or args.input, audio, sr)
            print(json_dumps({'status': 'ok', 'peak_before': float(peak), 'peak_after': 0.94}))
        elif args.action == 'info':
            info = analyze_audio(args.input)
            print(json_dumps(info))
        else:
            print(json_dumps({'error': f'Unknown action: {args.action}'}))
            sys.exit(1)
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)
