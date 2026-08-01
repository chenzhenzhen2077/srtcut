from types import SimpleNamespace

from podcast_cutter import speech


class FakeModel:
    def transcribe(self, _path, **_kwargs):
        return iter(
            [
                SimpleNamespace(start=0.12, end=1.5, text="  第一段  "),
                SimpleNamespace(start=2.0, end=3.25, text="第二段"),
            ]
        ), SimpleNamespace(language="zh")


def test_format_srt_timestamp():
    assert speech.format_srt_timestamp(1.234) == "00:00:01,234"
    assert speech.format_srt_timestamp(3661.5) == "01:01:01,500"


def test_transcribe_writes_srt_without_real_model(tmp_path, monkeypatch):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.srt"
    progress_path = tmp_path / "progress.json"
    input_path.write_bytes(b"fake")
    monkeypatch.setattr(speech, "_get_model", lambda _model_name: FakeModel())

    speech.transcribe_to_srt(input_path, output_path, progress_path, "abc123def456", "tiny", "zh")

    result = output_path.read_text(encoding="utf-8")
    assert "1\n00:00:00,120 --> 00:00:01,500\n第一段" in result
    assert "2\n00:00:02,000 --> 00:00:03,250\n第二段" in result
    assert '"status": "done"' in progress_path.read_text(encoding="utf-8")
    assert not input_path.exists()

