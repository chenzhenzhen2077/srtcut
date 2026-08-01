"""HTTP routes for the local Podcast Cutter application."""

import json
import logging
import threading
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from .ai import generate_ai_proposals
from .audio import analyze_audio_segments, run_audio_export
from .media import (
    binary_version,
    find_binary,
    install_ffmpeg_tools,
    normalize_cuts,
    run_ffmpeg_cut,
    write_progress,
)
from .project import create_edit_decision, load_edit_decision, run_podcast_exports
from .smart import parse_srt
from .speech import faster_whisper_available, transcribe_to_srt

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__)


def _paths(job_id):
    work_dir = Path(current_app.config["WORK_DIR"])
    return (
        work_dir / f"{job_id}_input.mp4",
        work_dir / f"{job_id}_output.mp4",
        work_dir / f"{job_id}_progress.json",
    )


def _transcription_paths(job_id, extension):
    work_dir = Path(current_app.config["WORK_DIR"])
    return (
        work_dir / f"{job_id}_transcribe_input{extension}",
        work_dir / f"{job_id}_transcript.srt",
        work_dir / f"{job_id}_transcribe_progress.json",
    )


def _smart_paths(project_id, extension=".mp4"):
    work_dir = Path(current_app.config["WORK_DIR"])
    return work_dir / f"{project_id}_smart_input{extension}", work_dir / f"{project_id}_smart_output.mp4"


def _find_smart_input(project_id):
    work_dir = Path(current_app.config["WORK_DIR"])
    allowed = (".mp4", ".mov", ".mkv", ".avi", ".webm")
    return next((work_dir / f"{project_id}_smart_input{suffix}" for suffix in allowed if (work_dir / f"{project_id}_smart_input{suffix}").is_file()), None)


def _audio_paths(job_id, extension=".mp3"):
    work_dir = Path(current_app.config["WORK_DIR"])
    return (
        work_dir / f"{job_id}_audio_input{extension}",
        work_dir / f"{job_id}_audio_output.mp3",
        work_dir / f"{job_id}_audio_progress.json",
    )


def _podcast_input_path(project_id, extension):
    return Path(current_app.config["WORK_DIR"]) / f"{project_id}_podcast_input{extension}"


def _find_podcast_input(project_id):
    decision = load_edit_decision(current_app.config["WORK_DIR"], project_id)
    if decision is None:
        return None, None
    source_path = Path(current_app.config["WORK_DIR"]) / decision["source"]["stored_name"]
    return decision, source_path if source_path.is_file() else None


def _find_raw_podcast_input(project_id):
    work_dir = Path(current_app.config["WORK_DIR"])
    allowed = (
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
    )
    return next(
        (
            work_dir / f"{project_id}_podcast_input{suffix}"
            for suffix in allowed
            if (work_dir / f"{project_id}_podcast_input{suffix}").is_file()
        ),
        None,
    )


def _is_valid_job_id(job_id):
    return len(job_id) == current_app.config["JOB_ID_LENGTH"] and all(
        char in "0123456789abcdef" for char in job_id
    )


def _find_tools():
    bin_dir = current_app.config["BIN_DIR"]
    return find_binary("ffmpeg", bin_dir), find_binary("ffprobe", bin_dir)


@api.get("/")
def index():
    return send_file(current_app.config["INDEX_FILE"])


@api.get("/health")
def health():
    ffmpeg, ffprobe = _find_tools()
    return jsonify(
        {
            "status": "ok",
            "ffmpeg": {"available": bool(ffmpeg), "version": binary_version(ffmpeg)},
            "ffprobe": {"available": bool(ffprobe), "version": binary_version(ffprobe)},
        }
    )


@api.get("/api/check-ffmpeg")
def check_ffmpeg():
    ffmpeg, ffprobe = _find_tools()
    available = bool(ffmpeg and ffprobe)
    return jsonify(
        {
            "available": available,
            "ffmpeg_available": bool(ffmpeg),
            "ffprobe_available": bool(ffprobe),
            "version": binary_version(ffmpeg),
            "path": ffmpeg,
            "error": None if available else "FFmpeg 和 FFprobe 均需要安装",
        }
    )


@api.get("/api/check-transcription")
def check_transcription():
    return jsonify(
        {
            "available": faster_whisper_available(),
            "model": current_app.config["WHISPER_MODEL"],
            "install_hint": "python -m pip install -e '.[speech]'",
        }
    )


@api.get("/api/check-ai")
def check_ai():
    available = bool(current_app.config["AI_API_KEY"])
    return jsonify(
        {
            "available": available,
            "model": current_app.config["AI_MODEL"] if available else None,
            "message": "智能内容分析已开通" if available else "智能内容分析服务尚未配置",
        }
    )


@api.post("/api/install-ffmpeg")
def install_ffmpeg():
    try:
        install_ffmpeg_tools(current_app.config["BIN_DIR"])
        ffmpeg, ffprobe = _find_tools()
        if not ffmpeg or not ffprobe:
            raise RuntimeError("安装完成后仍无法找到 FFmpeg 或 FFprobe")
        return jsonify({"success": True, "version": binary_version(ffmpeg)})
    except Exception as exc:
        logger.exception("FFmpeg installation failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@api.post("/api/cut")
def cut_video():
    ffmpeg, ffprobe = _find_tools()
    if not ffmpeg or not ffprobe:
        return jsonify({"error": "FFmpeg 和 FFprobe 均需要安装，请先安装"}), 400
    if "video" not in request.files:
        return jsonify({"error": "请上传视频文件"}), 400

    try:
        raw_cuts = json.loads(request.form.get("cuts", "[]"))
        cuts = normalize_cuts(raw_cuts, max_cuts=current_app.config["MAX_CUTS"])
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if not cuts:
        return jsonify({"error": "没有有效的剪辑段"}), 400

    quality = request.form.get("quality", "high")
    if quality not in {"high", "medium", "fast"}:
        return jsonify({"error": "画质参数无效"}), 400

    job_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    input_path, output_path, progress_path = _paths(job_id)
    request.files["video"].save(input_path)
    worker = threading.Thread(
        target=run_ffmpeg_cut,
        args=(ffmpeg, ffprobe, input_path, output_path, progress_path, cuts, quality),
        daemon=True,
        name=f"cut-{job_id}",
    )
    worker.start()
    return jsonify({"job_id": job_id})


@api.post("/api/transcribe")
def transcribe_video():
    if not faster_whisper_available():
        return jsonify({"error": "未安装 faster-whisper，请先安装语音识别依赖"}), 503
    if "media" not in request.files:
        return jsonify({"error": "请上传视频或音频文件"}), 400

    media = request.files["media"]
    original_name = Path(media.filename or "media").name
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    if extension not in allowed_extensions:
        return jsonify({"error": "不支持的媒体格式"}), 400
    model_name = request.form.get("model", current_app.config["WHISPER_MODEL"])
    allowed_models = {"tiny", "base", "small", "medium", "large-v3", "distil-large-v3"}
    if model_name not in allowed_models:
        return jsonify({"error": "识别模型无效"}), 400
    language = request.form.get("language", "").strip() or None

    job_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    input_path, output_path, progress_path = _transcription_paths(job_id, extension)
    media.save(input_path)
    worker = threading.Thread(
        target=transcribe_to_srt,
        args=(input_path, output_path, progress_path, job_id, model_name, language),
        daemon=True,
        name=f"transcribe-{job_id}",
    )
    worker.start()
    return jsonify({"job_id": job_id})


@api.get("/api/transcribe/<job_id>/progress")
def get_transcription_progress(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    _input, _output, progress_path = _transcription_paths(job_id, ".mp4")
    if progress_path.is_file():
        try:
            return jsonify(json.loads(progress_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return jsonify({"status": "running", "progress": 0})
    return jsonify({"status": "pending", "progress": 0})


@api.get("/api/transcribe/<job_id>/srt")
def download_transcript(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    output_path = Path(current_app.config["WORK_DIR"]) / f"{job_id}_transcript.srt"
    if output_path.is_file():
        return send_file(str(output_path), as_attachment=True, download_name="自动生成字幕.srt")
    return jsonify({"error": "字幕未就绪"}), 404


@api.post("/api/media/start")
def start_media_project():
    if not faster_whisper_available():
        return jsonify({"error": "本地字幕功能尚未安装"}), 503
    if "media" not in request.files:
        return jsonify({"error": "请上传音频或视频文件"}), 400

    media = request.files["media"]
    original_name = Path(media.filename or "media").name
    extension = Path(original_name).suffix.lower()
    audio_extensions = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    video_extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    if extension not in audio_extensions | video_extensions:
        return jsonify({"error": "不支持的素材格式"}), 400
    model_name = request.form.get("model", current_app.config["WHISPER_MODEL"])
    if model_name not in {"tiny", "base", "small", "medium", "large-v3", "distil-large-v3"}:
        return jsonify({"error": "字幕识别质量参数无效"}), 400
    language = request.form.get("language", "").strip() or None

    project_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    source_path = _podcast_input_path(project_id, extension)
    output_path = Path(current_app.config["WORK_DIR"]) / f"{project_id}_transcript.srt"
    progress_path = Path(current_app.config["WORK_DIR"]) / f"{project_id}_transcribe_progress.json"
    metadata_path = Path(current_app.config["WORK_DIR"]) / f"{project_id}_media.json"
    media.save(source_path)
    source_kind = "video" if extension in video_extensions else "audio"
    write_progress(
        metadata_path,
        {
            "project_id": project_id,
            "original_name": original_name,
            "source_kind": source_kind,
            "stored_name": source_path.name,
        },
    )
    worker = threading.Thread(
        target=transcribe_to_srt,
        args=(source_path, output_path, progress_path, project_id, model_name, language, False),
        daemon=True,
        name=f"media-transcribe-{project_id}",
    )
    worker.start()
    return jsonify({"project_id": project_id, "job_id": project_id, "source_kind": source_kind})


@api.post("/api/media/<project_id>/prepare")
def prepare_media_project(project_id):
    if not _is_valid_job_id(project_id):
        return jsonify({"error": "项目 ID 无效"}), 400
    work_dir = Path(current_app.config["WORK_DIR"])
    source_path = _find_raw_podcast_input(project_id)
    transcript_path = work_dir / f"{project_id}_transcript.srt"
    metadata_path = work_dir / f"{project_id}_media.json"
    if source_path is None or not transcript_path.is_file() or not metadata_path.is_file():
        return jsonify({"error": "字幕尚未生成完成"}), 409
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        transcript = transcript_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        return jsonify({"error": "素材项目信息损坏"}), 500
    segments = parse_srt(transcript)
    if not segments:
        return jsonify({"error": "没有识别到可用字幕"}), 400
    suggestions = analyze_audio_segments(segments)
    decision = create_edit_decision(
        work_dir,
        project_id,
        source_path,
        metadata["source_kind"],
        metadata["original_name"],
        segments,
        suggestions,
    )
    return jsonify(
        {
            "project_id": project_id,
            "source_kind": decision["source"]["kind"],
            "segments": segments,
            "suggestions": suggestions,
            "transcript": transcript,
            "ai_available": bool(current_app.config["AI_API_KEY"]),
        }
    )


@api.post("/api/audio/analyze")
def analyze_audio():
    if "audio" not in request.files:
        return jsonify({"error": "请上传音频文件"}), 400
    try:
        segments = json.loads(request.form.get("segments", "[]"))
        threshold = float(request.form.get("silence_threshold", "1.5"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return jsonify({"error": "音频分析参数无效"}), 400
    if not isinstance(segments, list) or not segments:
        return jsonify({"error": "请先生成或导入音频字幕"}), 400
    media = request.files["audio"]
    extension = Path(media.filename or ".mp3").suffix.lower() or ".mp3"
    if extension not in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}:
        return jsonify({"error": "不支持的音频格式"}), 400
    job_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    input_path, _output_path, _progress_path = _audio_paths(job_id, extension)
    media.save(input_path)
    suggestions = analyze_audio_segments(segments, threshold)
    return jsonify({"job_id": job_id, "suggestions": suggestions, "suggestion_count": len(suggestions)})


@api.post("/api/audio/render")
def render_audio():
    try:
        payload = request.get_json(force=True)
        job_id = payload["job_id"]
        cuts = normalize_cuts(payload.get("cuts", []), max_cuts=current_app.config["MAX_CUTS"])
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return jsonify({"error": "音频剪辑参数无效"}), 400
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    work_dir = Path(current_app.config["WORK_DIR"])
    input_path = next((work_dir / f"{job_id}_audio_input{suffix}" for suffix in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg") if (work_dir / f"{job_id}_audio_input{suffix}").is_file()), None)
    if input_path is None:
        return jsonify({"error": "音频项目已过期"}), 404
    ffmpeg, ffprobe = _find_tools()
    if not ffmpeg or not ffprobe:
        return jsonify({"error": "音频处理功能不可用"}), 400
    output_path = work_dir / f"{job_id}_audio_output.mp3"
    progress_path = work_dir / f"{job_id}_audio_progress.json"
    worker = threading.Thread(target=run_audio_export, args=(ffmpeg, ffprobe, input_path, output_path, progress_path, cuts), daemon=True, name=f"audio-{job_id}")
    worker.start()
    return jsonify({"job_id": job_id})


@api.get("/api/audio/progress/<job_id>")
def audio_progress(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    progress_path = Path(current_app.config["WORK_DIR"]) / f"{job_id}_audio_progress.json"
    if progress_path.is_file():
        return jsonify(json.loads(progress_path.read_text(encoding="utf-8")))
    return jsonify({"status": "pending", "progress": 0})


@api.get("/api/audio/download/<job_id>")
def audio_download(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    output_path = Path(current_app.config["WORK_DIR"]) / f"{job_id}_audio_output.mp3"
    if output_path.is_file():
        return send_file(str(output_path), as_attachment=True, download_name="剪辑后播客.mp3")
    return jsonify({"error": "音频未就绪"}), 404


@api.post("/api/podcast/analyze")
def analyze_podcast():
    media = request.files.get("media") or request.files.get("audio")
    if media is None:
        return jsonify({"error": "请上传播客音频或视频"}), 400
    try:
        segments = json.loads(request.form.get("segments", "[]"))
        threshold = float(request.form.get("silence_threshold", "1.5"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return jsonify({"error": "播客分析参数无效"}), 400
    if not isinstance(segments, list) or not segments:
        return jsonify({"error": "请先生成播客字幕"}), 400

    original_name = Path(media.filename or "podcast.mp3").name
    extension = Path(original_name).suffix.lower()
    audio_extensions = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    video_extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    if extension not in audio_extensions | video_extensions:
        return jsonify({"error": "不支持的播客文件格式"}), 400

    project_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    source_path = _podcast_input_path(project_id, extension)
    media.save(source_path)
    suggestions = analyze_audio_segments(segments, threshold)
    source_kind = "video" if extension in video_extensions else "audio"
    create_edit_decision(
        current_app.config["WORK_DIR"],
        project_id,
        source_path,
        source_kind,
        original_name,
        segments,
        suggestions,
    )
    return jsonify(
        {
            "project_id": project_id,
            "job_id": project_id,
            "source_kind": source_kind,
            "can_export_video": source_kind == "video",
            "suggestions": suggestions,
            "suggestion_count": len(suggestions),
        }
    )


@api.post("/api/podcast/render")
def render_podcast():
    try:
        payload = request.get_json(force=True)
        project_id = payload["project_id"]
        cuts = normalize_cuts(
            payload.get("cuts", []), max_cuts=current_app.config["MAX_CUTS"]
        )
        outputs = payload.get("outputs", ["audio"])
        quality = payload.get("quality", "medium")
        allow_unchanged = payload.get("allow_unchanged") is True
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return jsonify({"error": "播客导出参数无效"}), 400
    if not _is_valid_job_id(project_id):
        return jsonify({"error": "项目 ID 无效"}), 400
    if not cuts and not allow_unchanged:
        return jsonify({"error": "请至少选择一处需要删除的片段"}), 400
    if not isinstance(outputs, list) or not outputs or any(
        output not in {"audio", "video"} for output in outputs
    ):
        return jsonify({"error": "请选择要生成的文件"}), 400
    outputs = list(dict.fromkeys(outputs))
    if quality not in {"high", "medium", "fast"}:
        return jsonify({"error": "输出质量参数无效"}), 400

    decision, source_path = _find_podcast_input(project_id)
    if decision is None or source_path is None:
        return jsonify({"error": "播客项目已过期"}), 404
    if "video" in outputs and decision["source"]["kind"] != "video":
        return jsonify({"error": "只上传了音频，无法生成视频"}), 400
    ffmpeg, ffprobe = _find_tools()
    if not ffmpeg or not ffprobe:
        return jsonify({"error": "音视频处理功能不可用"}), 400

    work_dir = Path(current_app.config["WORK_DIR"])
    progress_path = work_dir / f"{project_id}_podcast_progress.json"
    progress_path.unlink(missing_ok=True)
    worker = threading.Thread(
        target=run_podcast_exports,
        args=(
            ffmpeg,
            ffprobe,
            work_dir,
            project_id,
            source_path,
            cuts,
            outputs,
            quality,
        ),
        daemon=True,
        name=f"podcast-render-{project_id}",
    )
    worker.start()
    return jsonify({"project_id": project_id, "outputs": outputs})


@api.get("/api/podcast/progress/<project_id>")
def podcast_progress(project_id):
    if not _is_valid_job_id(project_id):
        return jsonify({"error": "项目 ID 无效"}), 400
    progress_path = (
        Path(current_app.config["WORK_DIR"]) / f"{project_id}_podcast_progress.json"
    )
    if progress_path.is_file():
        try:
            return jsonify(json.loads(progress_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return jsonify({"status": "running", "progress": 0})
    return jsonify({"status": "pending", "progress": 0})


@api.get("/api/podcast/project/<project_id>")
def podcast_project(project_id):
    if not _is_valid_job_id(project_id):
        return jsonify({"error": "项目 ID 无效"}), 400
    decision = load_edit_decision(current_app.config["WORK_DIR"], project_id)
    if decision is None:
        return jsonify({"error": "播客项目不存在"}), 404
    return jsonify(decision)


@api.get("/api/podcast/download/<output_name>/<project_id>")
def podcast_download(output_name, project_id):
    if not _is_valid_job_id(project_id) or output_name not in {"audio", "video"}:
        return jsonify({"error": "下载参数无效"}), 400
    suffix = ".mp3" if output_name == "audio" else ".mp4"
    output_path = (
        Path(current_app.config["WORK_DIR"])
        / f"{project_id}_podcast_{output_name}{suffix}"
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        return jsonify({"error": "文件尚未生成"}), 404
    download_name = "剪辑后播客.mp3" if output_name == "audio" else "同步剪辑视频.mp4"
    return send_file(str(output_path), as_attachment=True, download_name=download_name)


@api.post("/api/smart/analyze")
def smart_analyze():
    if not current_app.config["AI_API_KEY"]:
        return (
            jsonify(
                {
                    "error": "智能内容分析服务尚未配置，请使用精简剪辑",
                    "code": "ai_unavailable",
                }
            ),
            503,
        )
    try:
        payload = request.get_json(force=True)
        project_id = payload["project_id"]
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return jsonify({"error": "智能分析项目参数无效"}), 400
    if not _is_valid_job_id(project_id):
        return jsonify({"error": "项目 ID 无效"}), 400
    decision = load_edit_decision(current_app.config["WORK_DIR"], project_id)
    if decision is None:
        return jsonify({"error": "请先完成素材上传和字幕生成"}), 404
    segments = decision.get("segments", [])
    if len(segments) < 2:
        return jsonify({"error": "字幕内容太少，无法生成智能方案"}), 400
    try:
        understanding, proposals = generate_ai_proposals(
            segments,
            current_app.config["AI_API_KEY"],
            current_app.config["AI_BASE_URL"],
            current_app.config["AI_MODEL"],
        )
    except Exception:
        logger.exception("Semantic proposal generation failed")
        return jsonify({"error": "智能内容分析失败，请稍后重试或进入精简剪辑"}), 502
    return jsonify(
        {
            "project_id": project_id,
            "proposals": proposals,
            "understanding": understanding,
            "segment_count": len(segments),
            "generation_mode": "ai",
        }
    )


@api.post("/api/smart/render")
def smart_render():
    try:
        payload = request.get_json(force=True)
        project_id = payload["project_id"]
        proposal = payload["proposal"]
    except (TypeError, KeyError, ValueError):
        return jsonify({"error": "方案参数无效"}), 400
    if not _is_valid_job_id(project_id) or not isinstance(proposal, dict):
        return jsonify({"error": "方案参数无效"}), 400
    input_path = _find_smart_input(project_id)
    if input_path is None:
        return jsonify({"error": "智能剪辑项目已过期"}), 404
    ffmpeg, ffprobe = _find_tools()
    if not ffmpeg or not ffprobe:
        return jsonify({"error": "FFmpeg 和 FFprobe 均需要安装"}), 400
    try:
        keep = {"start": float(proposal["start"]), "end": float(proposal["end"])}
        cuts = normalize_cuts(proposal.get("cuts", []), max_cuts=current_app.config["MAX_CUTS"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "方案时间范围无效"}), 400
    job_id = uuid.uuid4().hex[: current_app.config["JOB_ID_LENGTH"]]
    _input, output_path, progress_path = _paths(job_id)
    worker = threading.Thread(
        target=run_ffmpeg_cut,
        args=(ffmpeg, ffprobe, input_path, output_path, progress_path, cuts, "medium"),
        kwargs={"keep": keep, "download_url": f"/api/download/{job_id}"},
        daemon=True,
        name=f"smart-render-{job_id}",
    )
    worker.start()
    return jsonify({"job_id": job_id})


@api.get("/api/progress/<job_id>")
def get_progress(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    _input, _output, progress_path = _paths(job_id)
    if progress_path.is_file():
        try:
            return jsonify(json.loads(progress_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return jsonify({"status": "running", "progress": 0})
    return jsonify({"status": "pending", "progress": 0})


@api.get("/api/download/<job_id>")
def download(job_id):
    if not _is_valid_job_id(job_id):
        return jsonify({"error": "任务 ID 无效"}), 400
    _input, output_path, _progress = _paths(job_id)
    if output_path.is_file() and output_path.stat().st_size > 0:
        return send_file(str(output_path), as_attachment=True, download_name="剪好_去口癖.mp4")
    return jsonify({"error": "文件未就绪"}), 404
