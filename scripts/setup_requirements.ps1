#!/usr/bin/env pwsh
# Setup script for installing Python dependencies, including vendored pipecat (Windows).
#
# Usage:
#   ./scripts/setup_requirements.ps1          # default: install runtime deps
#   ./scripts/setup_requirements.ps1 -Dev     # also install pipecat dev deps

[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir   = Split-Path -Parent $ScriptDir
Set-Location $BaseDir

if (-not (Test-Path 'pipecat/pyproject.toml')) {
    Write-Host 'Error: pipecat/ is missing. Clone the full repository.' -ForegroundColor Red
    exit 1
}

Write-Host 'Setting up Python requirements...'

# Install dograh API requirements first so pipecat's extras win on any
# shared transitive dependencies (matches api/Dockerfile and CI workflow).
Write-Host 'Installing dograh API requirements...'
pip install -r api/requirements.txt

if ($Dev) {
    Write-Host 'Installing dograh API dev requirements...'
    pip install -r api/requirements.dev.txt
}

# Install pipecat in editable mode with all extras
Write-Host 'Installing pipecat dependencies...'
pip install -e './pipecat[cartesia,deepgram,openai,elevenlabs,groq,google,azure,sarvam,soundfile,silero,webrtc,speechmatics,openrouter,camb]'

if ($Dev) {
    Write-Host 'Installing pipecat dev dependencies...'
    pip install --upgrade pip
    pip install --group pipecat/pyproject.toml:dev
}

Write-Host 'Setup complete! Requirements are installed.'
