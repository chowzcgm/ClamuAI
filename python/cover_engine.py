#!/usr/bin/env python3
"""
翻唱音频处理引擎 - Cover Audio Processing Engine.
- Voice formant shifting for vocal character change
- Pitch correction smoothing (removes perfect auto-tune)
- Vocal doubling simulation for thickness
- Voice cloning fingerprint masking
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal
import librosa

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, soft_clip, apply_eq_band


def formant_shifter(audio, sr, intensity=0.6):
    """Subtle formant shifting to alter vocal character without changing pitch."""
    if intensity < 0.05:
        return audio

    # Apply subtle spectral envelope shift via EQ that mimics formant changes
    formant_bands = [
        (300, intensity * 2.0, 0.8),   # F1 region
        (800, -intensity * 1.5, 1.0),   # F2 region
        (2200, intensity * 1.0, 1.2),   # F3 region
        (3500, -intensity * 0.8, 0.7),   # F4 region
    ]

    for freq, gain, q in formant_bands:
        audio = apply_eq_band(audio, sr, freq, gain, q, 'peaking')

    return audio


def pitch_smoothing(audio, sr, intensity=0.6):
    """
    Apply subtle pitch variation to break perfect pitch correction signatures.
    AI vocals often have mathematically perfect pitch - we add micro-variation.
    """
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    for ch in range(audio.shape[0]):
        ch_audio = audio[ch]

        # Segment-based micro pitch shifting
        segment_len = int(sr * 0.5)  # 500ms segments
        hop = segment_len // 2

        t = np.arange(len(ch_audio)) / sr
        lfo = intensity * 4 * np.sin(2 * np.pi * 0.3 * t) * np.sin(2 * np.pi * 0.08 * t)

        for start in range(0, len(ch_audio) - segment_len, hop):
            end = start + segment_len
            seg = ch_audio[start:end]
            avg_cents = float(np.mean(lfo[start:end]))
            if abs(avg_cents) > 0.3:
                try:
                    seg_shifted = librosa.effects.pitch_shift(
                        seg, sr=sr, n_steps=avg_cents / 100, bins_per_octave=24
                    )
                    ch_audio[start:end] = seg_shifted
                except Exception:
                    pass

        audio[ch] = ch_audio

    if was_mono:
        return audio[0]
    return audio


def vocal_doubler(audio, sr, intensity=0.6):
    """Simulate vocal doubling with micro-delay and detune."""
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    if audio.shape[0] == 1:
        # Create stereo by doubling
        original = audio[0]
        delay_ms = 8 + intensity * 22  # 8-30ms delay
        delay_samples = int(delay_ms * sr / 1000)

        doubled = np.roll(original, delay_samples)
        doubled[:delay_samples] = doubled[delay_samples:delay_samples * 2]

        # Micro-detune the double
        try:
            doubled = librosa.effects.pitch_shift(
                doubled, sr=sr, n_steps=intensity * 0.12, bins_per_octave=24
            )
        except Exception:
            pass

        mix = intensity * 0.4
        audio = np.array([
            original + mix * doubled * 0.5,
            doubled + mix * original * 0.5
        ])
    else:
        # Already stereo - cross-micro-delay
        delay_ms = int(5 + intensity * 15)
        delay_samples = int(delay_ms * sr / 1000)
        audio[1] = np.roll(audio[1], delay_samples)
        audio[1][:delay_samples] = audio[1][delay_samples:delay_samples * 2]

    return audio


def vocal_enhancement(audio, sr, intensity=0.6):
    """Enhance vocal presence and clarity."""
    # Vocal presence EQ
    audio = apply_eq_band(audio, sr, 250, intensity * 1.5, 0.6, 'low_shelf')
    audio = apply_eq_band(audio, sr, 3000, intensity * 2.0, 0.8, 'peaking')
    audio = apply_eq_band(audio, sr, 8000, intensity * 1.0, 1.2, 'high_shelf')

    # Subtle harmonic excitation for vocal richness
    if intensity > 0.2:
        excited = audio + intensity * 0.1 * np.tanh(audio * 3)
        audio = (1 - intensity * 0.05) * audio + intensity * 0.05 * excited

    return audio


def cover_engine(audio, sr, intensity=0.6):
    """Complete cover audio processing chain."""

    # 1. Pitch variation to break perfect tuning
    audio = pitch_smoothing(audio, sr, intensity * 0.6)

    # 2. Formant character shift
    audio = formant_shifter(audio, sr, intensity * 0.7)

    # 3. Vocal doubling
    audio = vocal_doubler(audio, sr, intensity * 0.5)

    # 4. Vocal enhancement EQ
    audio = vocal_enhancement(audio, sr, intensity * 0.8)

    # 5. Soft clip
    audio = soft_clip(audio, 0.95)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Cover Audio Processing Engine')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = cover_engine(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'cover_engine'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
