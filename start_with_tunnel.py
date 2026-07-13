"""
start_with_tunnel.py
====================
Run this script to start the Streamlit app and expose it publicly via ngrok.

Usage:
    py start_with_tunnel.py

Steps:
1. Paste your ngrok authtoken when prompted (get it from https://dashboard.ngrok.com/get-started/your-authtoken)
2. The script will print your public URL
3. Share that URL with anyone — they can access the app from anywhere
"""

import subprocess
import sys
import time

# ── Step 1: Get authtoken ────────────────────────────────────────────────────
print("\n" + "="*60)
print("  TRANSIT PASS AUTOMATION — PUBLIC URL LAUNCHER")
print("="*60)
print("\n1. Go to: https://dashboard.ngrok.com/get-started/your-authtoken")
print("2. Copy your authtoken")
print()
token = input("Paste your ngrok authtoken here: ").strip()

if not token:
    print("❌ No token entered. Exiting.")
    sys.exit(1)

# ── Step 2: Configure ngrok ──────────────────────────────────────────────────
from pyngrok import ngrok, conf

print("\n⚙️  Configuring ngrok...")
conf.get_default().auth_token = token
ngrok.set_auth_token(token)

# ── Step 3: Start Streamlit in background ────────────────────────────────────
print("🚀 Starting Streamlit app on port 8501...")
streamlit_proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.port", "8501",
     "--server.headless", "true",
     "--browser.gatherUsageStats", "false"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

print("⏳ Waiting for Streamlit to start...")
time.sleep(4)

# ── Step 4: Open ngrok tunnel ────────────────────────────────────────────────
print("🌐 Opening public tunnel...")
tunnel = ngrok.connect(8501)

print("\n" + "="*60)
print("  ✅ YOUR APP IS LIVE!")
print("="*60)
print(f"\n  🔗 Public URL: {tunnel.public_url}")
print(f"\n  Share this link with anyone!")
print("\n  Press Ctrl+C to stop the app and close the tunnel.")
print("="*60 + "\n")

# ── Step 5: Keep running ─────────────────────────────────────────────────────
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n\n⏹️  Stopping...")
    ngrok.kill()
    streamlit_proc.terminate()
    print("✅ App stopped. Goodbye!")
