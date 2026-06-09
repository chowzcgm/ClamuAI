#!/usr/bin/env python3
"""
智能混音处理器 - Smart Mixing Processor.
Professional mixing tools:
- Multi-band compression with auto-gain
- De-essing (5-8kHz)
- Parametric EQ
- Algorithmic reverb
- Tube saturation emulation
"""

import argparse
import sys
import os
import traceback
import json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, soft_clip, apply_eq_band


def de_esser(audio, sr, intensity=0.6):
    """De-essing: compress the 5-8kHz sibilance range."""
    nyquist = sr / 2
    b, a = signal.butter(2, [5000 / nyquist, 8000 / nyquist], btype='band')
    sibilance = signal.lfilter(b, a, audio if audio.ndim == 1 else audio[0])

    threshold = 0.05 - intensity * 0.03
    ratio = 3 + intensity * 5
    reduction = np.ones_like(audio if audio.ndim == 1 else audio[0])

    abs_sib = np.abs(sibilance)
    over = abs_sib > threshold
    gain = np.ones_like(abs_sib)
    gain[over] = threshold + (abs_sib[over] - threshold) / ratio
    gain = gain / (abs_sib + 1e-10)
    gain = signal.lfilter([0.1], [1, -0.9], gain)

    if audio.ndim > 1:
        for ch in range(audio.shape[0]):
            audio[ch] = audio[ch] * gain
    else:
        audio = audio * gain

    return audio


def spectral_dynamic_eq(audio, sr, intensity=0.6):
    """Dynamic EQ for breaking AI spectral uniformity."""
    # Subtle cuts at AI-typical clean frequencies
    eq_bands = [
        (200, intensity * 1.5, 0.7, 'peaking'),
        (500, -intensity * 1.0, 0.8, 'peaking'),
        (1000, intensity * 0.5, 0.6, 'peaking'),
        (2000, -intensity * 0.8, 1.0, 'peaking'),
        (4000, intensity * 1.0, 0.5, 'peaking'),
        (8000, -intensity * 0.5, 1.2, 'high_shelf'),
        (150, intensity * 0.8, 0.7, 'low_shelf'),
    ]

    for freq, gain, q, btype in eq_bands:
        audio = apply_eq_band(audio, sr, freq, gain, q, btype)

    return audio


def algorithmic_reverb(audio, sr, intensity=0.6):
    """Simple algorithmic reverb using comb/allpass (Schroeder-style)."""
    if intensity < 0.05:
        return audio

    mix = intensity * 0.08  # Very subtle reverb
    decay = 0.3 + intensity * 0.4

    # Comb filters for early reflections
    comb_delays = [29, 37, 43, 51]  # Prime delays in ms
    allpass_delays = [5, 9]

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    reverb = np.zeros_like(audio)

    for ch in range(audio.shape[0]):
        ch_audio = audio[ch]
        wet = np.zeros_like(ch_audio)

        # Comb filters
        for delay_ms in comb_delays:
            delay_samples = int(delay_ms * sr / 1000)
            comb_sig = ch_audio.copy()
            delayed = np.zeros_like(comb_sig)
            delayed[delay_samples:] = comb_sig[:-delay_samples]
            wet += delayed * (decay ** (delay_ms / 30)) / len(comb_delays)

        # Allpass diffusers
        for _ in range(2):
            for delay_ms in allpass_delays:
                delay_samples = int(delay_ms * sr / 1000)
                rolled = np.roll(wet, delay_samples)
                rolled[:delay_samples] = 0
                wet = 0.7 * wet + 0.3 * rolled

        reverb[ch] = ch_audio + mix * wet

    if was_mono:
        return reverb[0]
    return reverb


def tube_saturation(audio, intensity=0.6):
    """Emulate tube/valve saturation (soft asymmetric clipping)."""
    if intensity < 0.05:
        return audio

    drive = 0.5 + intensity * 2.0
    audio = audio * drive
    # Asymmetric soft clipping (tube characteristic)
    audio = np.where(audio > 0,
                      np.tanh(audio) * 0.8 + audio * 0.2,
                      np.tanh(audio * 1.3) * 0.7 + audio * 0.3)
    return audio / drive  # compensate gain


def smart_mixer(audio, sr, intensity=0.6):
    """Complete smart mixing chain."""
    # 1. Subtle tube saturation for analog warmth
    if intensity > 0.1:
        audio = tube_saturation(audio, intensity * 0.6)

    # 2. Dynamic EQ - break spectral uniformity
    audio = spectral_dynamic_eq(audio, sr, intensity * 0.7)

    # 3. De-essing
    if intensity > 0.3:
        audio = de_esser(audio, sr, intensity)

    # 4. Subtle reverb for room presence
    if intensity > 0.1:
        audio = algorithmic_reverb(audio, sr, intensity * 0.5)

    # 5. Soft clip to smooth peaks
    audio = soft_clip(audio, 0.94)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Smart Mixing Processor')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = smart_mixer(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'smart_mixer'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
