#!/usr/bin/env python3
"""
低频增强处理器 - Bass Enhancement Processor.
- Sub-bass harmonic synthesis (generates harmonics for low end presence)
- Bass compression for tightness
- Tube saturation for analog warmth
- Mono-izing low frequencies for phase coherence
- 808 / kick / bass synth bus processing
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, soft_clip


def sub_harmonic_synthesis(audio, sr, intensity=0.6):
    """Generate sub-harmonics to enhance low-end presence."""
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    nyquist = sr / 2

    for ch in range(audio.shape[0]):
        ch_audio = audio[ch]

        # Extract low frequencies (below 120Hz)
        b, a = signal.butter(4, 120 / nyquist, btype='low')
        low_band = signal.lfilter(b, a, ch_audio)

        # Generate 2nd harmonic (octave down) via full-wave rectification
        sub = np.abs(low_band)
        # Filter the sub to keep it clean
        b_sub, a_sub = signal.butter(2, 60 / nyquist, btype='low')
        sub = signal.lfilter(b_sub, a_sub, sub)
        # Normalize and mix
        sub_rms = np.sqrt(np.mean(sub ** 2)) + 1e-10
        sub = sub / sub_rms * np.sqrt(np.mean(low_band ** 2)) * intensity * 0.3

        audio[ch] = ch_audio + sub

    if was_mono:
        return audio[0]
    return audio


def bass_compressor(audio, sr, intensity=0.6):
    """Dedicated bass band compression."""
    nyquist = sr / 2
    b, a = signal.butter(4, 120 / nyquist, btype='low')

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    for ch in range(audio.shape[0]):
        low = signal.lfilter(b, a, audio[ch])
        high = audio[ch] - low

        # Heavy compression on bass
        threshold = 0.25 - intensity * 0.1
        ratio = 2 + intensity * 4
        makeup = 1.0 + intensity * 0.4

        envelope = np.abs(low)
        envelope = signal.lfilter([0.02], [1, -0.98], envelope)

        above = envelope > threshold
        gain = np.ones_like(envelope)
        gain[above] = threshold + (envelope[above] - threshold) / ratio
        gain = gain / (envelope + 1e-10)
        gain = signal.lfilter([0.05], [1, -0.95], gain)

        audio[ch] = high + low * gain * makeup

    if was_mono:
        return audio[0]
    return audio


def mono_low_end(audio, sr, crossover=150):
    """Make frequencies below crossover mono for phase coherence."""
    if audio.ndim < 2 or audio.shape[0] < 2:
        return audio

    nyquist = sr / 2
    b, a = signal.butter(4, crossover / nyquist, btype='low')

    left_low = signal.lfilter(b, a, audio[0])
    right_low = signal.lfilter(b, a, audio[1])
    mono_low = (left_low + right_low) / 2

    left_high = audio[0] - left_low
    right_high = audio[1] - right_low

    audio[0] = left_high + mono_low
    audio[1] = right_high + mono_low
    return audio


def tube_bass_saturation(audio, intensity=0.6):
    """Warm tube saturation tailored for bass."""
    if intensity < 0.05:
        return audio

    drive = 0.3 + intensity * 3.0
    audio = audio * drive
    # Warmer asymmetric saturation curve
    audio = np.where(audio > 0,
                      np.tanh(audio * 0.8),
                      np.tanh(audio * 1.5))
    return audio / (np.sqrt(drive))


def bass_enhancer(audio, sr, intensity=0.6):
    """Complete bass enhancement chain."""

    # 1. Mono-ize low frequencies for tighter bass
    if audio.ndim >= 2 and intensity > 0.1:
        audio = mono_low_end(audio, sr, crossover=120 + intensity * 30)

    # 2. Sub-harmonic synthesis
    if intensity > 0.2:
        audio = sub_harmonic_synthesis(audio, sr, intensity)

    # 3. Bass compression
    if intensity > 0.2:
        audio = bass_compressor(audio, sr, intensity)

    # 4. Tube saturation for warmth
    if intensity > 0.1:
        audio = tube_bass_saturation(audio, intensity * 0.7)

    # 5. Soft clip
    audio = soft_clip(audio, 0.95)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Bass Enhancement Processor')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = bass_enhancer(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'bass_enhancer'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
