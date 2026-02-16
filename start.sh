#!/bin/bash
set -e

echo "🔊 Starting PulseAudio daemon..."
pulseaudio --start --exit-idle-time=-1 --daemonize=yes
sleep 1

# Verify PulseAudio is running
if pactl info > /dev/null 2>&1; then
    echo "✅ PulseAudio is running"
else
    echo "❌ PulseAudio failed to start"
    exit 1
fi

echo "🖥️ Starting Xvfb virtual display..."
export DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 -ac &
XVFB_PID=$!
sleep 1

# Verify Xvfb is running
if kill -0 $XVFB_PID 2>/dev/null; then
    echo "✅ Xvfb is running on display :99"
else
    echo "❌ Xvfb failed to start"
    exit 1
fi

echo "🤖 Starting Discord bot..."
python bot.py
