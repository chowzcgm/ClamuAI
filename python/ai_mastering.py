#!/usr/bin/env python3
"""
AI母带处理器 - AI Mastering Processor.
Professional mastering chain:
- Multi-band compression (4-band)
- Stereo width enhancement (mid-side processing)
- Loudness normalization (LUFS target)
- Peak limiting with look-ahead
- Release-quality sound polishing
"""

import argparse
import sys
import os
import traceback
import json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import json_dumps, load_audio, save_audio, soft_clip, measure_lufs, normalize_loudness, sanitize_audio


def multi_band_compressor(audio, sr, intensity=0.6):
    """
    4-band multi-band compressor.
    Bands: sub (0-80Hz), low (80-300Hz), mid (300-3kHz), high (3kHz+)
    """
    nyquist = sr / 2

    # Crossover frequencies
    bands = [
        (0, 80, 'sub'),
        (80, 300, 'low'),
        (300, 3000, 'mid'),
        (3000, nyquist, 'high')
    ]

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    num_channels = audio.shape[0]
    processed = np.zeros_like(audio)

    for ch in range(num_channels):
        ch_audio = audio[ch]
        ch_processed = np.zeros_like(ch_audio)

        for low_freq, high_freq, name in bands:
            if low_freq == 0:
                b, a = signal.butter(4, high_freq / nyquist, btype='low')
            elif high_freq >= nyquist:
                b, a = signal.butter(4, low_freq / nyquist, btype='high')
            else:
                b, a = signal.butter(4, [low_freq / nyquist, high_freq / nyquist], btype='band')

            band_signal = signal.lfilter(b, a, ch_audio)

            # Gentle compression per band
            rms = np.sqrt(np.mean(band_signal ** 2)) + 1e-10
            if rms > 1e-6:
                # Compression threshold and ratio vary by band
                if name == 'sub':
                    threshold = 0.3 - intensity * 0.1
                    ratio = 1.5 + intensity * 2.5
                    makeup = 1.0 + intensity * 0.3
                elif name == 'low':
                    threshold = 0.35 - intensity * 0.1
                    ratio = 1.3 + intensity * 2.0
                    makeup = 1.0 + intensity * 0.2
                elif name == 'mid':
                    threshold = 0.4 - intensity * 0.1
                    ratio = 1.2 + intensity * 1.5
                    makeup = 1.0 + intensity * 0.1
                else:  # high
                    threshold = 0.35 - intensity * 0.1
                    ratio = 1.2 + intensity * 2.0
                    makeup = 1.0 + intensity * 0.15

                # Soft knee compression
                envelope = np.abs(band_signal)
                envelope = signal.lfilter([0.1], [1, -0.9], envelope)  # RMS smoothing

                above = envelope > threshold
                gain = np.ones_like(envelope)
                gain[above] = threshold + (envelope[above] - threshold) / ratio
                gain = gain / (envelope + 1e-10)
                gain = np.minimum(gain, 2.0)

                # Smooth gain changes
                gain = signal.lfilter([0.05], [1, -0.95], gain)

                band_signal = band_signal * gain * makeup

            ch_processed += band_signal

        processed[ch] = ch_processed

    if was_mono:
        return processed[0]
    return processed


def stereo_enhance(audio, intensity=0.6):
    """Mid-side stereo width enhancement."""
    if audio.ndim < 2 or audio.shape[0] < 2:
        return audio

    left, right = audio[0], audio[1]
    mid = (left + right) / 2
    side = (left - right) / 2

    # Widen side channel
    width = 1.0 + intensity * 0.5  # 1.0 to 1.5x width
    side = side * width

    audio[0] = mid + side
    audio[1] = mid - side
    return audio


def peak_limiter(audio, ceiling=-0.3, lookahead_ms=1):
    """Look-ahead peak limiter."""
    sr = 44100  # not critical, used for smoothing
    lookahead_samples = int(lookahead_ms * sr / 1000)
    if lookahead_samples < 1:
        lookahead_samples = 1

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    for ch in range(audio.shape[0]):
        ch_audio = audio[ch]
        envelope = np.abs(ch_audio)
        envelope = signal.medfilt(envelope, kernel_size=lookahead_samples * 2 + 1)

        overs = envelope > 10 ** (ceiling / 20.0)
        gain = np.ones_like(envelope)
        gain[overs] = (10 ** (ceiling / 20.0)) / (envelope[overs] + 1e-10)

        # Smooth gain reduction
        gain = signal.lfilter(np.ones(lookahead_samples) / lookahead_samples, [1], gain)
        audio[ch] = ch_audio * gain

    if was_mono:
        return audio[0]
    return audio


def ai_mastering(audio, sr, intensity=0.6):
    """Full mastering chain."""
    audio = sanitize_audio(audio)
    target_lufs = -16 + intensity * 4  # -16 to -12 LUFS

    # 1. Multi-band compression
    if intensity > 0.1:
        audio = multi_band_compressor(audio, sr, intensity)

    # 2. Stereo enhancement
    if audio.ndim >= 2:
        audio = stereo_enhance(audio, intensity)

    # 3. Harmonic saturation for warmth
    if intensity > 0.2:
        drive = intensity * 0.3
        audio = audio + drive * np.tanh(audio * 2)
        audio = soft_clip(audio, 0.95)

    # 4. Peak limiting
    audio = peak_limiter(audio, ceiling=-0.2 - intensity * 0.1, lookahead_ms=1.5)

    # 5. Loudness normalization
    audio = normalize_loudness(audio, sr, target_lufs)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='AI Mastering Processor')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = ai_mastering(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'ai_mastering'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
