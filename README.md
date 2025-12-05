<div align="center">

# Voice Dictation Pro

**Fast local voice dictation for macOS with Apple Silicon optimization**

[![macOS](https://img.shields.io/badge/macOS-12+-blue?logo=apple)](https://www.apple.com/macos/)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-M1%2FM2%2FM3%2FM4-orange)](https://support.apple.com/en-us/HT211814)
[![Python](https://img.shields.io/badge/Python-3.9+-green?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

<img src="assets/demo.gif" alt="Demo" width="600">

*Hold Option+Space → speak → release → Space to insert*

</div>

---

## Features

- **Fast** — Recognition in 0.3-0.5 sec thanks to MLX Whisper
- **Private** — Everything runs locally, no data leaves your Mac
- **Beautiful** — Native glassmorphism UI in Apple style
- **Multi-monitor** — Overlay appears on active screen
- **Simple** — Hold → speak → release → done

## How It Works

1. **Hold `Option + Space`** — Recording starts, overlay appears
2. **Speak** — Your voice is being recorded
3. **Release** — Text is recognized (~0.3 sec)
4. **Press `Space`** — Text is inserted into active field
5. **Or `Esc`** — Cancel

## Installation

### Quick Install

```bash
git clone https://github.com/Valeron2206/voice-dictation-pro.git
cd voice-dictation-pro
./install.sh
```

### Manual Installation

```bash
# Install dependencies
brew install ffmpeg python@3.11

# Clone repository
git clone https://github.com/Valeron2206/voice-dictation-pro.git
cd voice-dictation-pro

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

## Setting Up Permissions

After installation, you **must** grant permissions:

### 1. Accessibility (for key interception)
```
System Settings → Privacy & Security → Accessibility
```
Click **+** and add your terminal:
- Terminal.app: `/Applications/Utilities/Terminal.app`
- iTerm2: `/Applications/iTerm.app`
- VS Code: `/Applications/Visual Studio Code.app`
- Warp: `/Applications/Warp.app`

### 2. Microphone (for voice recording)
```
System Settings → Privacy & Security → Microphone
```
Enable for your terminal app.

### 3. Restart your terminal

## Usage

```bash
voice
```

Or directly:
```bash
cd voice-dictation-pro
source venv/bin/activate
python voice_dictation_pro.py
```

### Hotkeys

| Key | Action |
|-----|--------|
| `Option + Space` (hold) | Start recording |
| Release | Stop and recognize |
| `Space` | Insert text |
| `Esc` | Cancel |
| `Ctrl + C` | Exit application |

## Language Configuration

Default language is Russian. Change in `voice_dictation_pro.py`:

```python
@dataclass
class Config:
    language: str = "ru"  # "en", "de", "fr", None (auto-detect)
```

## Configuration

At the top of `voice_dictation_pro.py`:

```python
@dataclass
class Config:
    # Recognition
    language: str = "ru"                              # Language
    model: str = "mlx-community/whisper-medium-mlx"   # Whisper model

    # Audio
    sample_rate: int = 16000

    # UX
    play_sounds: bool = True          # Sounds on record
    min_recording_duration: float = 0.3  # Min recording duration
```

### Available Models

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `mlx-community/whisper-tiny-mlx` | ~75 MB | Very fast | Basic |
| `mlx-community/whisper-small-mlx` | ~460 MB | Fast | Good |
| `mlx-community/whisper-medium-mlx` | ~1.5 GB | Medium | Excellent |
| `mlx-community/whisper-large-v3-mlx` | ~3 GB | Slower | Best |

## Requirements

- **macOS** 12 Monterey or newer
- **Apple Silicon** (M1, M2, M3, M4)
- **Python** 3.9+
- **~2 GB** free space (for Whisper model)

## Technologies

- [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Speech recognition optimized for Apple Silicon
- [PyObjC](https://pyobjc.readthedocs.io/) — Native UI and Event Tap
- [sounddevice](https://python-sounddevice.readthedocs.io/) — Audio recording

## Troubleshooting

### Event Tap not working
```
Error: Failed to create Event Tap
```
→ Add terminal to Accessibility and **restart** it

### Text not inserting
→ Make sure cursor is in a text field before pressing Space

### Microphone not working
```
Warning: Microphone permission required
```
→ Enable microphone for terminal in System Settings

### Model takes long to load
First launch downloads the model (~1.5 GB). This is normal.

## License

MIT License — do what you want, but at your own risk.

## Contributing

PRs and Issues are welcome!

---

<div align="center">

**Made with love for macOS**

</div>
