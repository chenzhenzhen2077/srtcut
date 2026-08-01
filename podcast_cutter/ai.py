"""Server-side OpenAI-compatible provider for semantic clip proposals."""

import json
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def _local_root_url(base_url):
    parsed = urlsplit(base_url.rstrip("/"))
    path = parsed.path.rstrip("/").removesuffix("/v1")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _read_json(url, timeout, api_key=""):
    headers = {"Accept": "application/json", "User-Agent": "PodcastCutter/0.3"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def list_local_models(base_url, timeout=2, api_key=""):
    """List models from Ollama or another OpenAI-compatible local server."""
    root_url = _local_root_url(base_url)
    endpoints = [root_url + "/api/tags", base_url.rstrip("/") + "/models"]
    for endpoint in endpoints:
        try:
            data = _read_json(endpoint, timeout, api_key)
        except (OSError, ValueError):
            data = {}
        if isinstance(data.get("models"), list):
            names = [str(item.get("name", "")) for item in data["models"] if item.get("name")]
        elif isinstance(data.get("data"), list):
            names = [str(item.get("id", "")) for item in data["data"] if item.get("id")]
        else:
            names = []
        if names:
            return names
    return []


def resolve_ai_backend(config, provider_override=None):
    """Resolve the active semantic model without exposing credentials to the browser."""
    provider = str(
        provider_override if provider_override is not None else config.get("AI_PROVIDER", "auto")
    ).lower()
    api_key = str(config.get("AI_API_KEY", ""))
    api_ready = bool(api_key)

    if provider in {"api", "cloud", "remote"}:
        if api_ready:
            return {
                "available": True,
                "provider": "api",
                "model": config["AI_MODEL"],
                "base_url": config["AI_BASE_URL"],
                "api_key": api_key,
                "message": f"在线 AI 已配置：{config['AI_MODEL']}",
            }
        return {
            "available": False,
            "provider": "api",
            "model": config.get("AI_MODEL"),
            "base_url": config.get("AI_BASE_URL"),
            "message": "在线 AI 尚未配置服务密钥",
        }

    if provider == "auto" and api_ready:
        return {
            "available": True,
            "provider": "api",
            "model": config["AI_MODEL"],
            "base_url": config["AI_BASE_URL"],
            "api_key": api_key,
            "message": f"当前使用在线 AI：{config['AI_MODEL']}",
        }

    if provider not in {"auto", "local", "ollama"}:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "message": "AI 通道配置无效，请使用 auto、local 或 api",
        }

    if not config.get("AI_LOCAL_ENABLED", True):
        return {
            "available": False,
            "provider": "local",
            "model": config.get("AI_LOCAL_MODEL"),
            "base_url": config.get("AI_LOCAL_BASE_URL"),
            "message": "本地 AI 已关闭；在线 AI 也尚未配置",
        }

    local_model = str(config.get("AI_LOCAL_MODEL", "qwen2.5:14b"))
    local_base_url = str(config.get("AI_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1"))
    local_api_key = str(config.get("AI_LOCAL_API_KEY", "ollama"))
    models = list_local_models(
        local_base_url,
        timeout=max(1, int(config.get("AI_LOCAL_TIMEOUT", 2))),
        api_key=local_api_key,
    )
    normalized = {name.removesuffix(":latest") for name in models}
    if local_model in models or local_model.removesuffix(":latest") in normalized:
        return {
            "available": True,
            "provider": "local",
            "model": local_model,
            "base_url": local_base_url,
            "api_key": local_api_key,
            "models": models,
            "message": f"当前使用本地模型：{local_model}，内容不会发送到外部 AI",
        }
    if models:
        return {
            "available": False,
            "provider": "local",
            "model": local_model,
            "base_url": local_base_url,
            "models": models,
            "message": f"本地服务已运行，但没有找到 {local_model}",
        }
    return {
        "available": False,
        "provider": "local",
        "model": local_model,
        "base_url": local_base_url,
        "models": [],
        "message": "智能内容分析尚未配置，或本地模型服务尚未启动",
    }


def resolve_ai_channels(config):
    """Resolve both user-selectable AI channels and the configured default.

    The returned ``active`` value is the full internal backend description. The
    channel summaries intentionally omit API credentials before they are sent
    to the browser.
    """
    local = resolve_ai_backend(config, "local")
    api = resolve_ai_backend(config, "api")
    configured_provider = str(config.get("AI_PROVIDER", "auto")).lower()
    if configured_provider in {"api", "cloud", "remote"}:
        active = api
    elif configured_provider in {"local", "ollama"}:
        active = local
    else:
        active = api if api["available"] else local

    def summary(status):
        return {
            "available": bool(status.get("available")),
            "provider": status.get("provider"),
            "model": status.get("model"),
            "base_url": status.get("base_url"),
            "message": status.get("message", ""),
            "configured": bool(status.get("available")),
            "models": status.get("models", []),
        }

    local_summary = summary(local)
    local_summary["enabled"] = bool(config.get("AI_LOCAL_ENABLED", True))
    return {"local": local_summary, "api": summary(api), "active": active}


def generate_ai_proposals(segments, api_key, base_url, model, timeout=90, max_tokens=1200):
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
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "PodcastCutter/0.3"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
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
