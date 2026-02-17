FROM python:3.12-slim

# Force unbuffered Python output (shows logs immediately)
ENV PYTHONUNBUFFERED=1

# Install FFmpeg, libopus, libsodium, build tools, Chromium, PulseAudio, Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    libsodium23 \
    libsodium-dev \
    build-essential \
    libffi-dev \
    curl \
    unzip \
    chromium \
    chromium-driver \
    pulseaudio \
    pulseaudio-utils \
    dbus \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Configure PulseAudio for running as root in a container
# 1. Allow PulseAudio to run as root in system mode
RUN mkdir -p /var/run/pulse /var/lib/pulse /root/.config/pulse && \
    echo "autospawn = no" > /root/.config/pulse/client.conf && \
    echo "daemon-binary = /usr/bin/pulseaudio" >> /root/.config/pulse/client.conf

# 2. Create a minimal system-mode PulseAudio config (no D-Bus needed)
RUN echo "load-module module-native-protocol-unix auth-anonymous=1" > /etc/pulse/system.pa && \
    echo "load-module module-null-sink" >> /etc/pulse/system.pa && \
    echo "load-module module-always-sink" >> /etc/pulse/system.pa && \
    echo "load-module module-rescue-streams" >> /etc/pulse/system.pa

# Set Chromium environment so Selenium can find it
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .

# Install PyNaCl from source to ensure it links with system libsodium
RUN pip install --no-cache-dir --no-binary PyNaCl PyNaCl>=1.5.0
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure start.sh is executable
RUN chmod +x start.sh

CMD ["bash", "start.sh"]
