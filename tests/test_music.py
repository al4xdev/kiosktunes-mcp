import json
import socket
import threading

import pytest

from kiosktunes_mcp import server
from kiosktunes_mcp.player import Player, video_url


def test_video_id_validation():
    assert video_url("dQw4w9WgXcQ").endswith("dQw4w9WgXcQ")
    for invalid in ["--option", "https://example.com", "../secret", "", "a" * 12]:
        with pytest.raises(ValueError):
            video_url(invalid)


@pytest.mark.parametrize("volume", [-1, 101, float("nan"), float("inf")])
def test_volume_validation(volume):
    with pytest.raises(ValueError):
        server.set_volume(volume)


def test_search_validation():
    with pytest.raises(ValueError):
        server.search_music("")
    with pytest.raises(ValueError):
        server.search_music("music", filter="secret")


def test_ipc_ignores_events(tmp_path):
    player = Player(tmp_path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(player.socket_path))
    listener.listen(1)

    def respond():
        conn, _ = listener.accept()
        with conn:
            req = json.loads(conn.recv(4096))
            assert req["command"] == ["get_property", "volume"]
            conn.sendall(b'{"event":"start-file"}\n')
            conn.sendall(b'{"request_id":1,"error":"success","data":70}\n')
        listener.close()

    thread = threading.Thread(target=respond)
    thread.start()
    assert player.command("get_property", "volume") == 70
    thread.join(2)


def test_private_runtime(tmp_path):
    player = Player(tmp_path / "runtime")
    player.prepare()
    assert player.runtime.stat().st_mode & 0o777 == 0o700


def test_remote_error_is_sanitized():
    def fail():
        raise RuntimeError("cookie=secret signed_url=private")

    with pytest.raises(RuntimeError) as error:
        server.remote(fail)
    assert "secret" not in str(error.value)


def test_play_validates_before_start(tmp_path):
    with pytest.raises(ValueError):
        Player(tmp_path).play("malformed")


def test_enqueue_respects_hard_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "get_playlist",
        lambda *args: {"tracks": [{"videoId": "dQw4w9WgXcQ"}] * 150},
    )
    monkeypatch.setattr(
        server.player, "play", lambda *args, **kwargs: calls.append(args[0])
    )
    monkeypatch.setattr(server.player, "queue", list)
    assert server.enqueue_playlist("test", limit=1)["enqueued"] == 1
    assert len(calls) == 1


def test_queue_does_not_leak_signed_urls(monkeypatch, tmp_path):
    player = Player(tmp_path)
    monkeypatch.setattr(player, "available", lambda: True)
    monkeypatch.setattr(
        player, "get", lambda *args: [{"filename": "https://host/private?token=secret"}]
    )
    queue = player.queue()
    assert queue[0]["video_id"] is None
    assert "secret" not in str(queue)


def test_clear_queue_stops_current_track(monkeypatch):
    calls = []
    monkeypatch.setattr(server.player, "available", lambda: True)
    monkeypatch.setattr(server.player, "command", lambda *args: calls.append(args))
    monkeypatch.setattr(server.player, "status", dict)
    server.control_playback("clear_queue")
    assert calls == [("stop",), ("playlist-clear",)]


def test_busy_player_is_not_replaced(monkeypatch, tmp_path):
    player = Player(tmp_path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(player.socket_path))
    listener.listen(2)
    monkeypatch.setattr(player, "available", lambda: False)
    monkeypatch.setattr("kiosktunes_mcp.player.shutil.which", lambda _: "/usr/bin/mpv")
    try:
        with pytest.raises(RuntimeError, match="existing"):
            player.ensure()
        assert player.socket_path.exists()
    finally:
        listener.close()


def test_startup_failure_reaps_process(monkeypatch, tmp_path):
    player = Player(tmp_path)
    calls = []

    class FailedProcess:
        def poll(self):
            return 1

        def terminate(self):
            calls.append("terminate")

        def wait(self, **kwargs):
            calls.append("wait")

    monkeypatch.setattr(player, "available", lambda: False)
    monkeypatch.setattr("kiosktunes_mcp.player.shutil.which", lambda _: "/usr/bin/mpv")
    monkeypatch.setattr(
        "kiosktunes_mcp.player.subprocess.Popen", lambda *args, **kwargs: FailedProcess()
    )
    with pytest.raises(RuntimeError, match="terminated"):
        player.ensure()
    assert calls == ["terminate", "wait"]


def test_search_compact_by_default(monkeypatch):
    raw_item = {
        "resultType": "song",
        "title": "Creep",
        "videoId": "9RfVp-GhKfs",
        "artists": [{"name": "Radiohead", "id": "123"}],
        "album": {"name": "Pablo Honey", "id": "456"},
        "duration": "3:59",
        "duration_seconds": 239,
        "thumbnails": [{"url": "http://img", "width": 60, "height": 60}],
        "inLibrary": False,
        "videoType": "MUSIC_VIDEO_TYPE_ATV",
    }
    monkeypatch.setattr(server, "remote", lambda call, *args, **kwargs: [raw_item])
    compact = server.search_music("Radiohead")
    assert len(compact) == 1
    assert "thumbnails" not in compact[0]
    assert "duration_seconds" not in compact[0]
    assert "inLibrary" not in compact[0]
    assert compact[0]["artists"] == ["Radiohead"]
    assert compact[0]["album"] == "Pablo Honey"
    assert compact[0]["videoId"] == "9RfVp-GhKfs"

    detailed = server.search_music("Radiohead", detailed=True)
    assert "thumbnails" in detailed[0]
    assert detailed[0]["inLibrary"] is False


def test_search_batch_concurrent(monkeypatch):
    queries_searched = []

    def mock_search(query, **kwargs):
        queries_searched.append(query)
        return [{"title": f"Song for {query}", "videoId": "dQw4w9WgXcQ"}]

    monkeypatch.setattr(
        server, "remote", lambda call, *args, **kwargs: mock_search(args[0])
    )
    results = server.search_music(["query1", "query2", "query3"])
    assert isinstance(results, dict)
    assert set(results.keys()) == {"query1", "query2", "query3"}
    assert len(results["query1"]) == 1
    assert set(queries_searched) == {"query1", "query2", "query3"}


def test_search_batch_validation():
    with pytest.raises(ValueError, match="empty"):
        server.search_music([])
    with pytest.raises(ValueError, match="20"):
        server.search_music(["q"] * 21)
    with pytest.raises(ValueError, match="characters"):
        server.search_music(["valid", ""])


def test_play_music_defaults_to_enqueue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server.player,
        "play",
        lambda video_id, enqueue=True: calls.append((video_id, enqueue)),
    )
    server.play_music("dQw4w9WgXcQ")
    assert calls == [("dQw4w9WgXcQ", True)]


def test_play_batch_tracks(monkeypatch, tmp_path):
    player = Player(tmp_path)
    monkeypatch.setattr(player, "ensure", lambda: None)
    commands = []
    monkeypatch.setattr(player, "command", lambda *args: commands.append(args))

    # Test batch enqueue
    res = player.play(["dQw4w9WgXcQ", "pyTY6Z-Fqzw"], enqueue=True)
    assert res["count"] == 2
    assert res["enqueued"] is True
    assert commands == [
        ("loadfile", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "append-play"),
        ("loadfile", "https://www.youtube.com/watch?v=pyTY6Z-Fqzw", "append-play"),
    ]

    # Test batch replace (first replaces, subsequent append-play)
    commands.clear()
    res = player.play(["dQw4w9WgXcQ", "pyTY6Z-Fqzw"], enqueue=False)
    assert res["enqueued"] is False
    assert commands == [
        ("loadfile", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "replace"),
        ("set_property", "pause", False),
        ("loadfile", "https://www.youtube.com/watch?v=pyTY6Z-Fqzw", "append-play"),
    ]


def test_play_batch_validation(tmp_path):
    player = Player(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        player.play([])
    with pytest.raises(ValueError, match="100"):
        player.play(["dQw4w9WgXcQ"] * 101)
    with pytest.raises(ValueError, match="11-character"):
        player.play(["dQw4w9WgXcQ", "invalid_id"])


def test_edit_queue_batch_remove(monkeypatch):
    queue_mock = [
        {"index": 0, "title": "Track 0"},
        {"index": 1, "title": "Track 1"},
        {"index": 2, "title": "Track 2"},
        {"index": 3, "title": "Track 3"},
    ]
    commands = []
    monkeypatch.setattr(server.player, "queue", lambda: queue_mock)
    monkeypatch.setattr(server.player, "command", lambda *args: commands.append(args))

    # Removing indices 1 and 3 should remove 3 first, then 1 (reverse order)
    server.edit_queue("remove", [1, 3])
    assert commands == [("playlist-remove", 3), ("playlist-remove", 1)]

    # Disallow batch indices on move or select
    with pytest.raises(ValueError, match="Only action 'remove'"):
        server.edit_queue("move", [0, 1])

    # Out of range index
    with pytest.raises(ValueError, match="out of range"):
        server.edit_queue("remove", [1, 10])


def test_rate_music_single_and_batch(tmp_path, monkeypatch):
    from kiosktunes_mcp import history

    monkeypatch.setattr(history, "history_dir", lambda: tmp_path)

    # Rate single track
    res = server.rate_music("dQw4w9WgXcQ", rating=5.0, title="Never Gonna Give You Up")
    assert res["rated"] == 1
    assert res["ratings"][0]["rating"] == 5.0

    # Rate batch list of tracks
    res = server.rate_music(["dQw4w9WgXcQ", "pyTY6Z-Fqzw"], rating=4.0)
    assert res["rated"] == 2
    assert res["ratings"][0]["rating"] == 4.0
    assert res["ratings"][1]["rating"] == 4.0

    # Rate batch dict of tracks with individual scores
    res = server.rate_music({"dQw4w9WgXcQ": 5.0, "pyTY6Z-Fqzw": 3.5})
    assert res["rated"] == 2

    # Query ratings
    ratings = server.get_user_ratings(min_rating=4.0)
    assert len(ratings) == 1
    assert ratings[0]["video_id"] == "dQw4w9WgXcQ"


def test_rate_music_current_track(monkeypatch, tmp_path):
    from kiosktunes_mcp import history

    monkeypatch.setattr(history, "history_dir", lambda: tmp_path)
    monkeypatch.setattr(
        server.player,
        "queue",
        lambda: [
            {"index": 0, "video_id": "dQw4w9WgXcQ", "title": "Current Song", "current": True}
        ],
    )

    res = server.rate_music(rating=4.5)
    assert res["rated"] == 1
    assert res["ratings"][0]["video_id"] == "dQw4w9WgXcQ"
    assert res["ratings"][0]["title"] == "Current Song"
    assert res["ratings"][0]["rating"] == 4.5


def test_rate_music_validation(monkeypatch):
    monkeypatch.setattr(server.player, "queue", list)
    with pytest.raises(ValueError, match="currently playing"):
        server.rate_music()

    with pytest.raises(ValueError, match="11-character"):
        server.rate_music("invalid")

    with pytest.raises(TypeError, match="must be a string"):
        server.rate_music(123)
