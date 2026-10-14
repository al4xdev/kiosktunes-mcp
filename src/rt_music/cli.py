"""Deterministic CLI for terminal and DSH controls; default entry is MCP stdio."""

from __future__ import annotations

import argparse
import json
import sys

from rt_music import auth, server
from rt_music.player import VIDEO_ID


def music_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simp-mcp music", description="Control your local persistent music player.")
    commands = parser.add_subparsers(dest="command")
    play = commands.add_parser("play", help="Search and play a song; with no query, resume playback")
    play.add_argument("query", nargs="*", help="Search query or a video ID")
    play.add_argument("--id", dest="video_id", help="Use an exact YouTube video ID")
    play.add_argument("--enqueue", action="store_true", help="Append without interrupting the current song")
    search = commands.add_parser("search", help="Search without starting playback")
    search.add_argument("query", nargs="+")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--filter", choices=["songs", "videos", "albums", "artists", "playlists"], default="songs")
    for name in ("pause", "resume", "stop", "next", "last", "previous", "shuffle", "clear", "status", "queue", "shutdown", "help"):
        commands.add_parser(name)
    volume = commands.add_parser("volume", help="Set volume from 0 to 100")
    volume.add_argument("value", type=float)
    seek = commands.add_parser("seek", help="Seek in seconds")
    seek.add_argument("seconds", type=float)
    seek.add_argument("--relative", action="store_true")
    repeat = commands.add_parser("repeat", help="Repeat a track or the queue")
    repeat.add_argument("mode", choices=["off", "one", "all"])
    playlist = commands.add_parser("playlist", help="Enqueue a YouTube Music playlist")
    playlist.add_argument("playlist_id")
    playlist.add_argument("--limit", type=int, default=50)
    edit = commands.add_parser("edit", help="Remove, move or select a queue item")
    edit.add_argument("action", choices=["remove", "move", "select"])
    edit.add_argument("index", type=int)
    edit.add_argument("--destination", type=int, default=0)
    authentication = commands.add_parser("auth", help="Local auth metadata or fixed-source SimpMusic import; no secrets")
    authentication.add_argument("action", choices=["status", "import-simpmusic"])
    authentication.add_argument("--force", action="store_true")
    authentication.add_argument("--auth-user", type=int, default=0)
    return parser


def execute(args: argparse.Namespace):
    command = args.command
    if command == "play":
        query = " ".join(args.query).strip()
        if args.video_id and query:
            raise ValueError("Choose either a search query or --id, not both.")
        if not args.video_id and not query:
            if args.enqueue:
                raise ValueError("Provide a query or --id to enqueue a song.")
            return server.control_playback("resume")
        video_id = args.video_id
        selected = None
        if video_id is None and VIDEO_ID.fullmatch(query):
            video_id = query
        if video_id is None:
            results = server.search_music(query, limit=10)
            selected = next((item for item in results if VIDEO_ID.fullmatch(item.get("videoId") or "")), None)
            if selected is None:
                raise ValueError("No playable songs found. Try a more specific query.")
            video_id = selected["videoId"]
        result = server.play_music(video_id, enqueue=args.enqueue)
        if selected:
            result["selected_title"] = selected.get("title")
        return result
    if command == "search":
        return server.search_music(" ".join(args.query), filter=args.filter, limit=args.limit)
    if command in {"pause", "resume", "stop", "next", "previous", "last", "shuffle", "clear"}:
        return server.control_playback({"last": "previous", "clear": "clear_queue"}.get(command, command))
    if command == "status":
        return server.playback_status()
    if command == "queue":
        return server.get_queue()
    if command == "volume":
        return server.set_volume(args.value)
    if command == "seek":
        return server.seek_music(args.seconds, relative=args.relative)
    if command == "repeat":
        return server.set_repeat(args.mode)
    if command == "playlist":
        return server.enqueue_playlist(args.playlist_id, limit=args.limit)
    if command == "edit":
        return server.edit_queue(args.action, args.index, args.destination)
    if command == "shutdown":
        return server.shutdown_player()
    if command == "auth":
        if args.action == "status":
            return server.auth_status()
        return server.import_simpmusic_auth(force=args.force, auth_user=args.auth_user)
    raise ValueError("Unknown music command.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ["mcp"]:
        server.main()
        return 0
    if argv[0] == "auth":
        return auth.main(argv[1:])
    if argv[0] in {"-h", "--help", "help"}:
        print("Usage: simp-mcp [mcp | music COMMAND | auth COMMAND]\nNo arguments starts the MCP stdio server.\nUse simp-mcp music --help for direct controls.")
        return 0
    if argv[0] != "music":
        print("Unknown mode. Use simp-mcp --help.", file=sys.stderr)
        return 2
    parser = music_parser()
    args = parser.parse_args(argv[1:])
    if args.command in {None, "help"}:
        parser.print_help()
        return 0
    try:
        result = execute(args)
    except (ValueError, RuntimeError, auth.AuthError) as error:
        print(f"Music error: {error}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 -- keep unexpected third-party errors out of chat/terminal output
        print("Music command failed. Check the player, network and local configuration.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
