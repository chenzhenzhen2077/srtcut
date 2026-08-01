"""Server-side OpenAI-compatible provider for semantic clip proposals."""

import json
import re
from urllib.request import Request, urlopen


def generate_ai_proposals(segments, api_key, base_url, model):
    transcript = "\n".join(
        f'[{segment["start"]:.2f}-{segment["end"]:.2f}] {segment["text"]}' for segment in segments
    )[:50_000]
    prompt = (
        "你是中文播客短视频剪辑策划。请从字幕中选择2到3个可以独立传播的连续内容片段。"
        "每段建议30到120秒，优先选择观点完整、有开头吸引力、无需上下文也能理解的片段。"
        "只输出JSON，不要Markdown。格式："
        '{"proposals":[{"title":"标题","hook":"开头钩子","summary":"摘要",'
        '"start":0.0,"end":60.0,"reason":"推荐理由","confidence":0.8}]}。\n字幕：\n'
        + transcript
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "你只返回有效JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        raise ValueError("AI 返回格式无效")
    raw_proposals = json.loads(match.group(0)).get("proposals", [])
    max_end = max(segment["end"] for segment in segments)
    proposals = []
    for index, item in enumerate(raw_proposals[:3]):
        start = max(0.0, float(item["start"]))
        end = min(max_end, float(item["end"]))
        if end <= start + 1:
            continue
        proposals.append(
            {
                "id": f"ai-proposal-{index + 1}",
                "title": str(item.get("title", f"内容方案 {index + 1}"))[:40],
                "hook": str(item.get("hook", ""))[:100],
                "summary": str(item.get("summary", ""))[:240],
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "reason": str(item.get("reason", "AI 内容分析"))[:160],
                "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.75)))),
                "cuts": [],
            }
        )
    if len(proposals) < 2:
        raise ValueError("AI 未生成足够的有效方案")
    return proposals

