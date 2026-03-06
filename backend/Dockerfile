FROM python:3.11-slim

# Install system dependencies including FFmpeg
# This layer rarely changes, so it's cached efficiently
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Pin setuptools<70 so pkg_resources remains a top-level module
# (openai-whisper setup.py imports pkg_resources which was broken in setuptools>=70)
# This is also cached since it rarely changes
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "setuptools==68.2.2" wheel

WORKDIR /app

# Copy ONLY requirements.txt first (not the entire codebase)
# This way, dependencies are cached and only reinstalled when requirements.txt changes
COPY requirements.txt .

# Install Python dependencies
# openai-whisper setup.py imports pkg_resources which is missing in setuptools>=70.
# --no-build-isolation forces pip to use the system env (with setuptools==68.2.2)
# instead of creating an isolated build env that re-installs the latest setuptools.
RUN pip install --no-cache-dir --no-build-isolation openai-whisper==20231117 && \
    pip install --no-cache-dir -r requirements.txt

# Create necessary directories before copying code
RUN mkdir -p /app/output /app/cache

# Copy application code LAST
# This means code changes don't invalidate the dependency cache above
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
