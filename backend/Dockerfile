FROM python:3.11-slim

# Install system dependencies including FFmpeg

RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Pin setuptools<70 so pkg_resources remains a top-level module
# (openai-whisper setup.py imports pkg_resources which was broken in setuptools>=70)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "setuptools==68.2.2" wheel

WORKDIR /app

COPY requirements.txt .
# Install openai-whisper first (legacy build, needs pinned setuptools above)
RUN pip install --no-cache-dir openai-whisper==20231117
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p /app/output /app/cache

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
