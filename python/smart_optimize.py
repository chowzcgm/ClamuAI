#!/usr/bin/env python3
"""
智能音质一键优化 - Smart One-Click Full Chain Optimization (Suno-optimized).
Runs all essential modules in optimal order:
1. label_purify -> 2. neural_fingerprint -> 3. suno_specialist
-> 4. deep_purify -> 5. ai_to_human -> 6. vocal_eq -> 7. ai_mastering
"""

import argparse, sys, os, traceback, json
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import json_dumps, load_audio, save_audio, sanitize_audio
from label_purify import label_purify
from neural_fingerprint import neural_fingerprint_removal
from suno_specialist import suno_vocal_humanize
from deep_purify import deep_purify
from ai_to_human import ai_to_human
from vocal_eq import vocal_eq
from ai_mastering import ai_mastering


def smart_optimize(audio, sr, intensity=0.6):
    """Run essential Suno-optimized chain. Chain intensity is reduced to prevent cumulative degradation."""
    # Chain intensity: reduce slightly to prevent cumulative effect buildup
    ci = np.clip(intensity * 0.85, 0.15, 1.0)

    steps = [
        ('Neural Fingerprint Removal', neural_fingerprint_removal),
        ('Suno Vocal Specialist', suno_vocal_humanize),
        ('AI to Human', ai_to_human),
        ('AI Mastering', ai_mastering),
    ]

    for name, func in steps:
        try:
            audio = func(audio, sr, ci)
            audio = sanitize_audio(audio)
        except Exception as e:
            print(f'Warning: {name} failed: {e}', file=sys.stderr)
            continue

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Smart One-Click Optimization')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = smart_optimize(audio, sr, args.intensity)
        save_audio(args.output, audio, sr)
        print(json_dumps({'status': 'ok', 'module': 'smart_optimize'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
