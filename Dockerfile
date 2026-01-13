FROM python:3.12-slim

# Force unbuffered Python output (shows logs immediately)
ENV PYTHONUNBUFFERED=1

# Install FFmpeg and libopus (required for Discord voice)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
