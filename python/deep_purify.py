#!/usr/bin/env python3
"""
深度提存 - Deep Purification.
Flat spectrum optimization through:
- Parametric EQ to reduce spectral uniformity
- Harmonic exciter simulation
- Transient shaping
- Spectral variation injection
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, apply_eq_band, soft_clip, add_noise


def break_spectral_flatness(audio, sr, intensity=0.6):
    """
    AI music often has unnaturally flat spectral distribution.
    This injects controlled spectral variation to break that pattern.
    """
    nyquist = sr / 2

    # Apply a few gentle randomized EQ bands to break spectral uniformity
    num_bands = int(2 + intensity * 4)  # 2-6 bands
    np.random.seed(int(np.mean(np.abs(audio)) * 10000) % 100000)

    for _ in range(num_bands):
        freq = 100 + np.random.random() * (nyquist - 200)
        gain = np.random.uniform(-intensity * 0.6, intensity * 0.6)  # ±0.6dB max
        q = 0.6 + np.random.random() * 1.0
        audio = apply_eq_band(audio, sr, freq, gain, q, 'peaking')

    return audio


def harmonic_exciter(audio, sr, intensity=0.6):
    """Add subtle harmonic content to make audio sound richer/more analog."""
    if intensity < 0.1:
        return audio

    # Generate subtle harmonics via waveshaping
    drive = 0.2 + intensity * 0.3
    excited = soft_clip(audio * drive, 0.85)

    # Mix original with excited (very subtle)
    mix = intensity * 0.04
    audio = (1 - mix) * audio + mix * excited

    return audio


def transient_shaper(audio, sr, intensity=0.6):
    """Subtle transient shaping to break uniform ADSR patterns."""
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    for ch in range(audio.shape[0]):
        ch_audio = audio[ch]

        # Envelope follower
        envelope = np.abs(ch_audio)
        envelope = signal.lfilter([0.05], [1, -0.95], envelope)

        # Detect transients (fast rise)
        attack = np.diff(envelope, prepend=envelope[0])
        transients = attack > np.mean(attack) + np.std(attack) * 2

        # Slightly enhance attack transients
        attack_boost = 1.0 + intensity * 0.1
        boost = np.ones_like(ch_audio)
        # Apply boost at transient positions with fast decay
        for i in np.where(transients)[0]:
            end = min(i + int(sr * 0.02), len(boost))  # 20ms decay
            decay = np.linspace(attack_boost, 1.0, end - i)
            boost[i:end] = np.maximum(boost[i:end], decay)

        audio[ch] = ch_audio * boost

    if was_mono:
        return audio[0]
    return audio


def spectral_variation_injector(audio, sr, intensity=0.6):
    """
    Inject time-varying spectral changes to prevent the detector from
    finding stable spectral patterns across the entire track.
    """
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    num_segments = int(3 + intensity * 5)
    segment_len = audio.shape[-1] // num_segments
    if segment_len < sr:  # Don't segment too small
        segment_len = max(segment_len, int(sr * 0.5))

    for seg in range(num_segments):
        start = seg * segment_len
        end = min((seg + 1) * segment_len, audio.shape[-1])
        if end - start < sr * 0.3:
            continue

        # Random micro-EQ per segment (very subtle)
        freq = 200 + np.random.random() * (sr / 2 - 400)
        gain = np.random.uniform(-intensity * 0.4, intensity * 0.4)
        q = 0.6 + np.random.random() * 0.8

        for ch in range(audio.shape[0]):
            audio[ch, start:end] = apply_eq_band(audio[ch, start:end], sr, freq, gain, q)

    if was_mono:
        return audio[0]
    return audio


def deep_purify(audio, sr, intensity=0.6):
    """Complete deep purification chain (gentle processing)."""
    i = np.clip(intensity, 0, 1)

    # 1. Break spectral flatness with randomized EQ (gentle)
    audio = break_spectral_flatness(audio, sr, i * 0.6)

    # 2. Harmonic exciter for analog richness (subtle)
    audio = harmonic_exciter(audio, sr, i * 0.5)

    # 3. Transient shaping (gentle)
    audio = transient_shaper(audio, sr, i * 0.5)

    # 4. Spectral variation over time (subtle)
    audio = spectral_variation_injector(audio, sr, i * 0.4)

    # 5. Very subtle noise floor
    audio = add_noise(audio, level_db=-90 + i * 6)

    # 6. Final soft clip
    audio = soft_clip(audio, 0.97)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Deep Purification')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = deep_purify(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'deep_purify'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
