from podcast_cutter.audio import analyze_audio_segments, build_audio_export_command


def test_audio_analysis_marks_gap_only_and_filler_segment():
    suggestions = analyze_audio_segments(
        [
            {"start": 0, "end": 2, "text": "我们开始"},
            {"start": 5, "end": 6, "text": "嗯"},
        ],
        silence_threshold=1.5,
    )
    assert suggestions[0]["start"] == 2.25
    assert suggestions[0]["end"] == 4.75
    assert "长停顿" in suggestions[0]["reason"]
    assert suggestions[1]["start"] == 5
    assert suggestions[1]["end"] == 6
    assert "口癖" in suggestions[1]["reason"]


def test_audio_command_outputs_mp3():
    command = build_audio_export_command(
        "ffmpeg", "input.wav", "output.mp3", [{"start": 2, "end": 4}]
    )
    assert command[0] == "ffmpeg"
    assert "libmp3lame" in command
    assert command[-1] == "output.mp3"
