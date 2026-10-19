"""A detached mpv process owns playback and queue across MCP sessions."""

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

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LOCK = threading.Lock()


def video_url(video_id: str) -> str:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Use an 11-character video_id returned by search.")
    return f"https://www.youtube.com/watch?v={video_id}"


def config_dir() -> Path:
    from rt_music.auth import config_dir as auth_config_dir

    return auth_config_dir()


class Player:
    def __init__(self, runtime: Path | None = None):
        base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.runtime = runtime or base / f"rt-music-{os.getuid()}"
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
                ytdlp = Path(sys.executable).parent / "yt-dlp"
                if not ytdlp.exists():
                    found = shutil.which("yt-dlp")
                    if not found:
                        raise RuntimeError(
                            "yt-dlp was not found; run uv sync or install yt-dlp."
                        )
                    ytdlp = Path(found)
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
            "title": self.get("media-title"),
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
        for i, item in enumerate(self.get("playlist", [])):
            url = item.get("filename", "")
            match = re.fullmatch(
                r"https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})", url
            )
            result.append(
                {
                    "index": i,
                    "title": item.get("title"),
                    "video_id": match.group(1) if match else None,
                    "current": item.get("current", False),
                }
            )
        return result

    def play(self, video_id, enqueue=False, title=None, artists=None):
        url = video_url(video_id)
        self.ensure()
        self.command("loadfile", url, "append-play" if enqueue else "replace")
        if not enqueue:
            self.command("set_property", "pause", False)
        try:
            from rt_music.history import log_playback

            log_playback(video_id, title=title, artists=artists, source="play_music")
        except Exception:  # noqa: S110, BLE001 — best-effort: playback must not fail because history is unavailable
            pass
        return {
            "accepted": True,
            "video_id": video_id,
            "enqueued": enqueue,
            "note": "Loading asynchronously; check playback_status to confirm audio playback.",
        }
