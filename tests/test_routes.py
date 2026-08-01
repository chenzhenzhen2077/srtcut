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
