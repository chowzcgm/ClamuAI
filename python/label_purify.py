#!/usr/bin/env python3
"""
AI原标签净化系统 - AI Label Purification.
Removes AI generation traces through:
- Multi-format codec re-encoding chain to overwrite neural codec residuals
- Metadata stripping
- Phase randomization
- Subtle dithering
"""

import argparse
import sys
import os
import traceback
import json
import tempfile
import numpy as np
from pydub import AudioSegment

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, add_noise, allpass_phase_scramble


def label_purify(audio, sr, intensity=0.6):
    """
    Strip AI generation labels by:
    1. Gentle phase variation (single stage) to break phase coherence
    2. Subtle dither to mask quantization patterns
    3. Very subtle high-frequency fill
    """
    audio = sanitize_audio(np.asarray(audio, dtype=np.float64))
    i = np.clip(intensity, 0, 1)

    # 1. Gentle phase variation (single stage only)
    if i > 0.15:
        audio = allpass_phase_scramble(audio, sr, num_stages=1)

    # 2. Subtle dither at very low level
    if i > 0.1:
        dither_level = -96 + i * 6  # -96dB to -90dB
        signal_rms = np.sqrt(np.mean(np.square(audio, dtype=np.float64))) + 1e-10
        dither = (np.random.rand(*audio.shape) + np.random.rand(*audio.shape) - 1.0).astype(np.float32)
        dither = dither * (signal_rms * (10 ** (dither_level / 20.0))) / (np.std(dither) + 1e-10)
        audio = audio + dither

    # 3. Very gentle high-frequency fill (below -70dB)
    if i > 0.3 and sr >= 44100:
        from scipy import signal as sig
        nyquist = sr / 2
        b, a = sig.butter(4, 17000 / nyquist, btype='high')
        hf_noise = np.random.randn(*audio.shape).astype(np.float32) * i * 0.00002
        if audio.ndim > 1:
            for ch in range(audio.shape[0]):
                audio[ch] = audio[ch] + sig.lfilter(b, a, hf_noise[ch] if hf_noise.ndim > 1 else hf_noise)
        else:
            audio = audio + sig.lfilter(b, a, hf_noise)

    return sanitize_audio(audio)


def codec_reencode(filepath, intensity):
    """
    Re-encode the audio through multiple codecs to destroy neural codec residual patterns.
    This is the core technique that breaks ArtifactNet-style detection.
    """
    # Load with pydub for format handling
    audio_seg = AudioSegment.from_file(filepath)
    orig_sr = audio_seg.frame_rate

    reencode_chains = {
        'light': ['mp3'],  # Single MP3 re-encode
        'medium': ['flac', 'mp3'],  # FLAC then MP3
        'heavy': ['ogg', 'flac', 'mp3', 'ogg', 'mp3']  # Multiple format hops
    }

    if intensity < 0.3:
        chain = reencode_chains['light']
    elif intensity < 0.7:
        chain = reencode_chains['medium']
    else:
        chain = reencode_chains['heavy']

    current = audio_seg
    for fmt in chain:
        tmp = tempfile.NamedTemporaryFile(suffix=f'.{fmt}', delete=False)
        tmp.close()
        try:
            if fmt == 'mp3':
                current.export(tmp.name, format='mp3', bitrate='320k')
            elif fmt == 'flac':
                current.export(tmp.name, format='flac')
            elif fmt == 'ogg':
                current.export(tmp.name, format='ogg', parameters=['-q:a', '8'])
            current = AudioSegment.from_file(tmp.name)
        finally:
            os.unlink(tmp.name)

    return current


def main():
    parser = argparse.ArgumentParser(description='AI Label Purification')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    try:
        # Step 1: Codec re-encoding to break neural codec residuals
        reencoded = codec_reencode(args.input, args.intensity)

        # Convert back to numpy for processing
        samples = np.array(reencoded.get_array_of_samples(), dtype=np.float32) / 32768.0
        sr = reencoded.frame_rate
        if reencoded.channels > 1:
            samples = samples.reshape(-1, reencoded.channels).T

        # Step 2: Apply dither, phase scramble, HF smoothing
        samples = label_purify(samples, sr, args.intensity)

        # Step 3: Final format output
        output_ext = os.path.splitext(args.output)[1].lower()
        if output_ext == '.mp3':
            audio_int16 = (samples * 32767).astype(np.int16)
            seg = AudioSegment(
                audio_int16.tobytes() if samples.ndim == 1 else audio_int16.T.flatten().tobytes(),
                frame_rate=sr,
                sample_width=2,
                channels=1 if samples.ndim == 1 else min(samples.shape[0], 2)
            )
            seg.export(args.output, format='mp3', bitrate='320k')
        else:
            save_audio(args.output, samples, sr)

        print(json_dumps({'status': 'ok', 'module': 'label_purify'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
