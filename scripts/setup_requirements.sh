#!/bin/bash

# Setup script for installing Python dependencies, including vendored pipecat.
#
# Usage:
#   ./scripts/setup_requirements.sh           # default: install runtime deps
#   ./scripts/setup_requirements.sh --dev     # also install pipecat dev deps

set -euo pipefail

DEV_MODE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)
            DEV_MODE=1
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--dev]" >&2
            exit 1
            ;;
    esac
done

# Get the project root directory (parent of scripts)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOGRAH_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DOGRAH_DIR"

if [[ ! -f pipecat/pyproject.toml ]]; then
    echo "Error: pipecat/ is missing. Clone the full repository." >&2
    exit 1
fi

echo "Setting up Python requirements..."

# Install dograh API requirements first so pipecat's extras win on any
# shared transitive dependencies (matches api/Dockerfile and CI workflow).
echo "Installing dograh API requirements..."
pip install -r api/requirements.txt

if [ "$DEV_MODE" -eq 1 ]; then
    echo "Installing dograh API dev requirements..."
    pip install -r api/requirements.dev.txt
fi

# Install pipecat in editable mode with all extras
echo "Installing pipecat dependencies..."
pip install -e ./pipecat[cartesia,deepgram,openai,elevenlabs,groq,google,azure,sarvam,soundfile,silero,webrtc,speechmatics,openrouter,camb,mcp]

if [ "$DEV_MODE" -eq 1 ]; then
    echo "Installing pipecat dev dependencies..."
    pip install --upgrade pip
    pip install --group pipecat/pyproject.toml:dev
fi

echo "Setup complete! Requirements are installed."
