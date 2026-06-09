#!/usr/bin/env python3
"""
ClamuAI Quality Check — Compare original vs processed audio.
Uses cross-spectral coherence, PSD analysis, and spectral flatness
to objectively measure processing effectiveness.

Key metrics:
- Coherence: How much musical content is preserved (higher = better)
- Watermark band coherence: Should be LOW (watermarks destroyed)
- AI residue score delta: How much "AI signature" was reduced
- PSD preservation by band: Per-band energy retention

Usage:
    python quality_check.py --original <path> --processed <path> [--json]
"""

import argparse
import sys
import os
import json
import traceback
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from audio_utils import (load_audio, json_dumps, _compute_psd,
                         _spectral_flatness_db, _spectral_slope, _ai_residue_score)


def compute_coherence(orig_audio, proc_audio, sr, nperseg=4096):
    """
    Compute magnitude-squared coherence between original and processed.
    Returns (freqs, coherence) where coherence is in [0, 1].
    """
    from scipy import signal

    # Convert to mono for coherence
    orig_mono = orig_audio if orig_audio.ndim == 1 else np.mean(orig_audio, axis=0)
    proc_mono = proc_audio if proc_audio.ndim == 1 else np.mean(proc_audio, axis=0)

    # Match lengths
    min_len = min(len(orig_mono), len(proc_mono))
    orig_mono = orig_mono[:min_len]
    proc_mono = proc_mono[:min_len]

    if min_len < nperseg:
        nperseg = min_len // 2

    f, Cxy = signal.coherence(orig_mono, proc_mono, fs=sr, nperseg=nperseg)
    return f, Cxy


def band_metric(freqs, values, band, metric='mean'):
    """Aggregate metric values within a frequency band."""
    mask = (freqs >= band[0]) & (freqs < band[1])
    if not np.any(mask):
        return 0.0
    if metric == 'mean':
        return float(np.mean(values[mask]))
    elif metric == 'min':
        return float(np.min(values[mask]))
    elif metric == 'max':
        return float(np.max(values[mask]))
    return float(np.mean(values[mask]))


def compute_psd_ratio(orig_audio, proc_audio, sr, nperseg=4096):
    """Compute PSD ratio (processed / original) in dB."""
    orig_mono = orig_audio if orig_audio.ndim == 1 else np.mean(orig_audio, axis=0)
    proc_mono = proc_audio if proc_audio.ndim == 1 else np.mean(proc_audio, axis=0)
    min_len = min(len(orig_mono), len(proc_mono))
    orig_mono = orig_mono[:min_len]
    proc_mono = proc_mono[:min_len]

    f_orig, psd_orig = _compute_psd(orig_mono, sr)
    f_proc, psd_proc = _compute_psd(proc_mono, sr)

    # Use common frequency grid
    min_freqs = min(len(f_orig), len(f_proc))
    ratio_db = 10.0 * np.log10(psd_proc[:min_freqs] / (psd_orig[:min_freqs] + 1e-12))
    return f_orig[:min_freqs], ratio_db


def quality_check(orig_path, proc_path):
    """
    Run full quality comparison between original and processed audio.

    Returns dict with:
        - coherence_by_band: Coherence in musical vs watermark bands
        - psd_ratio_by_band: Energy change per band (dB)
        - ai_score_delta: Reduction in AI residue score
        - spectral_slope_delta: Change in spectral slope
        - overall_preservation: 0-100 score of music content preservation
        - watermark_disruption: 0-100 score of watermark band disruption
    """
    orig_audio, sr1 = load_audio(orig_path)
    proc_audio, sr2 = load_audio(proc_path)

    # Resample if needed
    if sr1 != sr2:
        import librosa
        if proc_audio.ndim > 1:
            proc_audio = librosa.resample(proc_audio, orig_sr=sr2, target_sr=sr1, axis=-1)
        else:
            proc_audio = librosa.resample(proc_audio, orig_sr=sr2, target_sr=sr1)
        sr2 = sr1
    sr = sr1

    # === 1. Coherence Analysis ===
    f_coh, coh = compute_coherence(orig_audio, proc_audio, sr)

    # Musical content bands (should have HIGH coherence = preserved)
    music_bands = {
        'sub_bass': (20, 80),
        'bass': (80, 300),
        'low_mid': (300, 1000),
        'mid': (1000, 4000),
        'presence': (4000, 8000),
    }
    # Watermark / HF bands (should have LOW coherence = disrupted)
    wm_bands = {
        'low_watermark': (8000, 12000),
        'mid_watermark': (12000, 16000),
        'high_watermark': (16000, 20000),
        'ultrasonic': (20000, 22000),
    }

    coherence_by_band = {}
    for name, band in {**music_bands, **wm_bands}.items():
        if band[0] >= sr / 2:
            coherence_by_band[name] = None  # beyond Nyquist
            continue
        effective_high = min(band[1], sr / 2 * 0.95)
        coherence_by_band[name] = round(band_metric(f_coh, coh, (band[0], effective_high)), 4)

    # === 2. PSD Ratio Analysis ===
    f_ratio, ratio_db = compute_psd_ratio(orig_audio, proc_audio, sr)
    psd_ratio_by_band = {}
    for name, band in {**music_bands, **wm_bands}.items():
        if band[0] >= sr / 2:
            psd_ratio_by_band[name] = None
            continue
        effective_high = min(band[1], sr / 2 * 0.95)
        psd_ratio_by_band[name] = round(
            band_metric(f_ratio, ratio_db, (band[0], effective_high)), 2
        )

    # === 3. AI Residue Score Delta ===
    f_orig, psd_orig = _compute_psd(orig_audio, sr)
    f_proc, psd_proc = _compute_psd(proc_audio, sr)

    flatness_orig = _spectral_flatness_db(psd_orig)
    slope_orig = _spectral_slope(f_orig, psd_orig)
    ai_score_orig = _ai_residue_score(flatness_orig, slope_orig)

    flatness_proc = _spectral_flatness_db(psd_proc)
    slope_proc = _spectral_slope(f_proc, psd_proc)
    ai_score_proc = _ai_residue_score(flatness_proc, slope_proc)

    # === 4. Composite Scores ===
    # Music preservation: avg coherence across music bands (should be HIGH)
    music_coh_vals = [coherence_by_band[k] for k in music_bands
                      if coherence_by_band.get(k) is not None]
    if music_coh_vals:
        overall_preservation = round(np.mean(music_coh_vals) * 100, 1)
    else:
        overall_preservation = 0.0

    # Watermark disruption: 1 - coherence in watermark bands
    wm_coh_vals = [coherence_by_band[k] for k in wm_bands
                   if coherence_by_band.get(k) is not None]
    if wm_coh_vals:
        wm_mean_coh = np.mean(wm_coh_vals)
        watermark_disruption = round((1.0 - wm_mean_coh) * 100, 1)
    else:
        watermark_disruption = 0.0

    return {
        'coherence_by_band': coherence_by_band,
        'psd_ratio_db_by_band': psd_ratio_by_band,
        'ai_score': {
            'original': ai_score_orig,
            'processed': ai_score_proc,
            'delta': round(ai_score_proc - ai_score_orig, 1),
        },
        'spectral_flatness_db': {
            'original': round(flatness_orig, 2),
            'processed': round(flatness_proc, 2),
        },
        'spectral_slope': {
            'original': round(slope_orig, 3),
            'processed': round(slope_proc, 3),
        },
        'overall_music_preservation': overall_preservation,
        'watermark_disruption': watermark_disruption,
        'sample_rate': int(sr),
    }


def main():
    parser = argparse.ArgumentParser(description='ClamuAI Quality Check')
    parser.add_argument('--original', required=True, help='Original/input audio file')
    parser.add_argument('--processed', required=True, help='Processed/output audio file')
    args = parser.parse_args()

    try:
        if not os.path.exists(args.original):
            print(json_dumps({'error': f'Original file not found: {args.original}'}))
            sys.exit(1)
        if not os.path.exists(args.processed):
            print(json_dumps({'error': f'Processed file not found: {args.processed}'}))
            sys.exit(1)

        result = quality_check(args.original, args.processed)
        print(json_dumps(result))
    except Exception as e:
        print(json_dumps({'error': str(e), 'traceback': traceback.format_exc()}))
        sys.exit(1)


if __name__ == '__main__':
    main()
