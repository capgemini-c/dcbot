#!/bin/bash
set -e

echo "🔧 Environment check..."
echo "  User: $(whoami)"
echo "  Chromium: $(which chromium 2>/dev/null || echo 'NOT FOUND')"
echo "  ChromeDriver: $(which chromedriver 2>/dev/null || echo 'NOT FOUND')"
echo "  FFmpeg: $(which ffmpeg 2>/dev/null || echo 'NOT FOUND')"
echo "  PulseAudio: $(which pulseaudio 2>/dev/null || echo 'NOT FOUND')"
echo "  Xvfb: $(which Xvfb 2>/dev/null || echo 'NOT FOUND')"

# ── Start D-Bus (required by PulseAudio in some containers) ──
echo "🔌 Starting D-Bus..."
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || echo "⚠️ D-Bus already running or not needed"

# ── Start PulseAudio ──
echo "🔊 Starting PulseAudio daemon..."

# Clean up stale PulseAudio state
rm -rf /tmp/pulseaudio.socket /tmp/pulse-* /root/.config/pulse/cookie 2>/dev/null

# Start PulseAudio with flags suitable for running as root in a container
pulseaudio \
    --start \
    --exit-idle-time=-1 \
    --daemonize=yes \
    --system=false \
    --disallow-exit \
    --log-level=error \
    || true

sleep 2

# Verify PulseAudio is running
if pactl info > /dev/null 2>&1; then
    echo "✅ PulseAudio is running"
    pactl info | head -5
else
    echo "⚠️ PulseAudio not responding, trying fallback start..."
    # Fallback: start without daemon mode, backgrounded
    pulseaudio --exit-idle-time=-1 --system=false --disallow-exit &
    sleep 2
    if pactl info > /dev/null 2>&1; then
        echo "✅ PulseAudio is running (fallback)"
    else
        echo "❌ PulseAudio failed to start!"
        echo "  Trying to get more info..."
        pulseaudio --check -v 2>&1 || true
        exit 1
    fi
fi

# ── Start Xvfb virtual display ──
echo "🖥️ Starting Xvfb virtual display..."
export DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 1

# Verify Xvfb is running
if kill -0 $XVFB_PID 2>/dev/null; then
    echo "✅ Xvfb is running on display :99 (PID: $XVFB_PID)"
else
    echo "❌ Xvfb failed to start"
    exit 1
fi

# ── Verify Chromium works ──
echo "🌐 Verifying Chromium..."
if chromium --version 2>/dev/null; then
    echo "✅ Chromium is available"
else
    echo "⚠️ Could not get Chromium version (may still work)"
fi

echo ""
echo "════════════════════════════════════════"
echo "  🤖 Starting Discord bot..."
echo "════════════════════════════════════════"
echo ""

exec python bot.py
