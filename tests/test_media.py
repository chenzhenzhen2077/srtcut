from podcast_cutter.media import build_ffmpeg_command, normalize_cuts


def test_normalize_cuts_sorts_and_merges_ranges():
    cuts = normalize_cuts(
        [
            {"start": 4, "end": 5, "reason": "b"},
            {"start": 1, "end": 2, "reason": "a"},
            {"start": 1.98, "end": 3, "reason": "c"},
        ]
    )
    assert cuts == [
        {"start": 1.0, "end": 3.0, "reason": "a; c"},
        {"start": 4.0, "end": 5.0, "reason": "b"},
    ]


def test_fast_quality_keeps_one_combined_video_filter():
    command = build_ffmpeg_command("ffmpeg", "input.mp4", "output.mp4", [{"start": 1, "end": 2}], "fast")
    vf_indexes = [index for index, value in enumerate(command) if value == "-vf"]
    assert len(vf_indexes) == 1
    assert "select=" in command[vf_indexes[0] + 1]
    assert "scale=1280:-2" in command[vf_indexes[0] + 1]

