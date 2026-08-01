"""Persistent edit decisions and shared podcast audio/video exports."""

import json
import subprocess
from pathlib import Path

from .audio import build_audio_export_command
from .media import build_ffmpeg_command, normalize_cuts, probe_duration, write_progress

DECISION_VERSION = 1


def decision_path(work_dir, project_id):
    return Path(work_dir) / f"{project_id}_edit_decision.json"


def create_edit_decision(
    work_dir,
    project_id,
    source_path,
    source_kind,
    original_name,
    segments,
    suggestions,
):
    """Create the server-side record shared by every output for one podcast."""
    decision = {
        "version": DECISION_VERSION,
        "project_id": project_id,
        "source": {
            "kind": source_kind,
            "original_name": original_name,
            "stored_name": Path(source_path).name,
        },
        "segments": segments,
        "suggested_cuts": normalize_cuts(suggestions),
        "cuts": [],
        "selected_proposal": None,
        "outputs": {
            "audio": {"status": "not_requested", "download_url": None},
            "video": {"status": "not_requested", "download_url": None},
        },
    }
    save_edit_decision(work_dir, decision)
    return decision


def load_edit_decision(work_dir, project_id):
    path = decision_path(work_dir, project_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("project_id") == project_id else None


def save_edit_decision(work_dir, decision):
    write_progress(decision_path(work_dir, decision["project_id"]), decision)


def _output_snapshot(decision):
    return {
        name: {
            "status": value.get("status", "not_requested"),
            "download_url": value.get("download_url"),
            "error": value.get("error"),
        }
        for name, value in decision["outputs"].items()
    }


def _run_command(command):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for _line in iter(process.stdout.readline, ""):
        pass
    process.wait()
    return process.returncode


def run_podcast_exports(
    ffmpeg_path,
    ffprobe_path,
    work_dir,
    project_id,
    source_path,
    cuts,
    requested_outputs,
    quality="medium",
):
    """Render one or both outputs from exactly the same confirmed cut list."""
    work_dir = Path(work_dir)
    source_path = Path(source_path)
    progress_path = work_dir / f"{project_id}_podcast_progress.json"
    decision = load_edit_decision(work_dir, project_id)
    if decision is None:
        write_progress(progress_path, {"status": "error", "error": "剪辑项目不存在"})
        return

    try:
        duration = probe_duration(ffprobe_path, source_path)
        cuts = normalize_cuts(cuts, duration=duration)
        if not cuts:
            raise ValueError("没有有效的剪辑段")

        decision["cuts"] = cuts
        for output_name in requested_outputs:
            decision["outputs"][output_name] = {"status": "pending", "download_url": None}
        save_edit_decision(work_dir, decision)

        total = len(requested_outputs)
        for index, output_name in enumerate(requested_outputs):
            label = "音频" if output_name == "audio" else "视频"
            decision["outputs"][output_name]["status"] = "running"
            save_edit_decision(work_dir, decision)
            write_progress(
                progress_path,
                {
                    "status": "running",
                    "progress": int(index / total * 90) + 5,
                    "message": f"正在生成{label}…",
                    "outputs": _output_snapshot(decision),
                },
            )

            if output_name == "audio":
                output_path = work_dir / f"{project_id}_podcast_audio.mp3"
                command = build_audio_export_command(
                    ffmpeg_path, source_path, output_path, cuts
                )
                download_url = f"/api/podcast/download/audio/{project_id}"
            else:
                output_path = work_dir / f"{project_id}_podcast_video.mp4"
                command = build_ffmpeg_command(
                    ffmpeg_path, source_path, output_path, cuts, quality
                )
                download_url = f"/api/podcast/download/video/{project_id}"

            returncode = _run_command(command)
            if returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError(f"{label}生成失败，请检查原文件后重试")

            decision["outputs"][output_name] = {
                "status": "done",
                "download_url": download_url,
            }
            save_edit_decision(work_dir, decision)

        can_continue_video = (
            decision["source"]["kind"] == "video"
            and decision["outputs"]["video"]["status"] != "done"
        )
        write_progress(
            progress_path,
            {
                "status": "done",
                "progress": 100,
                "message": "播客剪辑完成",
                "outputs": _output_snapshot(decision),
                "can_continue_video": can_continue_video,
            },
        )
    except (OSError, TypeError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        for output_name in requested_outputs:
            if decision["outputs"][output_name].get("status") in {"pending", "running"}:
                decision["outputs"][output_name] = {
                    "status": "error",
                    "download_url": None,
                    "error": str(exc),
                }
        save_edit_decision(work_dir, decision)
        write_progress(
            progress_path,
            {
                "status": "error",
                "error": str(exc),
                "outputs": _output_snapshot(decision),
            },
        )
