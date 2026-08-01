FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PODCAST_CUTTER_HOST=0.0.0.0 \
    PODCAST_CUTTER_PORT=8964 \
    PODCAST_CUTTER_WORK_DIR=/data/work \
    PODCAST_CUTTER_BIN_DIR=/usr/bin

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py README.md ./
COPY podcast_cutter ./podcast_cutter

RUN python -m pip install --upgrade pip \
    && python -m pip install '.[speech,prod]'

COPY app.py index.html ./

RUN mkdir -p /data/work

EXPOSE 8964

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8964} --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-4} --timeout ${WEB_TIMEOUT:-600}"]
