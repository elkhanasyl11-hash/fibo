# Fibo backend: FastAPI + ML. Build from backend/:  docker build -t fibo-backend .
# Optional: --build-arg PRELOAD_EMBEDDINGS=true downloads the e5 model (≈135 MB) into the image,
# so manual search works offline from the first start.
FROM python:3.11-slim

# ffmpeg: Telegram voice (OGG/Opus) and m4a -> WAV; libsndfile1: soundfile; libgomp1: OpenMP for
# xgboost / scikit-learn; libglib2.0-0: needed by opencv-python-headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIBO_DATA_DIR=/app/data \
    FIBO_DATABASE_URL=sqlite+aiosqlite:////app/data/sqlite/fibo.db \
    FIBO_RISK_MODEL_DIR=/app/ml/artifacts \
    FIBO_MODEL_CACHE_DIR=/app/model-cache

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user (uid 1000 matches the usual first user on Linux hosts, so ./data stays writable).
ARG UID=1000
RUN useradd --create-home --uid ${UID} fibo && mkdir -p /app/data /app/model-cache && chown -R fibo /app
COPY --chown=fibo . .
USER fibo

ARG PRELOAD_EMBEDDINGS=false
RUN if [ "$PRELOAD_EMBEDDINGS" = "true" ]; then python -m app.modules.assistant.embeddings; fi

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
