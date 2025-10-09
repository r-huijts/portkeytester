#!/bin/bash

# Portkey Tester Installation Script
# Sets up a virtual environment and installs dependencies
#
# Usage:
#   source ./install.sh   (keeps venv activated)
#   OR
#   ./install.sh          (shows activation command)

set -e  # Exit on error

echo "🔧 Portkey Tester Setup"
echo "======================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
VENV_DIR="venv"

if [ -d "$VENV_DIR" ]; then
    echo "⚠️  Virtual environment already exists at ./$VENV_DIR"
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Removing old virtual environment..."
        rm -rf "$VENV_DIR"
    else
        echo "📦 Using existing virtual environment..."
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip -q

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""

# Check if script was sourced or executed
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    # Script was sourced - venv is already active
    echo "🎉 Virtual environment is now active!"
    echo ""
    echo "To run the Portkey testers:"
    echo "  python test_portkey.py        # Test chat completions"
    echo "  python test_embeddings.py     # Test embeddings"
    echo ""
    echo "To deactivate when done:"
    echo "  deactivate"
else
    # Script was executed - activation will be lost
    echo "⚠️  Note: Virtual environment was created but is not active."
    echo ""
    echo "To activate it, run:"
    echo "  source venv/bin/activate"
    echo ""
    echo "Or re-run this script with 'source' to auto-activate:"
    echo "  source ./install.sh"
    echo ""
    echo "Then run the testers:"
    echo "  python test_portkey.py        # Test chat completions"
    echo "  python test_embeddings.py     # Test embeddings"
fi
echo ""

