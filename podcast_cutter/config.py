"""Runtime configuration with environment overrides."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None:
        return default


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}
    try:
        return int(value)
    except ValueError:
        return default


class Config:
    HOST = os.environ.get("PODCAST_CUTTER_HOST", "127.0.0.1")
    PORT = _env_int("PODCAST_CUTTER_PORT", 8964)
    WORK_DIR = Path(os.environ.get("PODCAST_CUTTER_WORK_DIR", BASE_DIR / "work"))
    BIN_DIR = Path(os.environ.get("PODCAST_CUTTER_BIN_DIR", BASE_DIR / "bin"))
    # 2 GiB is generous for local use and prevents accidental disk exhaustion.
    MAX_CONTENT_LENGTH = _env_int("PODCAST_CUTTER_MAX_UPLOAD_MB", 2048) * 1024 * 1024
    MAX_CUTS = _env_int("PODCAST_CUTTER_MAX_CUTS", 2000)
    JOB_ID_LENGTH = 12
    INDEX_FILE = BASE_DIR / "index.html"
    WHISPER_MODEL = os.environ.get("PODCAST_CUTTER_WHISPER_MODEL", "small")
    WHISPER_MAX_DURATION_MINUTES = _env_int("PODCAST_CUTTER_WHISPER_MAX_DURATION_MINUTES", 180)
    AI_API_KEY = os.environ.get("PODCAST_CUTTER_AI_API_KEY", "")
    AI_BASE_URL = os.environ.get("PODCAST_CUTTER_AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL = os.environ.get("PODCAST_CUTTER_AI_MODEL", "gpt-4.1-mini")
    # auto prefers a configured cloud API and falls back to a local Ollama model.
    AI_PROVIDER = os.environ.get("PODCAST_CUTTER_AI_PROVIDER", "auto").strip().lower()
    AI_LOCAL_ENABLED = _env_bool("PODCAST_CUTTER_AI_LOCAL_ENABLED", True)
    AI_LOCAL_BASE_URL = os.environ.get("PODCAST_CUTTER_AI_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    AI_LOCAL_MODEL = os.environ.get("PODCAST_CUTTER_AI_LOCAL_MODEL", "qwen2.5:14b")
    AI_LOCAL_API_KEY = os.environ.get("PODCAST_CUTTER_AI_LOCAL_API_KEY", "ollama")
    AI_LOCAL_TIMEOUT = _env_int("PODCAST_CUTTER_AI_LOCAL_TIMEOUT", 1)
    AUDIO_MAX_DURATION_MINUTES = _env_int("PODCAST_CUTTER_AUDIO_MAX_DURATION_MINUTES", 240)
