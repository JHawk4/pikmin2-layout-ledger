import pytest

from srcom_videos.links import parse_video_url


@pytest.mark.parametrize("url, canonical, host", [
    ("https://www.youtube.com/watch?v=NYcSyL-DpP0", "https://www.youtube.com/watch?v=NYcSyL-DpP0", "youtube"),
    ("https://youtu.be/im3ftB9QOQ4?si=H80chzpc7e-yzIpf", "https://www.youtube.com/watch?v=im3ftB9QOQ4", "youtube"),
    ("https://www.youtube.com/live/YRDzGs97EcI?si=gJQMWKhLZs0nciRu", "https://www.youtube.com/watch?v=YRDzGs97EcI", "youtube"),
    ("youtube.com/watch?v=k0n-_1TBMoM&t=30s", "https://www.youtube.com/watch?v=k0n-_1TBMoM", "youtube"),
    ("https://m.youtube.com/watch?v=222r2jWogVA", "https://www.youtube.com/watch?v=222r2jWogVA", "youtube"),
    ("https://www.twitch.tv/videos/1763792762", "https://www.twitch.tv/videos/1763792762", "twitch"),
    ("https://www.twitch.tv/someone/v/123456", "https://www.twitch.tv/videos/123456", "twitch"),
])
def test_known_hosts(url, canonical, host):
    link = parse_video_url(url)
    assert link.canonical_url == canonical
    assert link.host == host


def test_other_host_kept():
    link = parse_video_url("https://example.com/run.mp4")
    assert link.host == "other"
    assert link.video_id is None
    assert link.canonical_url == "https://example.com/run.mp4"
