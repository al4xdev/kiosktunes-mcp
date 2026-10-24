from kiosktunes_mcp import history


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


def test_log_and_get_ratings(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(history, "history_dir", lambda: tmp_path)
    assert history.get_ratings() == []

    history.log_rating("dQw4w9WgXcQ", 4.5, title="Song 1", artists=["Artist 1"])
    history.log_rating("pyTY6Z-Fqzw", 2.0, title="Song 2", artists=["Artist 2"])
    # Update first song to 5.0
    history.log_rating("dQw4w9WgXcQ", 5.0, title="Song 1", artists=["Artist 1"])

    ratings = history.get_ratings(min_rating=3.0)
    assert len(ratings) == 1
    assert ratings[0]["video_id"] == "dQw4w9WgXcQ"
    assert ratings[0]["rating"] == 5.0

    all_ratings = history.get_ratings()
    assert len(all_ratings) == 2

    with pytest.raises(ValueError, match="between 0 and 5"):
        history.log_rating("dQw4w9WgXcQ", 5.5)

    with pytest.raises(ValueError, match="between 0 and 5"):
        history.log_rating("dQw4w9WgXcQ", -1.0)


def test_history_annotated_with_ratings(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "history_dir", lambda: tmp_path)
    history.log_playback("dQw4w9WgXcQ", title="Track A")
    history.log_playback("pyTY6Z-Fqzw", title="Track B")
    history.log_rating("dQw4w9WgXcQ", 4.5)

    entries = history.get_history(10)
    assert len(entries) == 2
    # Most recent first
    assert entries[0]["video_id"] == "pyTY6Z-Fqzw"
    assert "user_rating" not in entries[0]
    assert entries[1]["video_id"] == "dQw4w9WgXcQ"
    assert entries[1]["user_rating"] == 4.5
