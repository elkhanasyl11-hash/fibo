# Fibo AI service (sidecar). Build from ai/:  docker build -t fibo-ai .   — NOT verified: no Docker on the team
# laptop, and the service needs its configs/ folder (levels, audio thresholds, safety keywords, ...) which was
# not in fibo_ai.zip (decision D82). Optional heavy models: --build-arg WITH_ML=true (faster-whisper, e5).
FROM python:3.11-slim

# ffmpeg/ffprobe: audio decoding and photo probing; tesseract (eng+rus): OCR cross-check of panel photos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-rus libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIBO_DATA_DIR=/data/ai \
    FIBO_SHARED_DIR=/app/data/media \
    FIBO_PORT=8001

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt
ARG WITH_ML=false
RUN if [ "$WITH_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

ARG UID=1000
RUN useradd --create-home --uid ${UID} fibo && mkdir -p /data/ai && chown -R fibo /app /data/ai
COPY --chown=fibo . .
USER fibo
EXPOSE 8001
CMD ["uvicorn", "fibo_ai.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
