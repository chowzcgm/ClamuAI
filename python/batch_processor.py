#!/usr/bin/env python3
"""
批量处理工作站 - Batch Processing Workstation.
Processes multiple audio files with selected processing chain.
Supports queued batch jobs with progress tracking.

Usage: python batch_processor.py --input_dir <dir> --output_dir <dir>
       --modules label_purify,neural_fingerprint,ai_mastering --intensity 0.6
"""

import argparse, sys, os, traceback, json, glob as globmod
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import json_dumps, load_audio, save_audio

# Import all processing modules
from label_purify import label_purify
from neural_fingerprint import neural_fingerprint_removal
from deep_purify import deep_purify
from ai_to_human import ai_to_human
from vocal_eq import vocal_eq
from ai_mastering import ai_mastering
from smart_mixer import smart_mixer
from bass_enhancer import bass_enhancer
from pro_tools import pro_tools as pro_tools_process
from cover_engine import cover_engine
from smart_optimize import smart_optimize

MODULE_MAP = {
    'label_purify': ('AI原标签净化', label_purify),
    'neural_fingerprint': ('AI神经指纹去除', neural_fingerprint_removal),
    'deep_purify': ('深度提存', deep_purify),
    'ai_to_human': ('AI转真人引擎', ai_to_human),
    'vocal_eq': ('人声EQ', vocal_eq),
    'ai_mastering': ('AI母带处理器', ai_mastering),
    'smart_mixer': ('智能混音处理器', smart_mixer),
    'bass_enhancer': ('低频增强处理器', bass_enhancer),
    'pro_tools': ('专业工具Pro', pro_tools_process),
    'cover_engine': ('翻唱音频处理引擎', cover_engine),
    'smart_optimize': ('智能音质一键优化', smart_optimize),
}

SUPPORTED_EXTENSIONS = ['.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac']


def process_file(filepath, output_path, modules, intensity):
    """Process a single file through the selected modules."""
    audio, sr = load_audio(filepath)
    audio = np.atleast_1d(audio)

    for mod_key in modules:
        if mod_key not in MODULE_MAP:
            continue
        name, func = MODULE_MAP[mod_key]
        try:
            audio = func(audio, sr, intensity)
        except Exception as e:
            print(f'  Warning: {name} failed on {os.path.basename(filepath)}: {e}', file=sys.stderr)

    save_audio(output_path, np.clip(audio, -1.0, 1.0), sr)
    return True


def main():
    parser = argparse.ArgumentParser(description='Batch Processing Workstation')
    parser.add_argument('--input_dir', help='Input directory with audio files')
    parser.add_argument('--output_dir', help='Output directory')
    parser.add_argument('--input', help='Single input file')
    parser.add_argument('--output', help='Single output file')
    parser.add_argument('--modules', default='smart_optimize',
                        help='Comma-separated module names: ' + ','.join(MODULE_MAP.keys()))
    parser.add_argument('--intensity', type=float, default=0.6)
    parser.add_argument('--job_id', default='')
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    modules = [m.strip() for m in args.modules.split(',') if m.strip() in MODULE_MAP]

    if not modules:
        print(json_dumps({'error': 'No valid modules selected'}))
        sys.exit(1)

    try:
        # Single file mode (for pipeline integration)
        if args.input and args.output:
            success = process_file(args.input, args.output, modules, args.intensity)
            print(json_dumps({
                'status': 'ok',
                'module': 'batch_processor',
                'files_processed': 1,
                'modules_used': [MODULE_MAP[m][0] for m in modules]
            }))
            return

        # Directory mode
        if not args.input_dir or not args.output_dir:
            print(json_dumps({'error': 'Provide either --input/--output or --input_dir/--output_dir'}))
            sys.exit(1)

        os.makedirs(args.output_dir, exist_ok=True)

        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(globmod.glob(os.path.join(args.input_dir, '*' + ext)))
            files.extend(globmod.glob(os.path.join(args.input_dir, '*' + ext.upper())))

        if not files:
            print(json_dumps({'error': f'No audio files found in {args.input_dir}'}))
            sys.exit(1)

        results = []
        for i, f in enumerate(files):
            basename = os.path.splitext(os.path.basename(f))[0]
            output_path = os.path.join(args.output_dir, basename + '_processed.wav')
            print(f'[{i+1}/{len(files)}] Processing: {os.path.basename(f)}')
            success = process_file(f, output_path, modules, args.intensity)
            results.append({
                'file': os.path.basename(f),
                'output': os.path.basename(output_path),
                'success': success
            })

        print(json_dumps({
            'status': 'ok',
            'module': 'batch_processor',
            'files_processed': len(results),
            'success_count': sum(1 for r in results if r['success']),
            'modules_used': [MODULE_MAP[m][0] for m in modules],
            'results': results
        }))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
