import json
import socket
import threading

import pytest

from rt_music import server
from rt_music.player import Player, video_url


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
    monkeypatch.setattr(server, "get_playlist", lambda *args: {"tracks": [{"videoId": "dQw4w9WgXcQ"}] * 150})
    monkeypatch.setattr(server.player, "play", lambda *args, **kwargs: calls.append(args[0]))
    monkeypatch.setattr(server.player, "queue", list)
    assert server.enqueue_playlist("test", limit=1)["enqueued"] == 1
    assert len(calls) == 1


def test_queue_does_not_leak_signed_urls(monkeypatch, tmp_path):
    player = Player(tmp_path)
    monkeypatch.setattr(player, "available", lambda: True)
    monkeypatch.setattr(player, "get", lambda *args: [{"filename": "https://host/private?token=secret"}])
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
    monkeypatch.setattr("rt_music.player.shutil.which", lambda _: "/usr/bin/mpv")
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
        def poll(self): return 1
        def terminate(self): calls.append("terminate")
        def wait(self, **kwargs): calls.append("wait")

    monkeypatch.setattr(player, "available", lambda: False)
    monkeypatch.setattr("rt_music.player.shutil.which", lambda _: "/usr/bin/mpv")
    monkeypatch.setattr("rt_music.player.subprocess.Popen", lambda *args, **kwargs: FailedProcess())
    with pytest.raises(RuntimeError, match="terminated"):
        player.ensure()
    assert calls == ["terminate", "wait"]
