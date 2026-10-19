"""CLI tests share mocked primitives and never change the user's player."""

import json

import pytest

from rt_music import cli, server


def test_default_is_stdio(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "main", lambda: calls.append("mcp"))
    assert cli.main([]) == 0
    assert calls == ["mcp"]


def test_help_does_not_start_player(capsys):
    assert cli.main(["music"]) == 0
    assert "Control your local" in capsys.readouterr().out


@pytest.mark.parametrize(
    "action,expected",
    [
        ("pause", "pause"),
        ("resume", "resume"),
        ("next", "next"),
        ("last", "previous"),
        ("previous", "previous"),
        ("clear", "clear_queue"),
    ],
)
def test_direct_controls(monkeypatch, capsys, action, expected):
    calls = []
    monkeypatch.setattr(
        server,
        "control_playback",
        lambda value: calls.append(value) or {"accepted": True},
    )
    assert cli.main(["music", action]) == 0
    assert calls == [expected]
    assert json.loads(capsys.readouterr().out)["accepted"] is True


def test_search_then_play(monkeypatch, capsys):
    monkeypatch.setattr(
        server,
        "search_music",
        lambda query, **kwargs: [{"videoId": "dQw4w9WgXcQ", "title": "Example"}],
    )
    calls = []
    monkeypatch.setattr(
        server,
        "play_music",
        lambda video_id, **kwargs: (
            calls.append((video_id, kwargs)) or {"accepted": True}
        ),
    )
    assert cli.main(["music", "play", "example artist", "song", "--enqueue"]) == 0
    assert calls == [("dQw4w9WgXcQ", {"enqueue": True})]
    assert json.loads(capsys.readouterr().out)["selected_title"] == "Example"


def test_play_without_query_resumes(monkeypatch):
    monkeypatch.setattr(server, "control_playback", lambda action: {"action": action})
    result = cli.execute(cli.music_parser().parse_args(["play"]))
    assert result == {"action": "resume"}


def test_cli_exact_id_does_not_search(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server, "play_music", lambda value, **kwargs: calls.append(value) or {}
    )
    assert cli.main(["music", "play", "--id", "dQw4w9WgXcQ"]) == 0
    assert calls == ["dQw4w9WgXcQ"]


def test_cli_auth_is_fixed_source(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        server,
        "import_simpmusic_auth",
        lambda **kwargs: calls.append(kwargs) or {"imported": True},
    )
    assert (
        cli.main(["music", "auth", "import-simpmusic", "--force", "--auth-user", "2"])
        == 0
    )
    assert calls == [{"force": True, "auth_user": 2}]
    assert "cookie" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["music", "auth", "import-simpmusic", "--source", "/private/file"])


def test_cli_unexpected_errors_are_redacted(monkeypatch, capsys):
    class UpstreamError(Exception):
        pass

    def fail():
        raise UpstreamError("cookie=private-session")

    monkeypatch.setattr(server, "playback_status", fail)
    assert cli.main(["music", "status"]) == 1
    result = capsys.readouterr()
    assert "private-session" not in result.err
    assert not result.out


def test_auth_tool_boundaries(monkeypatch):
    from rt_music import auth

    calls = []
    monkeypatch.setattr(
        auth,
        "import_simpmusic",
        lambda **kwargs: (
            calls.append(kwargs) or {"files": ["browser.json"], "cookie_count": 2}
        ),
    )
    assert server.import_simpmusic_auth(force=True, auth_user=3)["cookie_count"] == 2
    assert calls == [{"force": True, "auth_user": 3}]
    with pytest.raises(ValueError):
        server.import_simpmusic_auth(auth_user=-1)


def test_volume_validation_is_english(capsys):
    assert cli.main(["music", "volume", "101"]) == 1
    assert "between 0 and 100" in capsys.readouterr().err
