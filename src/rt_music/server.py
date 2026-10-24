"""MCP stdio entry point. Diagnostics never share cookies or stream URLs."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from mcp.server.fastmcp import FastMCP
from ytmusicapi import YTMusic

from rt_music.player import Player, config_dir

mcp = FastMCP(
    "simp-mcp",
    instructions="Search for a videoId before playing. play_music enqueues by default and accepts single or multiple videoIds; confirm playback_status. Playback persists between chats. Do not promise premium quality. Authentication tools return metadata only, never credentials.",
)
player = Player()


def compact_item(item: dict) -> dict:
    """Trim heavy metadata (thumbnails, internal flags) for LLM context efficiency."""
    if not isinstance(item, dict):
        return item
    compact: dict = {}
    result_type = item.get("resultType")
    if result_type:
        compact["resultType"] = result_type

    title = item.get("title") or item.get("artist")
    if title:
        compact["title"] = title

    for key in ("videoId", "browseId", "playlistId"):
        val = item.get(key)
        if val:
            compact[key] = val

    if "artists" in item and isinstance(item["artists"], list):
        names = [
            a.get("name")
            for a in item["artists"]
            if isinstance(a, dict) and a.get("name")
        ]
        if names:
            compact["artists"] = names
    elif "artist" in item and isinstance(item["artist"], str):
        compact["artists"] = [item["artist"]]

    if "album" in item:
        album = item["album"]
        if isinstance(album, dict) and album.get("name"):
            compact["album"] = album["name"]
        elif isinstance(album, str):
            compact["album"] = album

    duration = item.get("duration") or item.get("length")
    if duration:
        compact["duration"] = duration

    if item.get("year"):
        compact["year"] = item["year"]

    return compact


@lru_cache(maxsize=1)
def music():
    auth = config_dir() / "browser.json"
    try:
        return YTMusic(str(auth) if auth.is_file() else None)
    except Exception:  # noqa: BLE001 -- invalid auth data must never appear in MCP errors
        raise RuntimeError(
            "Local authentication configuration failed; reimport the cookies."
        ) from None


def remote(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except Exception:  # noqa: BLE001 -- sanitize all third-party diagnostics at credential boundary
        # Upstream errors may embed cookies, headers or signed URLs.
        raise RuntimeError(
            "YouTube Music is unavailable or authentication is invalid. Check your network and local configuration."
        ) from None


def limit_value(limit):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    return limit


@mcp.tool()
def search_music(
    query: str | list[str],
    filter: str = "songs",
    limit: int = 10,
    detailed: bool = False,
) -> list[dict] | dict[str, list[dict]]:
    """Search songs, videos, albums, artists or playlists. Accepts single query or list of queries."""
    if filter not in {"songs", "videos", "albums", "artists", "playlists"}:
        raise ValueError("filter: songs, videos, albums, artists or playlists.")
    bounded_limit = limit_value(limit)

    def _execute(q: str) -> list[dict]:
        if not isinstance(q, str) or not q.strip() or len(q) > 500:
            raise ValueError("Each query must contain 1 to 500 characters.")
        raw = remote(music().search, q, filter=filter, limit=bounded_limit)[
            :bounded_limit
        ]
        if not detailed:
            return [compact_item(item) for item in raw]
        return raw

    if isinstance(query, str):
        return _execute(query)
    if isinstance(query, list):
        if not query:
            raise ValueError("query list cannot be empty.")
        if len(query) > 20:
            raise ValueError("Cannot search more than 20 queries at once.")
        with ThreadPoolExecutor(max_workers=min(len(query), 5)) as pool:
            results = list(pool.map(_execute, query))
        return dict(zip(query, results))
    raise TypeError("query must be a string or list of strings.")


@mcp.tool()
def get_playlist(playlist_id: str, limit: int = 50, detailed: bool = False) -> dict:
    """List tracks in a YouTube Music playlist; use videoId for playback."""
    result = remote(music().get_playlist, playlist_id, limit=limit_value(limit))
    tracks = result.get("tracks", [])[:limit]
    if not detailed:
        tracks = [compact_item(t) for t in tracks]
        result.pop("thumbnails", None)
    result["tracks"] = tracks
    return result


@mcp.tool()
def get_album(browse_id: str, detailed: bool = False) -> dict:
    """Get album metadata and tracks using the browseId returned by search."""
    result = remote(music().get_album, browse_id)
    if not detailed:
        tracks = result.get("tracks", [])
        result["tracks"] = [compact_item(t) for t in tracks]
        result.pop("thumbnails", None)
    return result


@mcp.tool()
def get_artist(channel_id: str) -> dict:
    """Get artist information and discography."""
    return remote(music().get_artist, channel_id)


@mcp.tool()
def get_library_playlists(limit: int = 25) -> list:
    """List account playlists. Requires local browser.json authentication."""
    if not (config_dir() / "browser.json").is_file():
        raise ValueError("Configure local authentication to access your library.")
    return remote(music().get_library_playlists, limit=limit_value(limit))[:limit]


@mcp.tool()
def get_radio(video_id: str, limit: int = 25, detailed: bool = False) -> dict:
    """Get radio recommendations for a song without changing the queue."""
    from rt_music.player import video_url

    video_url(video_id)
    result = remote(
        music().get_watch_playlist, videoId=video_id, limit=limit_value(limit)
    )
    tracks = result.get("tracks", [])[:limit]
    if not detailed:
        tracks = [compact_item(t) for t in tracks]
    result["tracks"] = tracks
    return result


@mcp.tool()
def play_music(video_id: str | list[str], enqueue: bool = True) -> dict:
    """Play the best available audio or enqueue it. Defaults to enqueue=True. Accepts single video_id or list of video_ids."""
    return player.play(video_id, enqueue=enqueue)


@mcp.tool()
def playback_status() -> dict:
    """Get playback state, position and actual codec/bitrate when available. No signed URLs."""
    return player.status()


@mcp.tool()
def get_queue() -> list:
    """Get the persistent player queue with indices for removing or reordering tracks."""
    return player.queue()


@mcp.tool()
def control_playback(action: str) -> dict:
    """Control pause, resume, stop, next, previous, shuffle or clear_queue."""
    commands = {
        "pause": ("set_property", "pause", True),
        "resume": ("set_property", "pause", False),
        "stop": ("stop",),
        "next": ("playlist-next", "weak"),
        "previous": ("playlist-prev", "weak"),
        "shuffle": ("playlist-shuffle",),
        "clear_queue": ("playlist-clear",),
    }
    if action not in commands:
        raise ValueError(
            "action: pause, resume, stop, next, previous, shuffle or clear_queue."
        )
    if not player.available():
        return {"running": False, "note": "Use play_music first."}
    if action == "clear_queue":
        player.command("stop")
    player.command(*commands[action])
    return player.status()


@mcp.tool()
def seek_music(seconds: float, relative: bool = False) -> dict:
    """Seek to a position in seconds; relative allows skipping forward or backward."""
    if not math.isfinite(seconds) or (not relative and seconds < 0):
        raise ValueError("Invalid playback position.")
    player.command("seek", seconds, "relative+exact" if relative else "absolute+exact")
    return player.status()


@mcp.tool()
def set_volume(volume: float) -> dict:
    """Set volume from 0 to 100 without amplification above 100%."""
    if not math.isfinite(volume) or not 0 <= volume <= 100:
        raise ValueError("volume must be between 0 and 100.")
    player.command("set_property", "volume", volume)
    return player.status()


@mcp.tool()
def edit_queue(action: str, index: int | list[int], destination: int = 0) -> list:
    """Remove, move or select a queued item by index (action remove/move/select). Accepts int or list[int] for remove."""
    queue = player.queue()
    if isinstance(index, list) and action != "remove":
        raise ValueError("Only action 'remove' supports multiple indices.")
    if action == "remove":
        if isinstance(index, int):
            indices = [index]
        elif isinstance(index, list):
            if not index:
                raise ValueError("Queue index list cannot be empty.")
            indices = index
        else:
            raise TypeError("index must be an integer or list of integers.")
        for idx in indices:
            if not isinstance(idx, int) or not 0 <= idx < len(queue):
                raise ValueError("Queue index is out of range.")
        for idx in sorted(set(indices), reverse=True):
            player.command("playlist-remove", idx)
    elif action == "move":
        if not isinstance(index, int) or not 0 <= index < len(queue):
            raise ValueError("Queue index is out of range.")
        if not 0 <= destination < len(queue):
            raise ValueError("Destination index is out of range.")
        player.command("playlist-move", index, destination)
    elif action == "select":
        if not isinstance(index, int) or not 0 <= index < len(queue):
            raise ValueError("Queue index is out of range.")
        player.command("set_property", "playlist-pos", index)
    else:
        raise ValueError("action: remove, move or select.")
    return player.queue()


@mcp.tool()
def enqueue_playlist(playlist_id: str, limit: int = 50) -> dict:
    """Enqueue up to 100 playlist tracks, skipping entries without a valid videoId."""
    from rt_music.player import VIDEO_ID

    playlist = get_playlist(playlist_id, limit, True)
    ids = [track.get("videoId") for track in playlist.get("tracks", [])]
    ids = [item for item in ids if isinstance(item, str) and VIDEO_ID.fullmatch(item)][
        : limit_value(limit)
    ]
    if ids:
        player.play(ids, enqueue=True)
    return {"enqueued": len(ids), "queue": player.queue()}


@mcp.tool()
def set_repeat(mode: str) -> dict:
    """Set repeat mode: off, one (track) or all (queue)."""
    if mode not in {"off", "one", "all"}:
        raise ValueError("mode: off, one or all.")
    player.command("set_property", "loop-file", "inf" if mode == "one" else "no")
    player.command("set_property", "loop-playlist", "inf" if mode == "all" else "no")
    return {"repeat": mode}


@mcp.tool()
def get_lyrics(video_id: str) -> dict:
    """Get lyrics for a song when available."""
    radio = get_radio(video_id, 1)
    lyrics_id = radio.get("lyrics")
    if not lyrics_id:
        return {"available": False}
    return remote(music().get_lyrics, lyrics_id)


@mcp.tool()
def shutdown_player() -> dict:
    """Explicitly shut down mpv and discard its queue. Closing a chat does not stop playback."""
    if player.available():
        player.command("quit")
    return {"running": False}


@mcp.tool()
def auth_status() -> dict:
    """Report local auth file presence and permissions, never cookie/token values. Not a remote login check."""
    from rt_music.auth import AuthError, status

    try:
        result = status()
    except (AuthError, OSError):
        raise RuntimeError(
            "Cannot inspect local authentication configuration safely."
        ) from None
    result["configured"] = all(
        result[name].get("private", False) for name in ("cookies.txt", "browser.json")
    )
    return result


@mcp.tool()
def import_simpmusic_auth(force: bool = False, auth_user: int = 0) -> dict:
    """Explicitly import the local SimpMusic YouTube session. Fixed source, metadata only; force replaces existing files."""
    from rt_music.auth import AuthError, import_simpmusic

    if not 0 <= auth_user <= 100:
        raise ValueError("auth_user must be an account index between 0 and 100.")
    try:
        result = import_simpmusic(force=force, auth_user=auth_user)
    except AuthError as error:
        raise RuntimeError(str(error)) from None
    except OSError:
        raise RuntimeError("Local authentication import failed safely.") from None
    music.cache_clear()
    result["note"] = (
        "Catalog auth reloaded. Restart the player when convenient to reload playback cookies. No credentials returned."
    )
    return result


@mcp.tool()
def rate_music(
    video_id: str | list[str] | dict[str, float] | None = None,
    rating: float = 5.0,
    title: str | None = None,
    artists: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Rate or like one or multiple tracks (0 to 5 score) to train user taste profile for AI discovery. If video_id is omitted, rates the currently playing track."""
    from rt_music.history import log_rating
    from rt_music.player import VIDEO_ID

    items: list[tuple[str, float, str | None, list[str] | None]] = []

    if video_id is None:
        queue = player.queue()
        current = next((item for item in queue if item.get("current")), None)
        if not current or not current.get("video_id"):
            raise ValueError(
                "No track is currently playing. Provide a video_id to rate."
            )
        items.append(
            (current["video_id"], rating, title or current.get("title"), artists)
        )
    elif isinstance(video_id, str):
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError("Use an 11-character video_id returned by search.")
        items.append((video_id, rating, title, artists))
    elif isinstance(video_id, list):
        if not video_id:
            raise ValueError("video_id list cannot be empty.")
        if len(video_id) > 100:
            raise ValueError("Cannot rate more than 100 tracks at once.")
        for vid in video_id:
            if not isinstance(vid, str) or not VIDEO_ID.fullmatch(vid):
                raise ValueError("Each video_id must be an 11-character string.")
            items.append((vid, rating, None, None))
    elif isinstance(video_id, dict):
        if not video_id:
            raise ValueError("Ratings dictionary cannot be empty.")
        if len(video_id) > 100:
            raise ValueError("Cannot rate more than 100 tracks at once.")
        for vid, score in video_id.items():
            if not isinstance(vid, str) or not VIDEO_ID.fullmatch(vid):
                raise ValueError("Each video_id must be an 11-character string.")
            items.append((vid, float(score), None, None))
    else:
        raise TypeError(
            "video_id must be a string, list of strings, or dict of video_id->rating."
        )

    logged = []
    for vid, score, t, a in items:
        entry = log_rating(vid, score, title=t, artists=a, notes=notes)
        logged.append(entry)

    return {
        "rated": len(logged),
        "ratings": logged,
        "note": "Ratings saved to user music taste profile for personalized recommendations.",
    }


@mcp.tool()
def get_user_ratings(limit: int = 50, min_rating: float = 0.0) -> list[dict]:
    """Retrieve saved user song ratings (0 to 5) to understand musical taste and craft tailored recommendations."""
    from rt_music.history import get_ratings

    if not math.isfinite(min_rating) or not 0 <= min_rating <= 5:
        raise ValueError("min_rating must be between 0 and 5.")
    return get_ratings(limit=limit_value(limit), min_rating=min_rating)


@mcp.tool()
def get_listening_history(limit: int = 50) -> list:
    """Retrieve the recent listening history log to understand user music taste and craft custom playlists."""
    from rt_music.history import get_history

    return get_history(limit=limit_value(limit))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
