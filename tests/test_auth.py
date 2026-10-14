"""Auth tests use invented session strings, never the user's local credentials."""

import json
import stat
from pathlib import Path

import pytest
from ytmusicapi.auth.auth_parse import determine_auth_type, parse_auth_str
from ytmusicapi.auth.types import AuthType

from rt_music.auth import AuthError, config_dir, import_simpmusic, read_cookies, status


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t0\t__Secure-3PAPISID\tfake-session\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tfake-sid\n"
        ".google.com\tTRUE\t/\tTRUE\t0\tSID\tfake-unrelated\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1\tEXPIRED\tfake-expired\n"
        "youtube.com\tFALSE\t/\tTRUE\t0\tHOSTONLY\tfake-host-only\n",
        encoding="utf-8",
    )
    return path


def test_filter_and_private_import(source: Path, tmp_path: Path) -> None:
    cookies = read_cookies(source)
    assert len(cookies) == 2
    assert "fake-session" not in repr(cookies[0])
    directory = tmp_path / "rt-music"
    result = import_simpmusic(source, directory=directory)
    assert result["cookie_count"] == 2
    assert "fake-session" not in json.dumps(result)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in ("cookies.txt", "browser.json"):
        assert stat.S_IMODE((directory / name).stat().st_mode) == 0o600
        assert status(directory)[name]["private"] is True
    text = (directory / "cookies.txt").read_text()
    assert "fake-unrelated" not in text
    assert "fake-expired" not in text
    assert "fake-host-only" not in text
    assert "#HttpOnly_" in text
    headers, _ = parse_auth_str(str(directory / "browser.json"))
    assert determine_auth_type(headers) == AuthType.BROWSER


def test_overwrite_requires_force(source: Path, tmp_path: Path) -> None:
    directory = tmp_path / "rt-music"
    import_simpmusic(source, directory=directory)
    before = (directory / "browser.json").read_bytes()
    with pytest.raises(AuthError, match="--force"):
        import_simpmusic(source, directory=directory)
    assert before == (directory / "browser.json").read_bytes()
    import_simpmusic(source, directory=directory, force=True, auth_user=2)
    assert json.loads((directory / "browser.json").read_text())["x-goog-authuser"] == "2"
    assert not list(directory.glob(".auth-*"))


def test_existing_single_file_blocks_whole_import(source: Path, tmp_path: Path) -> None:
    directory = tmp_path / "rt-music"
    directory.mkdir()
    (directory / "browser.json").write_text("existing")
    with pytest.raises(AuthError, match="--force"):
        import_simpmusic(source, directory=directory)
    assert not (directory / "cookies.txt").exists()
    assert (directory / "browser.json").read_text() == "existing"


def test_reject_symlinks(source: Path, tmp_path: Path) -> None:
    link = tmp_path / "source-link"
    link.symlink_to(source)
    with pytest.raises(AuthError):
        read_cookies(link)
    directory = tmp_path / "rt-music"
    directory.mkdir()
    (directory / "cookies.txt").symlink_to(source)
    with pytest.raises(AuthError, match="unsafe"):
        import_simpmusic(source, directory=directory, force=True)
    assert source.read_text().startswith("# Netscape")
    directory_link = tmp_path / "directory-link"
    directory_link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(AuthError):
        import_simpmusic(source, directory=directory_link, force=True)


@pytest.mark.parametrize("row", [
    "malformed-row",
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tfake; injected",
    ".youtube.com\tTRUE\t/\tTRUE\t0\tBAD NAME\tfake",
    ".youtube.com\tTRUE\t/\tTRUE\t-1\tSID\tfake",
])
def test_malformed_errors_do_not_echo_input(tmp_path: Path, row: str) -> None:
    source = tmp_path / "source.txt"
    source.write_text("# Netscape HTTP Cookie File\n" + row)
    with pytest.raises(AuthError) as error:
        read_cookies(source)
    assert row not in str(error.value)
    assert "fake" not in str(error.value)


def test_missing_signing_cookie_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tfake")
    directory = tmp_path / "rt-music"
    with pytest.raises(AuthError, match="__Secure-3PAPISID"):
        import_simpmusic(source, directory=directory)
    assert not directory.exists()


def test_xdg_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_dir() == tmp_path / "rt-music"
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative")
    with pytest.raises(AuthError, match="absolute"):
        config_dir()
