import io
import os

from podcast_cutter import create_app


def test_health_and_index(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    client = app.test_client()

    assert client.get("/").status_code == 200
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_invalid_job_id_is_rejected(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    client = app.test_client()

    assert client.get("/api/progress/not-a-job").status_code == 400
    assert client.get("/api/download/not-a-job").status_code == 400


def test_cut_rejects_invalid_ranges(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("ffmpeg", "ffprobe"):
        path = bin_dir / tool
        path.write_text("#!/bin/sh\n")
        os.chmod(path, 0o755)
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": bin_dir})
    client = app.test_client()

    response = client.post(
        "/api/cut",
        data={
            "cuts": "[{\"start\": \"bad\", \"end\": 2}]",
            "video": (io.BytesIO(b"not-video"), "sample.mp4"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "剪辑段" in response.get_json()["error"]


def test_transcription_status_is_explicit(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    response = app.test_client().get("/api/check-transcription")
    assert response.status_code == 200
    data = response.get_json()
    assert "available" in data
    assert data["install_hint"]


def test_transcription_rejects_missing_media(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    response = app.test_client().post("/api/transcribe", data={}, content_type="multipart/form-data")
    assert response.status_code in (400, 503)


def test_interrupted_transcription_is_reported_after_restart(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    job_id = "abcdef123456"
    (work_dir / f"{job_id}_transcribe_progress.json").write_text(
        '{"status":"running","progress":23}', encoding="utf-8"
    )
    app = create_app({"TESTING": True, "WORK_DIR": work_dir, "BIN_DIR": tmp_path / "bin"})

    response = app.test_client().get(f"/api/transcribe/{job_id}/progress")

    assert response.status_code == 200
    assert response.get_json()["code"] == "job_interrupted"


def test_smart_analyze_requires_semantic_ai(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    client = app.test_client()
    srt = "1\n00:00:00,000 --> 00:00:02,000\n第一段\n\n2\n00:00:02,000 --> 00:00:04,000\n第二段\n\n3\n00:00:04,000 --> 00:00:06,000\n第三段\n\n4\n00:00:06,000 --> 00:00:08,000\n第四段\n"
    response = client.post(
        "/api/smart/analyze",
        data={"video": (io.BytesIO(b"fake-video"), "sample.mp4"), "srt": srt},
        content_type="multipart/form-data",
    )
    assert response.status_code == 503
    data = response.get_json()
    assert data["code"] == "ai_unavailable"
    assert "精简剪辑" in data["error"]


def test_check_ai_is_explicit_when_not_configured(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    response = app.test_client().get("/api/check-ai")
    assert response.status_code == 200
    data = response.get_json()
    assert data["available"] is False
    assert "尚未配置" in data["message"]


def test_prepare_media_project_builds_shared_decision(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    project_id = "abcdef123456"
    (work_dir / f"{project_id}_podcast_input.mp3").write_bytes(b"fake-audio")
    (work_dir / f"{project_id}_transcript.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n开始\n\n"
        "2\n00:00:05,000 --> 00:00:06,000\n嗯\n",
        encoding="utf-8",
    )
    (work_dir / f"{project_id}_media.json").write_text(
        '{"project_id":"abcdef123456","original_name":"sample.mp3",'
        '"source_kind":"audio","stored_name":"abcdef123456_podcast_input.mp3"}',
        encoding="utf-8",
    )
    app = create_app({"TESTING": True, "WORK_DIR": work_dir, "BIN_DIR": tmp_path / "bin"})
    response = app.test_client().post(f"/api/media/{project_id}/prepare")
    assert response.status_code == 200
    data = response.get_json()
    assert data["source_kind"] == "audio"
    assert data["ai_available"] is False
    assert len(data["segments"]) == 2
    assert len(data["suggestions"]) == 2


def test_audio_analyze_returns_suggestions(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    segments = '[{"start":0,"end":2,"text":"开始"},{"start":5,"end":6,"text":"嗯"}]'
    response = app.test_client().post(
        "/api/audio/analyze",
        data={"audio": (io.BytesIO(b"fake-audio"), "sample.mp3"), "segments": segments},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["job_id"]
    assert len(data["suggestions"]) == 2


def test_podcast_analyze_creates_shared_edit_decision(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    client = app.test_client()
    segments = '[{"start":0,"end":2,"text":"开始"},{"start":5,"end":6,"text":"嗯"}]'
    response = client.post(
        "/api/podcast/analyze",
        data={"media": (io.BytesIO(b"fake-video"), "sample.mp4"), "segments": segments},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["source_kind"] == "video"
    project = client.get(f"/api/podcast/project/{data['project_id']}")
    assert project.status_code == 200
    decision = project.get_json()
    assert decision["source"]["kind"] == "video"
    assert decision["suggested_cuts"][0]["start"] == 2.25


def test_podcast_render_validates_output_for_audio_only_project(tmp_path):
    app = create_app({"TESTING": True, "WORK_DIR": tmp_path / "work", "BIN_DIR": tmp_path / "bin"})
    client = app.test_client()
    segments = '[{"start":0,"end":2,"text":"开始"},{"start":5,"end":6,"text":"嗯"}]'
    response = client.post(
        "/api/podcast/analyze",
        data={"media": (io.BytesIO(b"fake-audio"), "sample.mp3"), "segments": segments},
        content_type="multipart/form-data",
    )
    project_id = response.get_json()["project_id"]
    render = client.post(
        "/api/podcast/render",
        json={
            "project_id": project_id,
            "cuts": [{"start": 2.25, "end": 4.75}],
            "outputs": ["video"],
        },
    )
    assert render.status_code == 400
    assert "只上传了音频" in render.get_json()["error"]
