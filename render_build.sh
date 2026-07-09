#!/usr/bin/env bash
set -e

echo "==> Installing Python packages..."
pip install -r requirements.txt

echo "==> Installing Playwright Chromium browser..."
playwright install chromium

echo "==> Build complete!"
