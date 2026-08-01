"""Server-side OpenAI-compatible provider for semantic clip proposals."""

import json
import re
from urllib.request import Request, urlopen


def generate_ai_proposals(segments, api_key, base_url, model):
    transcript = "\n".join(
        f'[{segment["start"]:.2f}-{segment["end"]:.2f}] {segment["text"]}' for segment in segments
    )[:50_000]
    prompt = (
        "你是一名中文播客内容总编和剪辑策划。先在内部完成以下分析，再给出结果："
        "1. 理解完整内容的主题、人物关系、论证结构、关键观点和目标听众；"
        "2. 按语义而不是按时长平均划分章节；"
        "3. 从中选择2到3个方向明显不同、可以独立传播的连续片段；"
        "4. 检查每个片段必须从完整句子开始，在完整观点结束，不能突然截断；"
        "5. 优先选择信息密度高、有明确观点或故事转折、无需大量上下文也能理解的内容。"
        "每个片段建议30到120秒。时间只能使用字幕中真实存在的时间，不得编造内容。"
        "如果片段中存在可以删除的口癖、明显重复或无意义停顿，在cuts中给出精确范围；"
        "不要为了凑数量而推荐低质量片段。"
        "只输出有效JSON，不要Markdown。格式："
        '{"understanding":{"topic":"准确主题","summary":"完整内容脉络",'
        '"audience":"适合观众"},"proposals":[{"title":"方案标题",'
        '"hook":"为什么开头能吸引人","summary":"片段讲了什么",'
        '"start":0.0,"end":60.0,"reason":"选择理由和适用场景",'
        '"confidence":0.8,"cuts":[{"start":10.0,"end":11.2,"reason":"口癖"}]}]}。\n字幕：\n'
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
    parsed = json.loads(match.group(0))
    raw_understanding = parsed.get("understanding", {})
    understanding = {
        "topic": str(raw_understanding.get("topic", "内容主题"))[:100],
        "summary": str(raw_understanding.get("summary", ""))[:500],
        "audience": str(raw_understanding.get("audience", "适合关注该主题的观众"))[:160],
    }
    raw_proposals = parsed.get("proposals", [])
    max_end = max(segment["end"] for segment in segments)
    proposals = []
    for index, item in enumerate(raw_proposals[:3]):
        start = max(0.0, float(item["start"]))
        end = min(max_end, float(item["end"]))
        if end <= start + 1:
            continue
        cuts = []
        for raw_cut in item.get("cuts", [])[:30]:
            try:
                cut_start = max(start, float(raw_cut["start"]))
                cut_end = min(end, float(raw_cut["end"]))
            except (KeyError, TypeError, ValueError):
                continue
            if cut_end > cut_start + 0.1:
                cuts.append(
                    {
                        "start": round(cut_start, 3),
                        "end": round(cut_end, 3),
                        "reason": str(raw_cut.get("reason", "AI 精简建议"))[:120],
                    }
                )
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
                "cuts": cuts,
            }
        )
    if len(proposals) < 2:
        raise ValueError("AI 未生成足够的有效方案")
    return understanding, proposals
