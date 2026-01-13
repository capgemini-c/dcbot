FROM python:3.12-slim

# Force unbuffered Python output (shows logs immediately)
ENV PYTHONUNBUFFERED=1

# Install FFmpeg, libopus, libsodium, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    libsodium23 \
    libsodium-dev \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install PyNaCl from source to ensure it links with system libsodium
RUN pip install --no-cache-dir --no-binary PyNaCl PyNaCl>=1.5.0
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
