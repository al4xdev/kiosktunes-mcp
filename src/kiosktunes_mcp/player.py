"""A detached mpv process owns playback and queue across MCP sessions."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SIGNED_URL = re.compile(r"https?://\S+")
_LOCK = threading.Lock()

STREAM_FORMAT = "bestaudio[acodec=opus]/bestaudio[acodec=m4a]/bestaudio/best"
# googlevideo rejects plain HTTP clients with 403 for streams minted by some
# yt-dlp clients (ffmpeg cannot open the TV/visionOS URLs it gets served now).
# The android client still answers any client, at a lower bitrate, so it is
# the fallback and not the default.
STREAM_CLIENTS = (None, "android")
# The probe only needs the response status: googlevideo decides from the
# request, not from how much of the body is read.
PROBE_BYTES = 1024
PROBE_TIMEOUT = 10.0
EXTRACT_TIMEOUT = 90
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
# Stream URLs outlive long queues but not forever; this bounds the sidecar.
KNOWN_STREAMS = 500


def video_url(video_id: str) -> str:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Use an 11-character video_id returned by search.")
    return f"https://www.youtube.com/watch?v={video_id}"


def redact(text: str) -> str:
    """Strip signed URLs from diagnostics before they reach MCP errors."""
    return _SIGNED_URL.sub("<url>", text)


def text_title(value) -> str | None:
    """Reject mpv media titles that are really part of a signed stream URL.

    mpv reports the media URL as the title of a resolved stream, sometimes
    shortened to its query tail, so a scheme check is not enough.
    """
    if not isinstance(value, str) or not value:
        return None
    if any(marker in value for marker in ("://", "sig=", "sparams=", "googlevideo")):
        return None
    return value


def config_dir() -> Path:
    from kiosktunes_mcp.auth import config_dir as auth_config_dir

    return auth_config_dir()


class Player:
    def __init__(self, runtime: Path | None = None):
        base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.runtime = runtime or base / f"kiosktunes-mcp-{os.getuid()}"
        self.socket_path = self.runtime / "mpv.sock"

    def prepare(self):
        self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.runtime.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError(
                "IPC directory must be private and owned by the current user."
            )
        self.runtime.chmod(0o700)

    def command(self, *args):
        directory = self.runtime.lstat()
        endpoint = self.socket_path.lstat()
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.getuid()
            or directory.st_mode & 0o077
            or not stat.S_ISSOCK(endpoint.st_mode)
            or endpoint.st_uid != os.getuid()
        ):
            raise RuntimeError("Player IPC is not inside a safe private directory.")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(str(self.socket_path))
            client.sendall(
                (json.dumps({"command": args, "request_id": 1}) + "\n").encode()
            )
            with client.makefile("rb") as stream:
                for line in stream:
                    response = json.loads(line)
                    if response.get("request_id") == 1:
                        if response.get("error") != "success":
                            raise RuntimeError(f"mpv: {response.get('error')}")
                        return response.get("data")
            raise RuntimeError("mpv closed the IPC connection.")

    def available(self):
        try:
            self.command("get_property", "idle-active")
            return True
        except (OSError, RuntimeError):
            return False

    def ytdlp(self) -> Path:
        """Locate the yt-dlp binary shipped beside the running interpreter."""
        local = Path(sys.executable).parent / "yt-dlp"
        if local.exists():
            return local
        found = shutil.which("yt-dlp")
        if not found:
            raise RuntimeError("yt-dlp was not found; run uv sync or install yt-dlp.")
        return Path(found)

    def extract(
        self, video_id: str, client: str | None = None
    ) -> tuple[str, str | None]:
        """Ask yt-dlp for one direct stream URL for ``video_id`` and its title."""
        args = [
            str(self.ytdlp()),
            "--no-warnings",
            "--no-playlist",
            "--format",
            STREAM_FORMAT,
            "--get-url",
            "--print",
            "%(title)s",
        ]
        cookies = config_dir() / "cookies.txt"
        if cookies.is_file():
            args += ["--cookies", str(cookies)]
        if client:
            args += ["--extractor-args", f"youtube:player_client={client}"]
        args.append(video_url(video_id))
        try:
            done = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=EXTRACT_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("yt-dlp timed out resolving the stream.") from None
        urls = [
            line.strip() for line in done.stdout.splitlines() if line.startswith("http")
        ]
        if urls:
            title = next(
                (
                    line.strip()
                    for line in done.stdout.splitlines()
                    if line.strip() and not line.startswith("http")
                ),
                None,
            )
            return urls[-1], title
        details = (done.stderr or "").strip().splitlines()
        reason = details[-1] if details else "yt-dlp returned no stream URL."
        raise RuntimeError(redact(reason))

    def reachable(self, url: str) -> bool:
        """True when an HTTP client can open ``url`` right now."""
        request = Request(
            url,
            headers={
                "Range": f"bytes=0-{PROBE_BYTES - 1}",
                "User-Agent": BROWSER_UA,
            },
        )
        try:
            with urlopen(request, timeout=PROBE_TIMEOUT) as response:
                return response.status in (200, 206)
        except (HTTPError, URLError, OSError):
            return False

    def resolve(self, video_id: str) -> str:
        """Return a stream URL that ffmpeg can actually open.

        yt-dlp hands out URLs that googlevideo answers with 403 when the client
        that minted them is not the client that reads them, and mpv's own yt-dlp
        hook then reports success while nothing plays. Walking a short client
        ladder and probing the result keeps a dead track from being queued.
        """
        video_url(video_id)  # validate before spawning yt-dlp
        problems = []
        for client in STREAM_CLIENTS:
            label = client or "default"
            try:
                candidate, title = self.extract(video_id, client)
            except RuntimeError as exc:
                problems.append(f"{label}: {exc}")
                continue
            if self.reachable(candidate):
                self.remember(video_id, candidate, title)
                return candidate
            problems.append(f"{label}: stream answered 403")
        raise RuntimeError(
            f"No playable stream for {video_id} ({'; '.join(problems)})."
        )

    def remember(self, video_id: str, url: str, title: str | None = None):
        """Record url -> track identity so listings can name a resolved stream."""
        known = self._known_streams()
        known[url] = {"video_id": video_id, "title": title}
        if len(known) > KNOWN_STREAMS:
            known = dict(list(known.items())[-KNOWN_STREAMS:])
        path = self.runtime / "streams.json"
        try:
            path.write_text(json.dumps(known), encoding="utf-8")
            path.chmod(0o600)
        except OSError:
            pass  # only queue listings lose the track name, playback is unaffected

    def _known_streams(self) -> dict[str, dict]:
        path = self.runtime / "streams.json"
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        known = {}
        for url, value in loaded.items():
            # Older sidecars stored just the video_id string.
            if isinstance(value, str):
                known[url] = {"video_id": value, "title": None}
            elif isinstance(value, dict) and isinstance(value.get("video_id"), str):
                known[url] = {
                    "video_id": value["video_id"],
                    "title": value.get("title")
                    if isinstance(value.get("title"), str)
                    else None,
                }
        return known

    def _current_stream(self) -> dict:
        playlist = self.get("playlist") or []
        position = self.get("playlist-pos")
        if isinstance(position, int) and 0 <= position < len(playlist):
            filename = playlist[position].get("filename", "")
            return self._known_streams().get(filename, {})
        return {}

    def ensure(self):
        with _LOCK:
            self.prepare()
            # File lock also serializes startup across independent MCP clients.
            import fcntl

            with (self.runtime / "startup.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if self.available():
                    return
                mpv = shutil.which("mpv")
                if not mpv:
                    raise RuntimeError("Install mpv to play music in the terminal.")
                ytdlp = self.ytdlp()
                if self.socket_path.exists():
                    info = self.socket_path.lstat()
                    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                        raise RuntimeError("Unexpected file at the mpv socket path.")
                    # A busy but live player must not lose its socket or get duplicated.
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                        probe.settimeout(1)
                        try:
                            probe.connect(str(self.socket_path))
                        except (ConnectionRefusedError, FileNotFoundError):
                            self.socket_path.unlink(missing_ok=True)
                        else:
                            raise RuntimeError(
                                "The existing player is unresponsive; wait before retrying."
                            )
                args = [
                    mpv,
                    "--no-config",
                    "--idle=yes",
                    "--no-terminal",
                    "--vid=no",
                    "--audio-display=no",
                    "--volume=80",
                    "--ytdl-format=bestaudio[acodec=opus]/bestaudio[acodec=m4a]/bestaudio/best",
                    "--af=lavfi=[crystalizer=i=2.0],lavfi=[extrastereo=m=1.1]",
                    f"--script-opts=ytdl_hook-ytdl_path={ytdlp}",
                    f"--input-ipc-server={self.socket_path}",
                ]
                cookies = config_dir() / "cookies.txt"
                if cookies.is_file():
                    args.append(f"--ytdl-raw-options=cookies={cookies}")
                # Do not log mpv output: URLs and extractor diagnostics can contain credentials.
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                for _ in range(100):
                    if self.available():
                        return
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                raise RuntimeError(
                    "mpv failed to start IPC; the startup process was terminated."
                )

    def get(self, name, default=None):
        try:
            return self.command("get_property", name)
        except RuntimeError:
            return default

    def status(self):
        if not self.available():
            return {"running": False}
        return {
            "running": True,
            "paused": self.get("pause"),
            "idle": self.get("idle-active"),
            "position_seconds": self.get("time-pos"),
            "duration_seconds": self.get("duration"),
            "volume": self.get("volume"),
            "queue_position": self.get("playlist-pos"),
            # mpv titles a resolved stream with its signed URL; never surface that.
            "title": text_title(self.get("media-title"))
            or self._current_stream().get("title"),
            "audio": {
                "codec": self.get("audio-codec-name"),
                "bitrate": self.get("audio-bitrate"),
                "sample_rate": self.get("audio-params/samplerate"),
            },
            "quality_policy": "bestaudio/best (best available stream, no transcoding)",
        }

    def queue(self):
        if not self.available():
            return []
        result = []
        known = self._known_streams()
        for i, item in enumerate(self.get("playlist", [])):
            url = item.get("filename", "")
            match = re.fullmatch(
                r"https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})", url
            )
            # Resolved streams are googlevideo URLs, so fall back to the
            # sidecar to keep naming the track the queue is playing.
            entry = known.get(url, {})
            result.append(
                {
                    "index": i,
                    "title": text_title(item.get("title")) or entry.get("title"),
                    "video_id": match.group(1) if match else entry.get("video_id"),
                    "current": item.get("current", False),
                }
            )
        return result

    def play(
        self,
        video_id: str | list[str],
        enqueue: bool = True,
        title: str | None = None,
        artists: list[str] | None = None,
    ):
        if isinstance(video_id, str):
            ids = [video_id]
        elif isinstance(video_id, list):
            if not video_id:
                raise ValueError("video_id list cannot be empty.")
            if len(video_id) > 100:
                raise ValueError("Cannot enqueue more than 100 tracks at once.")
            ids = video_id
        else:
            raise TypeError(
                "video_id must be an 11-character string or list of strings."
            )

        # Validate all IDs up front before issuing any mpv commands
        for vid in ids:
            video_url(vid)

        self.ensure()
        # Each id costs one yt-dlp run (plus a fallback attempt) because the
        # stream URL is resolved here instead of letting mpv re-resolve it.
        # Batches are therefore for a handful of tracks, not full playlists.
        for i, vid in enumerate(ids):
            url = self.resolve(vid)
            is_replace = (not enqueue) and (i == 0)
            mode = "replace" if is_replace else "append-play"
            self.command("loadfile", url, mode)
            if is_replace:
                self.command("set_property", "pause", False)
            try:
                from kiosktunes_mcp.history import log_playback

                log_playback(
                    vid,
                    title=title if len(ids) == 1 else None,
                    artists=artists if len(ids) == 1 else None,
                    source="play_music",
                )
            except Exception:  # noqa: S110, BLE001 — best-effort: playback must not fail because history is unavailable
                pass
        return {
            "accepted": True,
            "video_id": ids[0] if len(ids) == 1 else ids,
            "video_ids": ids,
            "count": len(ids),
            "enqueued": enqueue,
            "note": "Stream resolved and probed; check playback_status to confirm audio playback.",
        }
