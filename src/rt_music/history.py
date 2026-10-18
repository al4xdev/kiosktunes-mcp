"""Persistent listening history logger for AI agents to craft personalized playlists."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def history_dir() -> Path:
    """Return the base directory for history logs, prioritizing project local or XDG data."""
    # First check project-local logs directory
    local = Path(__file__).resolve().parent.parent.parent / "logs"
    if local.is_dir() or local.parent.is_dir():
        local.mkdir(parents=True, exist_ok=True)
        return local
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "simp-mcp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_file() -> Path:
    return history_dir() / "history.jsonl"


def log_playback(video_id: str, title: str | None = None, artists: list[str] | None = None, source: str = "play_music") -> dict:
    """Append a listening record to the JSON lines log."""
    entry = {
        "timestamp": int(time.time()),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video_id": video_id,
        "title": title or "Unknown",
        "artists": artists or [],
        "source": source,
    }
    file = history_file()
    try:
        with file.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def get_history(limit: int = 50) -> list[dict]:
    """Return the most recent playback entries up to limit."""
    file = history_file()
    if not file.is_file():
        return []
    entries = []
    try:
        with file.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries[-limit:][::-1]
