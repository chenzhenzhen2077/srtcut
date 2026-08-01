from podcast_cutter.smart import generate_proposals, parse_srt, summarize_content


def test_parse_srt_and_generate_proposals():
    srt = """1
00:00:00,000 --> 00:00:02,000
第一段内容

2
00:00:02,500 --> 00:00:04,000
第二段内容

3
00:00:05,000 --> 00:00:07,000
第三段内容

4
00:00:07,500 --> 00:00:09,000
第四段内容
"""
    segments = parse_srt(srt)
    proposals = generate_proposals(segments)
    assert len(segments) == 4
    assert 2 <= len(proposals) <= 3
    assert proposals[0]["end"] > proposals[0]["start"]
    assert proposals[0]["summary"]


def test_summarize_content_is_transparent():
    understanding = summarize_content([{"start": 0, "end": 2, "text": "我们来聊聊内容创作"}])
    assert understanding["topic"]
    assert understanding["summary"]
    assert understanding["audience"]
