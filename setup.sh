#!/bin/bash
# Workout Tracker — One-time setup

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/workout-tracker"
KEY_PATH="$CONFIG_DIR/firebase-key.json"

echo "=== Workout Tracker Setup ==="
echo ""

# Create config directory
mkdir -p "$CONFIG_DIR"

# Create virtualenv
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
fi

# Install dependencies
echo "Installing dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "=== Firebase Setup ==="
echo ""

if [ -f "$KEY_PATH" ]; then
    echo "Firebase key found at: $KEY_PATH"
else
    echo "You need a Firebase service account key. Here's how:"
    echo ""
    echo "  1. Go to https://console.firebase.google.com"
    echo "  2. Create a new project (or use an existing one)"
    echo "  3. Go to: Firestore Database → Create database → Start in test mode"
    echo "  4. Go to: Project Settings (gear icon) → Service Accounts"
    echo "  5. Click 'Generate New Private Key' → Download the JSON file"
    echo "  6. Move/copy it here:"
    echo ""
    echo "     mv ~/Downloads/<your-key-file>.json $KEY_PATH"
    echo ""
    read -p "Press Enter once you've placed the key file... "

    if [ ! -f "$KEY_PATH" ]; then
        echo "Warning: Key file not found at $KEY_PATH"
        echo "You can add it later and run the app."
        exit 1
    fi
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To run the app:"
echo "  $SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/app.py"
echo ""
echo "Or add an alias to your shell config:"
echo "  alias workout='$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/app.py'"
