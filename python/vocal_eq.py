#!/usr/bin/env python3
"""
人声EQ - Vocal EQ Enhancement.
- Dynamic EQ focused on vocal range (300Hz-3kHz)
- De-essing (5-8kHz)
- Presence boost (2-4kHz)
- Warmth (150-300Hz)
- Air band (10kHz+)
- Breath noise enhancement
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, apply_eq_band, soft_clip


def vocal_eq(audio, sr, intensity=0.6):
    """Apply vocal-focused EQ chain."""
    # Vocal EQ curve designed to add natural vocal characteristics
    eq_settings = [
        # Low cut to clean up rumble (below 80Hz)
        (80, -2 - intensity * 4, 0.7, 'high_pass' if False else 'low_shelf'),
        # Warmth boost (150-300Hz)
        (200, 1 + intensity * 2, 0.6, 'peaking'),
        # Body (400-800Hz)
        (600, intensity * 1.5, 0.8, 'peaking'),
        # Presence (2-4kHz) - critical for vocal clarity
        (3000, 1 + intensity * 2.5, 1.0, 'peaking'),
        # Reduce harshness (4-6kHz)
        (5000, -intensity * 1.5, 1.2, 'peaking'),
        # Air band (10-15kHz) - adds sparkle
        (12000, 0.5 + intensity * 2, 0.5, 'high_shelf'),
    ]

    for freq, gain, q, btype in eq_settings:
        audio = apply_eq_band(audio, sr, freq, gain, q, btype)

    # De-essing via multiband compression on 5-8kHz
    if intensity > 0.2:
        nyquist = sr / 2
        b, a = signal.butter(3, [5000 / nyquist, 8000 / nyquist], btype='band')

        if audio.ndim > 1:
            for ch in range(audio.shape[0]):
                sib = signal.lfilter(b, a, audio[ch])
                threshold = 0.04 - intensity * 0.02
                mask = np.abs(sib) > threshold
                gain = np.ones_like(sib)
                gain[mask] = threshold / (np.abs(sib[mask]) + 1e-10)
                gain = signal.lfilter([0.05], [1, -0.95], gain)
                audio[ch] = audio[ch] * (0.7 + 0.3 * gain)
        else:
            sib = signal.lfilter(b, a, audio)
            threshold = 0.04 - intensity * 0.02
            mask = np.abs(sib) > threshold
            gain = np.ones_like(sib)
            gain[mask] = threshold / (np.abs(sib[mask]) + 1e-10)
            gain = signal.lfilter([0.05], [1, -0.95], gain)
            audio = audio * (0.7 + 0.3 * gain)

    # Breath enhancement: add subtle modulated noise in vocal gaps
    if intensity > 0.3:
        if audio.ndim > 1:
            audio_mono = np.mean(audio, axis=0)
        else:
            audio_mono = audio

        envelope = np.abs(audio_mono)
        envelope = signal.lfilter([0.01], [1, -0.99], envelope)
        noise_gate = 0.015
        quiet_parts = envelope < noise_gate

        breath = np.random.randn(len(audio_mono)).astype(np.float32) * 0.002 * intensity
        b_breath, a_breath = signal.butter(2, [2000 / (sr / 2), 8000 / (sr / 2)], btype='band')
        breath = signal.lfilter(b_breath, a_breath, breath)

        if audio.ndim > 1:
            for ch in range(audio.shape[0]):
                audio[ch] = audio[ch] + breath * quiet_parts
        else:
            audio = audio + breath * quiet_parts

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Vocal EQ Enhancement')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = vocal_eq(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'vocal_eq'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
