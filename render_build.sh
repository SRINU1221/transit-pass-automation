#!/usr/bin/env bash
set -e

echo "==> Installing Python packages..."
pip install -r requirements.txt

echo "==> Installing Playwright Chromium browser with dependencies..."
playwright install --with-deps chromium

echo "==> Build complete!"
