"""HTTP routes for the local Podcast Cutter application."""

import json
import logging
import threading
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from .media import (
    binary_version,
    find_binary,
    install_ffmpeg_tools,
    normalize_cuts,
    run_ffmpeg_cut,
)


logger = logging.getLogger(__name__)
api = Blueprint("api", __name__)


def _paths(job_id):
    work_dir = Path(current_app.config["WORK_DIR"])
    return (
        work_dir / f"{job_id}_input.mp4",
        work_dir / f"{job_id}_output.mp4",
        work_dir / f"{job_id}_progress.json",
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
    except (json.JSONDecodeError, ValueError) as exc:
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

