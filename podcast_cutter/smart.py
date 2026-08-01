"""Heuristics for the first smart-editing workflow."""

import re
from math import ceil

TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)
FILLERS = ("嗯", "啊", "呃", "就是", "然后", "那个", "这个", "对吧", "是吧", "其实", "所以说")


def summarize_content(segments):
    """Provide a transparent local understanding when no semantic provider is configured."""
    if not segments:
        return {"topic": "暂时无法判断主题", "summary": "字幕内容不足，无法形成内容概览。", "audience": "暂时无法判断"}
    text = " ".join(segment["text"] for segment in segments)
    preview = text[:150]
    return {
        "topic": "这是一段以访谈/口述为主的内容",
        "summary": f"内容从“{preview}”开始，共 {len(segments)} 个字幕片段，建议先从观点完整、上下文较少的片段中选择。",
        "audience": "适合希望快速了解核心观点的观众",
    }


def parse_srt(text):
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((index for index, line in enumerate(lines) if TIMESTAMP_RE.search(line)), None)
        match = TIMESTAMP_RE.search(lines[time_index]) if time_index is not None else None
        if not match:
            continue
        start = timestamp_to_seconds(match.group("start"))
        end = timestamp_to_seconds(match.group("end"))
        text_lines = lines[time_index + 1 :]
        caption = " ".join(text_lines).strip()
        if caption and end > start:
            segments.append({"start": start, "end": end, "text": caption})
    return segments


def timestamp_to_seconds(value):
    hours, minutes, seconds, millis = re.split(r"[:,.]", value)
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _window(segments, start_index, end_index, title, hook, reason):
    selected = segments[start_index:end_index]
    cuts = []
    for segment in selected:
        compact = re.sub(r"[\s，。！？、,.!?]", "", segment["text"])
        filler_count = sum(compact.count(word) for word in FILLERS)
        if compact in FILLERS or filler_count >= 3:
            cuts.append({"start": segment["start"], "end": segment["end"], "reason": "自动识别口癖"})
    return {
        "id": f"proposal-{start_index + 1}",
        "title": title,
        "hook": hook,
        "summary": " ".join(item["text"] for item in selected)[:180],
        "start": round(selected[0]["start"], 3),
        "end": round(selected[-1]["end"], 3),
        "duration": round(selected[-1]["end"] - selected[0]["start"], 3),
        "reason": reason,
        "confidence": 0.62,
        "cuts": cuts,
    }


def generate_proposals(segments, max_proposals=3):
    """Create deterministic candidate windows until semantic AI is wired in."""
    if not segments:
        return []
    total = len(segments)
    target_count = min(max_proposals, 3 if total >= 6 else 2 if total >= 4 else 1)
    windows = []
    window_size = max(2, min(len(segments), ceil(total / target_count)))
    for index in range(target_count):
        start_index = min(index * window_size, max(0, total - window_size))
        end_index = min(total, start_index + window_size)
        if end_index - start_index < 2:
            continue
        labels = [("开场重点", "这一段最适合作为视频开头"), ("核心观点", "这一段包含较完整的观点表达"), ("故事片段", "这一段适合做独立内容片段")]
        title, reason = labels[index]
        candidate = _window(segments, start_index, end_index, title, segments[start_index]["text"][:42], reason)
        if not any(item["start"] == candidate["start"] and item["end"] == candidate["end"] for item in windows):
            windows.append(candidate)
    return windows
