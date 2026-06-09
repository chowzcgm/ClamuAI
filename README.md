# 🎵 ClamuAI — AI Music Humanizer

> Make AI-generated music sound human. Evade AI detection on SubmitHub and similar platforms.

**ClamuAI** is an anti-detection audio processing system that post-processes Suno/Udio AI-generated music to pass AI content detectors. It applies human-like imperfections — phase randomization, spectral variation, micro pitch/time shifts — that break AI fingerprint patterns while preserving audio quality.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![PHP](https://img.shields.io/badge/PHP-7.4%2B-777bb4)](https://php.net)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab)](https://python.org)

---

## 📊 Results

| Metric | Raw Suno | After ClamuAI |
|--------|----------|---------------|
| Spectral Detection (human %) | ~12% | **72-80%** |
| Temporal Detection (human %) | ~59% | **98-99%** |

*Tested with SubmitHub AI Song Checker (Random Forest, 21 features, 4000 samples)*

## 🔬 How It Works

SubmitHub and similar detectors don't directly "detect AI" — they detect the **absence of human error**. AI-generated audio exhibits:
- Perfect phase coherence across channels
- Unnaturally flat spectral envelopes
- Mathematically precise BPM/timing
- Characteristic frequency bin patterns at 48kHz

ClamuAI introduces controlled, musically-transparent imperfections:

```
Upload → Metadata Strip → HF Watermark Removal → Adaptive Analysis
→ Tape Spectrum → Spectral Comb → Harmonic Saturation
→ Pitch Shift (30-67¢) → Time Stretch (1.003-1.010x)
→ Phase Coherence Breaker → Mid-Side Decorrelation
→ Spectral Contrast → Spectral Variation → 44.1kHz Resample
→ Stereo Widen → Noise Floor + Mastering → Output
```

### Key Techniques

| Stage | Effect | Why It Works |
|-------|--------|--------------|
| **Pitch Shift** | 30-67 cents shift | Breaks spectral fingerprint bin alignment |
| **Time Stretch** | 1.003-1.010x | Disrupts temporal pattern matching |
| **Phase Breaker** | 5-band all-pass cascade | Inaudible — changes phase only, not magnitude |
| **44.1kHz Resample** | 48kHz→44.1kHz | Shifts ALL detector feature binning |
| **Spectral Variation** | Time-varying 6-band EQ | Creates natural envelope drift |

### Adaptive Processing

Each song is analyzed before processing — parameters adjust automatically:
- Bright songs → stronger HF reduction
- Flat spectral profile → stronger contrast enhancement
- Low sub-bass → stronger bass boost
- Narrow stereo → stronger widening

## 🏗️ Architecture

```
clamuai/
├── index.php              # Router (?action=upload|smart_optimize|download|status)
├── config.php             # Paths, presets, upload limits
├── includes/
│   ├── functions.php      # Shared helpers (runPython, getAudioInfo, job status)
│   ├── main.php           # Upload UI, preset buttons, pipeline viz, results
│   ├── header.php / footer.php
├── modules/
│   ├── upload.php         # File upload → saves to uploads/<jobid>.ext
│   ├── smart_optimize.php # Main processing endpoint → calls Python
│   ├── status.php         # Progress polling endpoint
│   ├── download.php       # Streams processed file
│   └── records.php        # Job history
├── python/
│   ├── mmm_wrapper.py     # Core anti-detection pipeline (active)
│   └── audio_utils.py     # Audio analysis utilities (active)
├── assets/
│   ├── css/style.css      # Dark theme, two-column layout
│   └── js/app.js          # Upload, presets, progress, results display
├── uploads/               # Original uploaded files (gitignored)
├── outputs/               # Processed output files (gitignored)
└── temp/                  # Job status JSON (gitignored)
```

## 🚀 Quick Start

### Requirements
- **PHP 7.4+** with `exec()` enabled
- **Python 3.8+** with pip
- Web server (XAMPP, Apache, Nginx, or PHP built-in)

### Python Dependencies
```bash
pip install numpy scipy librosa soundfile soxr mutagen
```

### Installation
```bash
# Clone
git clone https://github.com/chowzcgm/ClamuAI.git
cd ClamuAI

# Install Python deps
pip install numpy scipy librosa soundfile soxr mutagen

# Edit config.php if needed (Python path, upload limits)

# Run with PHP built-in server
php -S localhost:8080

# Or place in your XAMPP htdocs folder and visit:
# http://localhost/ClamuAI
```

### Usage
1. Open the web interface
2. Upload an AI-generated audio file (WAV/MP3/FLAC)
3. Select intensity preset: **基础** (Light) / **标准** (Standard) / **极致** (Heavy)
4. Click **MMM引擎处理**
5. Download the processed file

### CLI Usage
```bash
# Process directly from command line
cd python
python mmm_wrapper.py \
  --input "../uploads/test.wav" \
  --output "../outputs/test_processed.wav" \
  --intensity 0.5
```

### Intensity Presets
| Preset | Intensity | Pitch Shift | Time Stretch | Active Stages |
|--------|-----------|-------------|--------------|---------------|
| 基础 (Light) | 0.5 | 54¢ | 1.006x | tape + pitch + stretch + master |
| 标准 (Standard) | 0.7 | 61¢ | 1.008x | + comb + sat + phase + MS + contrast |
| 极致 (Heavy) | 0.88 | 67¢ | 1.010x | + spectral_var + 44.1k + stereo widen |

## ⚠️ Known Limitations

- Different Suno songs have different detection baselines — no single setting works for all
- Audio quality vs. detection evasion is a fundamental trade-off
- Best results achieved on songs with strong vocals and clear spectral structure
- Built and tested on Windows with XAMPP; Linux/macOS may need path adjustments

## 📝 License

This project is licensed under the Apache License 2.0 — see [LICENSE](LICENSE) for details.

---

**Disclaimer:** This tool is for educational and research purposes. Use responsibly and in accordance with the terms of service of any platforms you submit music to.
