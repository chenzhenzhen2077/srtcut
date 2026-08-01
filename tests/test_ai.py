from podcast_cutter import ai


def _config(**overrides):
    config = {
        "AI_PROVIDER": "auto",
        "AI_API_KEY": "",
        "AI_BASE_URL": "https://example.test/v1",
        "AI_MODEL": "cloud-model",
        "AI_LOCAL_ENABLED": True,
        "AI_LOCAL_BASE_URL": "http://127.0.0.1:11434/v1",
        "AI_LOCAL_MODEL": "qwen2.5:14b",
        "AI_LOCAL_API_KEY": "ollama",
        "AI_LOCAL_TIMEOUT": 1,
    }
    config.update(overrides)
    return config


def test_auto_uses_local_model_without_api_key(monkeypatch):
    monkeypatch.setattr(ai, "list_local_models", lambda *_args, **_kwargs: ["qwen2.5:14b"])

    result = ai.resolve_ai_backend(_config())

    assert result["available"] is True
    assert result["provider"] == "local"
    assert result["model"] == "qwen2.5:14b"


def test_auto_prefers_configured_api(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("local service should not be probed when API is configured")

    monkeypatch.setattr(ai, "list_local_models", fail_if_called)
    result = ai.resolve_ai_backend(_config(AI_API_KEY="secret"))

    assert result["available"] is True
    assert result["provider"] == "api"
    assert result["model"] == "cloud-model"


def test_local_mode_reports_missing_model(monkeypatch):
    monkeypatch.setattr(ai, "list_local_models", lambda *_args, **_kwargs: ["qwen2.5:7b"])

    result = ai.resolve_ai_backend(_config(AI_PROVIDER="local"))

    assert result["available"] is False
    assert "没有找到" in result["message"]
    assert result["models"] == ["qwen2.5:7b"]


def test_resolve_ai_channels_exposes_local_and_api(monkeypatch):
    monkeypatch.setattr(ai, "list_local_models", lambda *_args, **_kwargs: ["qwen2.5:14b"])

    channels = ai.resolve_ai_channels(_config(AI_API_KEY="secret"))

    assert channels["local"]["available"] is True
    assert channels["local"]["enabled"] is True
    assert channels["local"]["provider"] == "local"
    assert channels["api"]["available"] is True
    assert channels["api"]["configured"] is True
    assert channels["active"]["provider"] == "api"


def test_resolve_ai_channels_marks_disabled_local_channel(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("disabled local service should not be probed")

    monkeypatch.setattr(ai, "list_local_models", fail_if_called)
    channels = ai.resolve_ai_channels(
        _config(AI_LOCAL_ENABLED=False, AI_PROVIDER="api", AI_API_KEY="secret")
    )

    assert channels["local"]["enabled"] is False
    assert channels["local"]["available"] is False
    assert channels["active"]["provider"] == "api"
