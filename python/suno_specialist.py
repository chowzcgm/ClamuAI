#!/usr/bin/env python3
"""
Suno声乐人性化专家 - Suno Vocal Humanization. Ultra-gentle, gain-neutral processing.
Applies minimal spectral shaping to break AI vocal detection signatures.
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import (sanitize_audio, json_dumps, load_audio, save_audio,
                         soft_clip, apply_eq_band)


def gain_match(original, processed):
    """Match RMS level of processed to original."""
    orig_rms = np.sqrt(np.mean(np.square(original, dtype=np.float64))) + 1e-10
    proc_rms = np.sqrt(np.mean(np.square(processed, dtype=np.float64))) + 1e-10
    return processed * (orig_rms / proc_rms)


def gentle_sibilance_smooth(audio, sr, intensity=0.3):
    """
    Very gentle de-essing targeting 6-8kHz.
    Uses a simple spectral tilt rather than dynamic compression.
    """
    if intensity < 0.1:
        return audio
    # Just apply a subtle static cut at 7kHz with wide Q - no dynamics, no artifacts
    return apply_eq_band(audio, sr, 7000, -intensity * 1.5, 1.5, 'peaking')


def subtle_breath_noise(audio, sr, intensity=0.3):
    """
    Add extremely subtle filtered noise in quiet sections.
    Noise level: -60dB below signal = essentially inaudible.
    """
    if intensity < 0.15:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio_mono = audio
    else:
        audio_mono = np.mean(audio, axis=0)

    # Find quiet sections
    envelope = np.abs(audio_mono)
    envelope = signal.lfilter([0.005], [1, -0.995], envelope)
    quiet = envelope < np.mean(envelope) * 0.1

    # Generate gentle filtered noise (2-5kHz, breath-like)
    nyquist = sr / 2
    noise = np.random.randn(len(audio_mono)).astype(np.float32)
    b, a = signal.butter(2, [1500 / nyquist, 5000 / nyquist], btype='band')
    shaped_noise = signal.lfilter(b, a, noise)

    # Level at -60dB below signal
    signal_rms = np.sqrt(np.mean(np.square(audio_mono, dtype=np.float64))) + 1e-10
    noise_rms = np.sqrt(np.mean(shaped_noise ** 2)) + 1e-10
    target_noise = signal_rms * 0.001 * intensity  # -60dB at i=1.0
    shaped_noise = shaped_noise * (target_noise / noise_rms)

    # Apply only in quiet sections
    result = audio.copy() if audio.ndim > 1 else audio.copy()
    if audio.ndim > 1:
        for ch in range(audio.shape[0]):
            result[ch] = result[ch] + shaped_noise * quiet
    else:
        result = result + shaped_noise * quiet

    return result


def gentle_presence_eq(audio, sr, intensity=0.3):
    """
    Subtle presence EQ to add vocal clarity and analog warmth.
    Static EQ only - no dynamics, no artifacts.
    """
    if intensity < 0.1:
        return audio

    # Gentle high-pass at 80Hz (clean up rumble)
    audio = apply_eq_band(audio, sr, 80, -2.0 * intensity, 0.7, 'low_shelf')
    # Slight presence boost (warmth)
    audio = apply_eq_band(audio, sr, 3000, 1.5 * intensity, 1.0, 'peaking')
    return audio


def suno_vocal_humanize(audio, sr, intensity=0.6):
    """
    Ultra-gentle Suno vocal processing.
    Every effect is barely perceptible. The goal is to subtly alter
    the spectral fingerprint without changing the audible sound.
    """
    audio = sanitize_audio(audio)
    original = audio.copy()
    i = np.clip(intensity, 0, 1)

    # 1. Gentle sibilance smoothing (static EQ cut at 7kHz)
    audio = gentle_sibilance_smooth(audio, sr, i * 0.4)

    # 2. Ultra-subtle breath noise in quiet sections (-60dB)
    audio = subtle_breath_noise(audio, sr, i * 0.3)

    # 3. Gentle presence EQ
    audio = gentle_presence_eq(audio, sr, i * 0.3)

    # Gain match to original level (prevents clipping)
    audio = gain_match(original, audio)

    return sanitize_audio(audio)


def main():
    parser = argparse.ArgumentParser(description='Suno Vocal Humanization')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = suno_vocal_humanize(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'suno_specialist'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
