"""FFmpeg discovery, validation and background media processing."""

import io
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def find_binary(name, bin_dir, environ=None):
    """Find a bundled binary first, then a binary available on PATH."""
    bundled = Path(bin_dir) / name
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    path_value = (environ or os.environ).get("PATH", "")
    found = shutil.which(name, path=path_value)
    return found


def binary_version(binary):
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).splitlines()[0] if result.stdout or result.stderr else "unknown"


def normalize_cuts(raw_cuts, max_cuts=2000, duration=None):
    """Validate, sort and merge cut ranges before they reach FFmpeg."""
    if not isinstance(raw_cuts, list):
        raise TypeError("cuts 必须是数组")
    if len(raw_cuts) > max_cuts:
        raise ValueError(f"剪辑段数量不能超过 {max_cuts}")

    normalized = []
    for item in raw_cuts:
        if not isinstance(item, dict):
            raise TypeError("剪辑段格式无效")
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("剪辑段必须包含数字 start 和 end") from None
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("剪辑时间必须是有限数字")
        if start < 0 or end <= start + 0.1:
            continue
        if duration is not None:
            start = min(start, duration)
            end = min(end, duration)
        if end > start + 0.1:
            normalized.append({"start": start, "end": end, "reason": str(item.get("reason", ""))[:200]})

    normalized.sort(key=lambda cut: (cut["start"], cut["end"]))
    merged = []
    for cut in normalized:
        if merged and cut["start"] <= merged[-1]["end"] + 0.05:
            merged[-1]["end"] = max(merged[-1]["end"], cut["end"])
            if cut["reason"] and cut["reason"] not in merged[-1]["reason"]:
                merged[-1]["reason"] = "; ".join(filter(None, [merged[-1]["reason"], cut["reason"]]))[:200]
        else:
            merged.append(cut)
    return merged


@lru_cache(maxsize=8)
def encoder_available(ffmpeg_path, encoder):
    """Check an encoder once per process before selecting hardware acceleration."""
    try:
        result = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:r=1",
                "-frames:v",
                "1",
                "-c:v",
                encoder,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_ffmpeg_command(ffmpeg_path, input_path, output_path, cuts, quality, keep=None):
    """Build one filter chain for either deletion cuts or a selected keep range."""
    selectors = []
    if keep:
        selectors.append(f'between(t,{keep["start"]:.6f},{keep["end"]:.6f})')
    selectors.extend(f'not(between(t,{cut["start"]:.6f},{cut["end"]:.6f}))' for cut in cuts)
    expression = "*".join(selectors) or "1"
    video_filters = [f"select='{expression}'", "setpts=N/FRAME_RATE/TB"]
    if encoder_available(ffmpeg_path, "h264_videotoolbox"):
        video_options = {
            "high": ["-c:v", "h264_videotoolbox", "-b:v", "8000k"],
            "medium": ["-c:v", "h264_videotoolbox", "-b:v", "5000k"],
            "fast": ["-c:v", "h264_videotoolbox", "-b:v", "3000k"],
        }.get(quality, ["-c:v", "h264_videotoolbox", "-b:v", "5000k"])
    else:
        # Software fallback keeps the app usable on Linux, Windows and unsupported Macs.
        video_options = {
            "high": ["-c:v", "libx264", "-preset", "medium", "-crf", "18"],
            "medium": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"],
            "fast": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24"],
        }.get(quality, ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"])
    if quality == "fast":
        video_filters.append("scale=1280:-2")

    return [
        ffmpeg_path,
        "-i",
        str(input_path),
        "-vf",
        ",".join(video_filters),
        "-af",
        f"aselect='{expression}',asetpts=N/SR/TB",
        *video_options,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-progress",
        "pipe:1",
        "-y",
        str(output_path),
    ]


def probe_duration(ffprobe_path, input_path):
    result = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    duration = (result.stdout or "").strip()
    if not duration:
        raise ValueError(f"无法读取视频时长: {(result.stderr or '')[:200]}")
    return float(duration)


def write_progress(path, data):
    """Atomically publish progress so polling never sees partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def run_ffmpeg_cut(
    ffmpeg_path,
    ffprobe_path,
    input_path,
    output_path,
    progress_path,
    cuts,
    quality,
    keep=None,
    download_url=None,
):
    """Run a cut job, optionally keeping only one selected content range."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    progress_path = Path(progress_path)
    try:
        duration = probe_duration(ffprobe_path, input_path)
        cuts = normalize_cuts(cuts, duration=duration)
        if not cuts and not keep:
            write_progress(progress_path, {"status": "error", "error": "没有有效的剪辑段"})
            return
        if keep:
            keep = {
                "start": max(0.0, min(float(keep["start"]), duration)),
                "end": max(0.0, min(float(keep["end"]), duration)),
            }
            if keep["end"] <= keep["start"] + 0.1:
                raise ValueError("保留范围无效")

        command = build_ffmpeg_command(ffmpeg_path, input_path, output_path, cuts, quality, keep=keep)
        write_progress(progress_path, {"status": "running", "progress": 5, "message": "启动 FFmpeg…"})
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        cut_duration = sum(cut["end"] - cut["start"] for cut in cuts)
        base_duration = keep["end"] - keep["start"] if keep else duration
        estimated_output_duration = max(1.0, base_duration - cut_duration)
        started_at = time.time()
        last_progress = 5
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.strip()
            if line.startswith("out_time="):
                try:
                    hours, minutes, seconds = line.split("=", 1)[1].split(":")
                    rendered = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    last_progress = max(last_progress, min(95, int(rendered / estimated_output_duration * 100)))
                except (ValueError, IndexError):
                    pass
            elif line == "progress=end":
                last_progress = 99

            elapsed_progress = min(90, int((time.time() - started_at) / max(estimated_output_duration * 0.8, 1) * 100))
            last_progress = max(last_progress, elapsed_progress)
            write_progress(progress_path, {"status": "running", "progress": last_progress, "message": f"剪辑中… {last_progress}%"})

        process.wait()
        if process.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            job_id = input_path.stem.removesuffix("_input")
            write_progress(
                progress_path,
                {
                    "status": "done",
                    "progress": 100,
                    "message": "处理完成！",
                    "download_url": download_url or f"/api/download/{job_id}",
                },
            )
        else:
            write_progress(progress_path, {"status": "error", "error": f"FFmpeg 剪辑失败，返回码: {process.returncode}"})
    except Exception as exc:
        logger.exception("FFmpeg job failed")
        write_progress(progress_path, {"status": "error", "error": str(exc)})
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove input file: %s", input_path)


def install_ffmpeg_tools(bin_dir, version="7.1"):
    """Download both FFmpeg and FFprobe for the current local platform."""
    target_dir = Path(bin_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for tool in ("ffmpeg", "ffprobe"):
        url = f"https://evermeet.cx/ffmpeg/{tool}-{version}.zip"
        with urlopen(url, timeout=120) as response:
            archive = response.read()
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            member = next((name for name in zipped.namelist() if Path(name).name == tool), None)
            if not member:
                raise ValueError(f"安装包中缺少 {tool}")
            target = target_dir / tool
            temporary = target.with_suffix(".download")
            with zipped.open(member) as source, temporary.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            temporary.chmod(0o755)
            temporary.replace(target)
