#!/usr/bin/env python3
"""
专业工具Pro - Professional Audio Tools Suite.
- Mid-side stereo processing
- Dynamic range expander
- Harmonic exciter (tube/tape saturation models)
- Format conversion (WAV/MP3/FLAC/AAC)
- Channel balance correction
- Vocal enhancement
"""

import argparse, sys, os, traceback, json
import numpy as np
from scipy import signal
import soundfile as sf
from pydub import AudioSegment

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import sanitize_audio, json_dumps, load_audio, save_audio, soft_clip


def mid_side_processor(audio, sr, intensity=0.6):
    """Mid-side processing for stereo width and depth control."""
    if audio.ndim < 2 or audio.shape[0] < 2:
        return audio

    left, right = audio[0], audio[1]
    mid = (left + right) / 2
    side = (left - right) / 2

    # Enhance mid clarity (gentle compression)
    mid_env = np.abs(mid)
    mid_env = signal.lfilter([0.02], [1, -0.98], mid_env)
    mid_thresh = 0.3
    ratio = 1.5 + intensity * 1.5
    mid_gain = np.ones_like(mid)
    above = mid_env > mid_thresh
    mid_gain[above] = mid_thresh + (mid_env[above] - mid_thresh) / ratio
    mid_gain = mid_gain / (mid_env + 1e-10)
    mid = mid * signal.lfilter([0.05], [1, -0.95], mid_gain)

    # Widen side
    side_width = 1.0 + intensity * 0.4
    side = side * side_width

    # Subtle side EQ
    nyquist = sr / 2
    b, a = signal.butter(2, 2000 / nyquist, btype='high')
    side = side + intensity * 0.15 * signal.lfilter(b, a, side)

    audio[0] = mid + side
    audio[1] = mid - side
    return audio


def dynamic_range_expander(audio, sr, intensity=0.6):
    """Expand dynamic range slightly to counter AI over-compression."""
    if intensity < 0.1:
        return audio

    was_mono = audio.ndim == 1
    if was_mono:
        audio = audio.reshape(1, -1)

    for ch in range(audio.shape[0]):
        envelope = np.abs(audio[ch])
        envelope = signal.lfilter([0.01], [1, -0.99], envelope)
        rms = np.mean(envelope)
        if rms < 1e-6:
            continue

        # Slight expansion: quiet parts quieter, loud parts slightly louder
        expand_ratio = 1.0 + intensity * 0.15
        gain = (envelope / rms) ** (expand_ratio - 1)
        gain = np.clip(gain, 0.7, 1.3)
        gain = signal.lfilter([0.05], [1, -0.95], gain)
        audio[ch] = audio[ch] * gain

    if was_mono:
        return audio[0]
    return audio


def tape_saturation(audio, intensity=0.6):
    """Tape machine saturation emulation (soft hysteresis-style)."""
    if intensity < 0.05:
        return audio

    drive = 0.2 + intensity * 1.5
    audio = audio * drive
    # Tape-like: asymmetric with slight bias
    audio = np.where(audio > 0,
                      np.tanh(audio * 1.1) * 0.85 + audio * 0.15,
                      np.tanh(audio * 1.4) * 0.75 + audio * 0.25)
    return audio / (0.5 + drive * 0.5)


def channel_balance(audio, intensity=0.6):
    """Auto-balance stereo channels."""
    if audio.ndim < 2 or audio.shape[0] < 2:
        return audio

    rms_left = np.sqrt(np.mean(audio[0] ** 2))
    rms_right = np.sqrt(np.mean(audio[1] ** 2))
    if rms_left < 1e-6 or rms_right < 1e-6:
        return audio

    balance = rms_left / rms_right
    target = 1.0

    # Gentle correction
    if balance > 1.1:
        audio[1] = audio[1] * (balance ** (intensity * 0.3))
    elif balance < 0.9:
        audio[0] = audio[0] * ((1 / balance) ** (intensity * 0.3))

    return audio


def format_converter(filepath, output_format='wav'):
    """Convert between audio formats using pydub."""
    audio = AudioSegment.from_file(filepath)
    tmp = os.path.splitext(filepath)[0] + '_converted.' + output_format
    if output_format == 'mp3':
        audio.export(tmp, format='mp3', bitrate='320k')
    elif output_format == 'flac':
        audio.export(tmp, format='flac')
    elif output_format == 'wav':
        audio.export(tmp, format='wav')
    return tmp


def pro_tools(audio, sr, intensity=0.6):
    """Complete professional tools chain."""

    # 1. Channel balance
    if audio.ndim >= 2:
        audio = channel_balance(audio, intensity)

    # 2. Mid-side processing for stereo control
    if audio.ndim >= 2:
        audio = mid_side_processor(audio, sr, intensity)

    # 3. Dynamic range expansion
    audio = dynamic_range_expander(audio, sr, intensity * 0.7)

    # 4. Tape saturation for analog character
    audio = tape_saturation(audio, intensity * 0.6)

    # 5. Final soft clip
    audio = soft_clip(audio, 0.95)

    return np.clip(audio, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description='Professional Audio Tools')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    parser.add_argument('--format', default=None, help='Output format (wav, mp3, flac)')
    args = parser.parse_args()

    try:
        audio, sr = load_audio(args.input)
        audio = np.atleast_1d(audio)
        audio = pro_tools(audio, sr, args.intensity)

        # Handle format conversion if specified
        output_ext = os.path.splitext(args.output)[1].lower()
        if output_ext == '.mp3':
            audio_int16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            seg = AudioSegment(
                audio_int16.tobytes() if audio.ndim <= 1 else audio_int16.T.flatten().tobytes(),
                frame_rate=sr, sample_width=2,
                channels=1 if audio.ndim <= 1 else min(audio.shape[0], 2)
            )
            seg.export(args.output, format='mp3', bitrate='320k')
        else:
            save_audio(args.output, audio, sr)

        print(json_dumps({'status': 'ok', 'module': 'pro_tools'}))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
