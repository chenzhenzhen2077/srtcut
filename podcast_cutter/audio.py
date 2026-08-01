"""Audio podcast analysis and export helpers."""

from pathlib import Path

from .media import normalize_cuts, probe_duration, write_progress


def analyze_audio_segments(segments, silence_threshold=1.5):
    """Turn transcript segments into explainable audio editing suggestions."""
    suggestions = []
    previous_end = None
    for segment in segments:
        gap = max(0.0, segment["start"] - previous_end) if previous_end is not None else 0.0
        text = segment.get("text", "")
        compact = text.replace(" ", "")
        if gap >= silence_threshold:
            cut_start = previous_end + 0.25
            cut_end = segment["start"] - 0.25
            if cut_end > cut_start + 0.1:
                suggestions.append(
                    {
                        "start": round(cut_start, 3),
                        "end": round(cut_end, 3),
                        "reason": f"缩短 {gap:.1f} 秒长停顿",
                    }
                )
        filler_count = sum(compact.count(word) for word in ("嗯", "啊", "呃", "就是", "然后", "那个", "其实"))
        if compact in {"嗯", "啊", "呃"} or filler_count >= 3:
            suggestions.append(
                {
                    "start": round(segment["start"], 3),
                    "end": round(segment["end"], 3),
                    "reason": "口癖较多",
                }
            )
        previous_end = segment["end"]
    return normalize_cuts(suggestions)


def build_audio_export_command(ffmpeg_path, input_path, output_path, cuts):
    """Create an MP3 command that keeps all non-marked audio ranges."""
    expression = "*".join(
        f'not(between(t,{cut["start"]:.6f},{cut["end"]:.6f}))' for cut in cuts
    ) or "1"
    return [
        ffmpeg_path,
        "-i",
        str(input_path),
        "-af",
        f"aselect='{expression}',asetpts=N/SR/TB",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-progress",
        "pipe:1",
        "-y",
        str(output_path),
    ]


def run_audio_export(ffmpeg_path, ffprobe_path, input_path, output_path, progress_path, cuts):
    """Export a cleaned podcast audio file in the background."""
    import subprocess

    input_path, output_path = Path(input_path), Path(output_path)
    try:
        duration = probe_duration(ffprobe_path, input_path)
        cuts = normalize_cuts(cuts, duration=duration)
        if not cuts:
            write_progress(progress_path, {"status": "error", "error": "没有有效的音频剪辑段"})
            return
        process = subprocess.Popen(
            build_audio_export_command(ffmpeg_path, input_path, output_path, cuts),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        write_progress(progress_path, {"status": "running", "progress": 5, "message": "正在导出音频…"})
        for line in iter(process.stdout.readline, ""):
            if line.strip() == "progress=end":
                write_progress(progress_path, {"status": "running", "progress": 99, "message": "正在完成文件…"})
        process.wait()
        if process.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            job_id = input_path.stem.removesuffix("_audio_input")
            write_progress(progress_path, {"status": "done", "progress": 100, "message": "音频导出完成", "download_url": f"/api/audio/download/{job_id}"})
        else:
            write_progress(progress_path, {"status": "error", "error": f"音频导出失败，返回码: {process.returncode}"})
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        write_progress(progress_path, {"status": "error", "error": str(exc)})
    finally:
        input_path.unlink(missing_ok=True)
