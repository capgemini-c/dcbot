#!/bin/bash
set -e

echo "🔧 Environment check..."
echo "  User: $(whoami)"
echo "  Chromium: $(which chromium 2>/dev/null || echo 'NOT FOUND')"
echo "  ChromeDriver: $(which chromedriver 2>/dev/null || echo 'NOT FOUND')"
echo "  FFmpeg: $(which ffmpeg 2>/dev/null || echo 'NOT FOUND')"
echo "  PulseAudio: $(which pulseaudio 2>/dev/null || echo 'NOT FOUND')"
echo "  Xvfb: $(which Xvfb 2>/dev/null || echo 'NOT FOUND')"

# ── 1. Start Xvfb FIRST (PulseAudio/D-Bus may need DISPLAY) ──
echo "🖥️ Starting Xvfb virtual display..."
export DISPLAY=:99

# Clean up stale Xvfb lock files from previous runs
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 1

if kill -0 $XVFB_PID 2>/dev/null; then
    echo "✅ Xvfb is running on display :99 (PID: $XVFB_PID)"
else
    echo "❌ Xvfb failed to start"
    exit 1
fi

# ── 2. Start PulseAudio in system mode (works as root, no D-Bus needed) ──
echo "🔊 Starting PulseAudio daemon..."

# Clean up stale state
rm -rf /tmp/pulse-* /run/pulse/* 2>/dev/null || true
mkdir -p /var/run/pulse /var/lib/pulse

# Start in system mode — uses /etc/pulse/system.pa (configured in Dockerfile)
pulseaudio \
    --system \
    --disallow-exit \
    --disallow-module-loading=0 \
    --exit-idle-time=-1 \
    --daemonize=yes \
    --log-level=notice \
    2>&1 || true

sleep 2

# Verify PulseAudio is running
if pactl info > /dev/null 2>&1; then
    echo "✅ PulseAudio is running"
    pactl info 2>/dev/null | grep "Server Name" || true
else
    echo "⚠️ pactl can't connect, checking if process is alive..."
    if pgrep -x pulseaudio > /dev/null; then
        echo "✅ PulseAudio process is running (PID: $(pgrep -x pulseaudio))"
        # Set server path explicitly so pactl/clients can find it
        export PULSE_SERVER=unix:/var/run/pulse/native
        if pactl info > /dev/null 2>&1; then
            echo "✅ PulseAudio responding on $PULSE_SERVER"
        else
            echo "⚠️ PulseAudio running but pactl can't connect — audio may not work"
        fi
    else
        echo "❌ PulseAudio failed to start!"
        exit 1
    fi
fi

# ── 3. Verify Chromium works ──
echo "🌐 Verifying Chromium..."
chromium --version 2>/dev/null && echo "✅ Chromium is available" || echo "⚠️ Could not get Chromium version"

echo ""
echo "════════════════════════════════════════"
echo "  🤖 Starting Discord bot..."
echo "════════════════════════════════════════"
echo ""

exec python bot.py
