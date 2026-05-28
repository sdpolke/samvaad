#!/bin/bash

# Setup script for installing vendored pipecat and API requirements.

# Get the project root directory (parent of scripts)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DOGRAH_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DOGRAH_DIR"

if [[ ! -f pipecat/pyproject.toml ]]; then
    echo "Error: pipecat/ is missing. Clone the full repository." >&2
    exit 1
fi

echo "Setting up pipecat..."

# Install other requirements first so vendored pipecat wins any version conflicts
echo "Installing dograh API requirements..."
pip install -r api/requirements.txt

# Install pipecat last so it overrides any pipecat-ai pulled in by dependencies
echo "Installing pipecat dependencies..."
pip install -e ./pipecat[cartesia,deepgram,openai,elevenlabs,groq,google,azure,sarvam,soundfile,silero,webrtc,speechmatics,openrouter,camb]

echo "Setup complete! Pipecat is installed from ./pipecat."
