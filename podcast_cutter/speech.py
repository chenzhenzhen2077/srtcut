"""Local speech-to-text transcription using the optional faster-whisper package."""

import logging
import os
import threading
import time
from pathlib import Path

from .media import write_progress

logger = logging.getLogger(__name__)
_models = {}
_models_lock = threading.Lock()


def _positive_int(value, default):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


_transcription_slots = threading.BoundedSemaphore(
    _positive_int(os.environ.get("PODCAST_CUTTER_TRANSCRIPTION_CONCURRENCY"), 1)
)


def faster_whisper_available():
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model(model_name):
    """Load one model per process; loading is intentionally lazy."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "未安装 faster-whisper。请运行: python -m pip install -e '.[speech]'"
        ) from exc

    with _models_lock:
        if model_name not in _models:
            device = os.environ.get("PODCAST_CUTTER_WHISPER_DEVICE", "cpu")
            compute_type = os.environ.get("PODCAST_CUTTER_WHISPER_COMPUTE_TYPE", "int8")
            logger.info("Loading Whisper model %s on %s (%s)", model_name, device, compute_type)
            _models[model_name] = WhisperModel(model_name, device=device, compute_type=compute_type)
        return _models[model_name]


def format_srt_timestamp(seconds):
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def transcribe_to_srt(
    input_path,
    output_path,
    progress_path,
    job_id,
    model_name="small",
    language=None,
    cleanup_input=True,
):
    """Transcribe a media file and write standard SRT output."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    progress_path = Path(progress_path)
    slot_acquired = False
    try:
        write_progress(progress_path, {"status": "queued", "progress": 2, "message": "等待本机字幕任务…"})
        _transcription_slots.acquire()
        slot_acquired = True
        write_progress(progress_path, {"status": "loading", "progress": 5, "message": "加载语音模型…"})
        model = _get_model(model_name)
        write_progress(progress_path, {"status": "running", "progress": 10, "message": "开始识别语音…"})
        segments, info = model.transcribe(
            str(input_path),
            language=language or None,
            vad_filter=True,
            beam_size=5,
        )

        rows = []
        last_progress_write = 0.0
        for index, segment in enumerate(segments, start=1):
            text = (segment.text or "").strip()
            if not text:
                continue
            rows.append(
                "\n".join(
                    [
                        str(len(rows) + 1),
                        f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}",
                        text,
                    ]
                )
            )
            # faster-whisper does not expose total segment count, so provide a useful bounded status.
            progress = min(95, 10 + index // 2)
            now = time.monotonic()
            if now - last_progress_write >= 1.0:
                write_progress(
                    progress_path,
                    {
                        "status": "running",
                        "progress": progress,
                        "message": f"识别中… 已生成 {len(rows)} 段",
                    },
                    sync=False,
                )
                last_progress_write = now

        output_path.write_text("\n\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        detected_language = getattr(info, "language", None)
        write_progress(
            progress_path,
            {
                "status": "done",
                "progress": 100,
                "message": f"字幕生成完成，共 {len(rows)} 段",
                "segment_count": len(rows),
                "language": detected_language,
                "srt_url": f"/api/transcribe/{job_id}/srt",
            },
        )
    except Exception as exc:
        logger.exception("Transcription job failed")
        write_progress(progress_path, {"status": "error", "error": str(exc)})
    finally:
        if slot_acquired:
            _transcription_slots.release()
        if cleanup_input:
            try:
                input_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to remove transcription input: %s", input_path)
