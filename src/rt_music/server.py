"""MCP stdio entry point. Diagnostics never share cookies or stream URLs."""
import math
from functools import lru_cache

from mcp.server.fastmcp import FastMCP
from ytmusicapi import YTMusic

from rt_music.player import Player, config_dir

mcp = FastMCP("simp-mcp", instructions="Search for a videoId before playing. play_music loads asynchronously; confirm playback_status. Playback persists between chats. Do not promise premium quality. Authentication tools return metadata only, never credentials.")
player = Player()


@lru_cache(maxsize=1)
def music():
    auth = config_dir() / "browser.json"
    try:
        return YTMusic(str(auth) if auth.is_file() else None, requests_timeout=20)
    except Exception:  # noqa: BLE001 -- invalid auth data must never appear in MCP errors
        raise RuntimeError("Local authentication configuration failed; reimport the cookies.") from None


def remote(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except Exception:  # noqa: BLE001 -- sanitize all third-party diagnostics at credential boundary
        # Upstream errors may embed cookies, headers or signed URLs.
        raise RuntimeError("YouTube Music is unavailable or authentication is invalid. Check your network and local configuration.") from None


def limit_value(limit):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    return limit


@mcp.tool()
def search_music(query: str, filter: str = "songs", limit: int = 10) -> list:
    """Search songs, videos, albums, artists or playlists. Returns videoId/browseId."""
    if not query.strip() or len(query) > 500:
        raise ValueError("query must contain 1 to 500 characters.")
    if filter not in {"songs", "videos", "albums", "artists", "playlists"}:
        raise ValueError("filter: songs, videos, albums, artists or playlists.")
    return remote(music().search, query, filter=filter, limit=limit_value(limit))[:limit]


@mcp.tool()
def get_playlist(playlist_id: str, limit: int = 50) -> dict:
    """List tracks in a YouTube Music playlist; use videoId for playback."""
    result = remote(music().get_playlist, playlist_id, limit=limit_value(limit))
    result["tracks"] = result.get("tracks", [])[:limit]
    return result


@mcp.tool()
def get_album(browse_id: str) -> dict:
    """Get album metadata and tracks using the browseId returned by search."""
    return remote(music().get_album, browse_id)


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
def get_radio(video_id: str, limit: int = 25) -> dict:
    """Get radio recommendations for a song without changing the queue."""
    from rt_music.player import video_url
    video_url(video_id)
    return remote(music().get_watch_playlist, videoId=video_id, limit=limit_value(limit))


@mcp.tool()
def play_music(video_id: str, enqueue: bool = False) -> dict:
    """Play the best available audio or enqueue it. Acceptance does not confirm playback has started."""
    return player.play(video_id, enqueue)


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
    commands = {"pause": ("set_property", "pause", True),
                "resume": ("set_property", "pause", False), "stop": ("stop",),
                "next": ("playlist-next", "weak"), "previous": ("playlist-prev", "weak"),
                "shuffle": ("playlist-shuffle",), "clear_queue": ("playlist-clear",)}
    if action not in commands:
        raise ValueError("action: pause, resume, stop, next, previous, shuffle or clear_queue.")
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
def edit_queue(action: str, index: int, destination: int = 0) -> list:
    """Remove, move or select a queued item by index (action remove/move/select)."""
    queue = player.queue()
    if not 0 <= index < len(queue):
        raise ValueError("Queue index is out of range.")
    if action == "remove":
        player.command("playlist-remove", index)
    elif action == "move":
        if not 0 <= destination < len(queue):
            raise ValueError("Destination index is out of range.")
        player.command("playlist-move", index, destination)
    elif action == "select":
        player.command("set_property", "playlist-pos", index)
    else:
        raise ValueError("action: remove, move or select.")
    return player.queue()


@mcp.tool()
def enqueue_playlist(playlist_id: str, limit: int = 50) -> dict:
    """Enqueue up to 100 playlist tracks, skipping entries without a valid videoId."""
    from rt_music.player import VIDEO_ID
    playlist = get_playlist(playlist_id, limit)
    ids = [track.get("videoId") for track in playlist.get("tracks", [])]
    ids = [item for item in ids if isinstance(item, str) and VIDEO_ID.fullmatch(item)][:limit_value(limit)]
    for video_id in ids:
        player.play(video_id, enqueue=True)
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
        raise RuntimeError("Cannot inspect local authentication configuration safely.") from None
    result["configured"] = all(result[name].get("private", False)
                               for name in ("cookies.txt", "browser.json"))
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
    result["note"] = "Catalog auth reloaded. Restart the player when convenient to reload playback cookies. No credentials returned."
    return result


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
