#!/bin/bash
#
# Voice Dictation Pro - Installation Script
# For macOS with Apple Silicon (M1/M2/M3/M4)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🎤 Voice Dictation Pro - Installation"
echo "======================================"
echo ""

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ This app is for macOS only"
    exit 1
fi

# Check Apple Silicon
if [[ "$(uname -m)" != "arm64" ]]; then
    echo "⚠️  Warning: This app is optimized for Apple Silicon (M1/M2/M3/M4)"
    echo "   It may work on Intel Macs but will be slower"
    echo ""
fi

# Check/Install Homebrew
if ! command -v brew &> /dev/null; then
    echo "📦 Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add brew to PATH for Apple Silicon
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# Install ffmpeg
echo "📦 Installing ffmpeg..."
brew install ffmpeg 2>/dev/null || echo "   ffmpeg already installed"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "📦 Installing Python..."
    brew install python@3.11
fi

# Create virtual environment
echo "🐍 Creating virtual environment..."
cd "$SCRIPT_DIR"
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo ""
echo "✅ Installation complete!"
echo ""

# Add alias to shell
SHELL_RC="$HOME/.zshrc"
if [[ "$SHELL" == *"bash"* ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

ALIAS_CMD="alias voice='cd \"$SCRIPT_DIR\" && source venv/bin/activate && python voice_dictation_pro.py'"

if ! grep -q "alias voice=" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# Voice Dictation Pro" >> "$SHELL_RC"
    echo "$ALIAS_CMD" >> "$SHELL_RC"
    echo "✅ Added 'voice' command to $SHELL_RC"
else
    echo "ℹ️  'voice' command already exists in $SHELL_RC"
fi

echo ""
echo "======================================"
echo "⚠️  IMPORTANT: Set up permissions!"
echo "======================================"
echo ""
echo "1. System Settings → Privacy & Security → Accessibility"
echo "   Click + and add your terminal app"
echo ""
echo "2. System Settings → Privacy & Security → Microphone"
echo "   Enable for your terminal app"
echo ""
echo "3. Restart your terminal"
echo ""
echo "4. Run: voice"
echo ""
