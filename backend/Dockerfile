FROM python:3.11-slim

# Install system dependencies including FFmpeg

RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Fix: openai-whisper build needs pkg_resources (setuptools)

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app


COPY requirements.txt .
# openai-whisper uses legacy setup.py that needs pkg_resources;
# --no-build-isolation makes it use the already-installed setuptools
RUN pip install --no-cache-dir --no-build-isolation openai-whisper==20231117
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p /app/output /app/cache

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
