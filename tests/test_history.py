from rt_music import history


def test_log_and_get_history(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "history_dir", lambda: tmp_path)
    entries = history.get_history(10)
    assert entries == []

    history.log_playback("videoId1234", title="Test Song", artists=["Artist A"])
    history.log_playback("videoId5678", title="Second Song", artists=["Artist B"])

    loaded = history.get_history(10)
    assert len(loaded) == 2
    assert loaded[0]["video_id"] == "videoId5678"
    assert loaded[0]["title"] == "Second Song"
    assert loaded[1]["video_id"] == "videoId1234"
