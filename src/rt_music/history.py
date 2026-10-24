"""Persistent listening history logger for AI agents to craft personalized playlists."""

from __future__ import annotations

import json
import math
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
    path = base / "kiosktunes-mcp"
    if not path.is_dir() and (base / "simp-mcp").is_dir():
        return base / "simp-mcp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_file() -> Path:
    return history_dir() / "history.jsonl"


def log_playback(
    video_id: str,
    title: str | None = None,
    artists: list[str] | None = None,
    source: str = "play_music",
) -> dict:
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


def ratings_file() -> Path:
    return history_dir() / "ratings.jsonl"


def log_rating(
    video_id: str,
    rating: float,
    title: str | None = None,
    artists: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Append a rating/like entry (0 to 5) to the user taste profile."""
    if not math.isfinite(rating) or not 0 <= rating <= 5:
        raise ValueError("Rating must be a number between 0 and 5.")
    entry: dict = {
        "timestamp": int(time.time()),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video_id": video_id,
        "rating": round(float(rating), 2),
        "title": title or "Unknown",
        "artists": artists or [],
    }
    if notes:
        entry["notes"] = notes
    file = ratings_file()
    try:
        with file.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def get_ratings(limit: int = 50, min_rating: float = 0.0) -> list[dict]:
    """Return deduplicated ratings (latest rating per track), filtered by min_rating."""
    file = ratings_file()
    if not file.is_file():
        return []
    latest: dict[str, dict] = {}
    try:
        with file.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    vid = data.get("video_id")
                    if vid:
                        latest[vid] = data
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    filtered = [
        item for item in latest.values() if item.get("rating", 0.0) >= min_rating
    ]
    filtered.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return filtered[:limit]


def get_history(limit: int = 50) -> list[dict]:
    """Return the most recent playback entries up to limit, annotated with user ratings when available."""
    file = history_file()
    if not file.is_file():
        return []
    ratings_map = {r["video_id"]: r["rating"] for r in get_ratings(limit=1000)}
    entries = []
    try:
        with file.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    vid = entry.get("video_id")
                    if vid in ratings_map:
                        entry["user_rating"] = ratings_map[vid]
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries[-limit:][::-1]
