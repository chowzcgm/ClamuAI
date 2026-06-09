#!/usr/bin/env python3
"""
AI神经指纹去除技术 - AI Neural Fingerprint Removal (Suno-optimized).
Targets 7 specific Suno watermark frequency bands with gentle notch filters.
Also applies subtle phase variation and analog saturation.
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import (sanitize_audio, json_dumps, load_audio, save_audio, soft_clip)


# Suno watermark frequency bands (from reverse engineering research)
SUNO_WATERMARK_BANDS = [
    (50, 150, 'Low-freq steganography'),
    (8000, 8200, 'Mid-range marker'),
    (12000, 12100, 'Secondary marker'),
    (15000, 16000, 'Mid-high watermark'),
    (17500, 18500, 'Extended range'),
    (19000, 20000, 'Ultrasonic watermark'),
    (22000, 23000, 'Extended ultrasonic'),
]


def gentle_notch_filter(audio, sr, low_freq, high_freq, depth=0.3):
    """Apply a gentle notch/band-reject filter to break watermark patterns."""
    nyquist = sr / 2
    low_norm = np.clip(low_freq / nyquist, 0.001, 0.45)
    high_norm = np.clip(high_freq / nyquist, 0.002, 0.49)

    if low_norm < 0.001 or high_norm >= 0.5:
        return audio

    try:
        b, a = signal.butter(2, [low_norm, high_norm], btype='bandstop')
    except Exception:
        return audio

    # Mix: blend original with filtered version
    if audio.ndim > 1:
        result = np.zeros_like(audio)
        for ch in range(audio.shape[0]):
            filtered = signal.lfilter(b, a, audio[ch]).astype(np.float32)
            result[ch] = (1 - depth) * audio[ch] + depth * filtered
        return result
    else:
        filtered = signal.lfilter(b, a, audio).astype(np.float32)
        return (1 - depth) * audio + depth * filtered


def subtle_phase_variation(audio, sr, intensity=0.3):
    """Single gentle allpass filter for subtle phase variation."""
    if intensity < 0.03:
        return audio

    freq = 800 + np.random.uniform(-200, 200)
    w0 = 2 * np.pi * freq / sr
    q = 0.5 + np.random.random() * 0.3
    alpha = np.sin(w0) / (2 * q)

    b = np.array([1 - alpha, -2 * np.cos(w0), 1 + alpha])
    a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
    b = b / a[0]
    a = a / a[0]

    mix = intensity * 0.1  # very subtle

    if audio.ndim > 1:
        result = np.zeros_like(audio)
        for ch in range(audio.shape[0]):
            wet = signal.lfilter(b, a, audio[ch])
            result[ch] = (1 - mix) * audio[ch] + mix * wet
        return result
    else:
        wet = signal.lfilter(b, a, audio)
        return (1 - mix) * audio + mix * wet


def add_analog_warmth(audio, intensity=0.3):
    """Very subtle analog-style saturation to break clean harmonic series."""
    if intensity < 0.1:
        return audio

    drive = intensity * 0.06
    audio = audio + drive * np.tanh(audio * 1.5)
    return soft_clip(audio, 0.96)


def fill_high_frequencies(audio, sr, intensity=0.3):
    """Fill the 18-22kHz range that AI tracks often have rolled off."""
    if intensity < 0.2 or sr < 44100:
        return audio

    nyquist = sr / 2
    b, a = signal.butter(2, 18000 / nyquist, btype='high')
    hf_noise = np.random.randn(*audio.shape).astype(np.float32) * intensity * 0.00003

    if audio.ndim > 1:
        for ch in range(audio.shape[0]):
            hf_ch = signal.lfilter(b, a, hf_noise[ch] if hf_noise.ndim > 1 else hf_noise)
            audio[ch] = audio[ch] + hf_ch
    else:
        audio = audio + signal.lfilter(b, a, hf_noise)

    return audio


def neural_fingerprint_removal(audio, sr, intensity=0.6):
    """
    Remove Suno AI neural fingerprint using targeted watermark band processing.
    All effects are deliberately subtle to preserve audio quality.
    """
    audio = sanitize_audio(audio)
    i = np.clip(intensity, 0, 1)
    nyquist = sr / 2

    # 1. Process each Suno watermark band with gentle notch filtering
    active_bands = 0
    for low_freq, high_freq, label in SUNO_WATERMARK_BANDS:
        # Skip bands above Nyquist
        if low_freq >= nyquist:
            continue
        # Clamp to available frequency range
        effective_high = min(high_freq, nyquist * 0.95)
        if effective_high <= low_freq:
            continue

        # Depth scales with intensity: 0.08 to 0.35
        notch_depth = i * 0.3 * (0.7 + 0.3 * np.random.random())
        audio = gentle_notch_filter(audio, sr, low_freq, effective_high, notch_depth)
        active_bands += 1

    # 2. Gentle phase variation (breaks phase coherence signatures)
    if i > 0.15:
        audio = subtle_phase_variation(audio, sr, i * 0.5)

    # 3. Analog warmth (saturation to break clean harmonic series)
    if i > 0.2:
        audio = add_analog_warmth(audio, i * 0.6)

    # 4. High-frequency fill (mask AI roll-off signature)
    if i > 0.25:
        audio = fill_high_frequencies(audio, sr, i * 0.5)

    return sanitize_audio(audio)


def main():
    parser = argparse.ArgumentParser(description='AI Neural Fingerprint Removal (Suno-optimized)')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = neural_fingerprint_removal(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'neural_fingerprint'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
