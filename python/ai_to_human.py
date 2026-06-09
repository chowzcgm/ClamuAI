#!/usr/bin/env python3
"""
AI转真人引擎 - AI-to-Human Engine.
Makes AI-generated audio sound more human by:
- Adding micro-timing variations (breaking perfect quantization)
- Subtle pitch drift (LFO modulation, ±5-10 cents)
- Dynamic range micro-variations
- Groove/swing feel simulation
- Stereo field modulation
"""

import argparse
import sys
import os
import traceback
import json
import numpy as np
from scipy import signal
import librosa

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, soft_clip


def ai_to_human(audio, sr, intensity=0.6):
    """
    Transform AI audio characteristics to sound more human by introducing
    natural imperfections that human performances have.
    """
    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    num_channels = audio.shape[0]

    for ch in range(num_channels):
        ch_audio = audio[ch].copy()

        # 1. Micro-timing variation: random time shifts (5-15ms at max intensity)
        if intensity > 0.1:
            shift_ms = intensity * np.random.uniform(3, 15)
            shift_samples = int(shift_ms * sr / 1000)
            if shift_samples > 0:
                direction = 1 if np.random.random() > 0.5 else -1
                shift_samples *= direction
                ch_audio = np.roll(ch_audio, shift_samples)
                if shift_samples > 0:
                    ch_audio[:shift_samples] = ch_audio[shift_samples:shift_samples * 2]
                else:
                    ch_audio[shift_samples:] = ch_audio[2 * shift_samples:shift_samples]

        # 2. Subtle pitch drift with slow LFO (breaks stable pitch detection)
        if intensity > 0.05:
            duration = len(ch_audio) / sr
            t = np.arange(len(ch_audio)) / sr

            # Slow random LFO (0.1-0.3 Hz) for natural pitch variation
            lfo_freq = 0.1 + np.random.random() * 0.2
            lfo_amplitude = intensity * np.random.uniform(-8, 8)  # max ±8 cents
            pitch_shift_cents = lfo_amplitude * np.sin(2 * np.pi * lfo_freq * t + np.random.random() * np.pi)

            # Add second LFO for more organic movement
            lfo2_freq = 0.4 + np.random.random() * 0.3
            lfo2_amplitude = intensity * np.random.uniform(-3, 3)
            pitch_shift_cents += lfo2_amplitude * np.sin(2 * np.pi * lfo2_freq * t + np.random.random() * np.pi)

            # Apply pitch shift with STFT-based processing for segments
            segment_len = int(sr * 2)  # 2 second segments
            hop = segment_len // 2

            for start in range(0, len(ch_audio) - segment_len, hop):
                end = start + segment_len
                seg = ch_audio[start:end]
                avg_cents = float(np.mean(pitch_shift_cents[start:end]))
                if abs(avg_cents) > 0.5:
                    try:
                        seg_shifted = librosa.effects.pitch_shift(
                            seg, sr=sr, n_steps=avg_cents / 100, bins_per_octave=24
                        )
                        ch_audio[start:end] = seg_shifted
                    except Exception:
                        pass

        # 3. Dynamic range micro-variations (breaks perfect ADSR)
        if intensity > 0.15:
            # Apply subtle volume LFO for breath-like dynamics
            t = np.arange(len(ch_audio)) / sr
            vol_lfo_freq = 0.2 + np.random.random() * 0.5
            vol_lfo = 1.0 + intensity * 0.03 * np.sin(2 * np.pi * vol_lfo_freq * t)
            ch_audio = ch_audio * vol_lfo

            # Subtle transient shaping - slightly round attack transients
            attack_smooth_samples = int((1 + intensity * 10) * sr / 1000)
            if attack_smooth_samples > 1:
                kernel = np.hanning(attack_smooth_samples * 2 + 1)
                kernel = kernel / kernel.sum()
                envelope = np.abs(ch_audio)
                envelope = signal.convolve(envelope, kernel, mode='same')
                # Apply very gentle gain riding
                envelope_smooth = envelope / (np.mean(envelope) + 1e-10)
                gain = 1.0 - intensity * 0.05 * (envelope_smooth - 1.0)
                ch_audio = ch_audio * np.clip(gain, 0.85, 1.15)

        audio[ch] = ch_audio

    # 4. Stereo field modulation (break static spatial positioning)
    if num_channels >= 2 and intensity > 0.1:
        left, right = audio[0], audio[1]

        # Subtle mid-side processing
        mid = (left + right) / 2
        side = (left - right) / 2

        # Modulate side channel slightly
        t = np.arange(len(side)) / sr
        mod_depth = intensity * 0.15
        mod_lfo = 0.05 + np.random.random() * 0.15
        side_mod = side * (1.0 + mod_depth * np.sin(2 * np.pi * mod_lfo * t))

        # Random channel delay (Haas effect simulation, 1-8ms)
        delay_ms = intensity * np.random.uniform(1, 8)
        delay_samples = int(delay_ms * sr / 1000)
        if delay_samples > 0:
            ch_to_delay = np.random.randint(0, 2)
            if ch_to_delay == 0:
                left = np.roll(left, delay_samples)
                left[:delay_samples] *= 0.7
            else:
                right = np.roll(right, delay_samples)
                right[:delay_samples] *= 0.7

        audio[0] = mid + side_mod
        audio[1] = mid - side_mod

    if was_mono:
        audio = audio[0]

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='AI-to-Human Engine')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = ai_to_human(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'ai_to_human'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
