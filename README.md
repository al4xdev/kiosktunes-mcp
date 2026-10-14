# simp_mcp

A standalone Python music CLI and **stdio MCP server** for YouTube Music discovery and local playback through **mpv + yt-dlp**. No player window is required. The player runs separately from the MCP client: closing or reconnecting the chat does not interrupt music or discard the queue. `shutdown_player` stops the player; its queue does not survive shutdown or reboot.

The project is named **simp_mcp**, and its entry script is **`simp-mcp`**. The Python module remains **`rt_music`** for compatibility.

## Setup and CLI

Install **uv, mpv, and Deno** on Linux. Deno supplies the JavaScript runtime used by YouTube extraction; `yt-dlp[default]` includes the official `yt-dlp-ejs` solver.

```fish
cd ~/git/my/simp_mcp
uv sync
uv run simp-mcp music play "Daft Punk Get Lucky"
uv run simp-mcp music pause
uv run simp-mcp music resume
uv run simp-mcp music next
uv run simp-mcp music last
uv run simp-mcp music volume 40
uv run simp-mcp music status
uv run simp-mcp music queue
```

Use `uv run simp-mcp music --help` for the complete command list. Playback is asynchronous: an accepted request is not proof of decoded or audible audio. Check status after loading.

## MCP integration

```fish
uv run simp-mcp
```

With no subcommand, this starts the **stdio protocol server**, not an interactive prompt. It may remain silent while waiting for a client.

Configure a client with the following portable command shape, replacing the placeholder with the absolute checkout path:

```json
{
  "mcpServers": {
    "music": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/simp_mcp", "simp-mcp"]
    }
  }
}
```

See also [mcp-config.json](mcp-config.json). The client must be able to find `uv` on its PATH. Reconnect an existing MCP session after changing tools or authentication. No global client configuration is modified automatically.

| Group | Tools |
|---|---|
| Discovery | `search_music`, `get_album`, `get_artist`, `get_radio`, `get_lyrics` |
| Library/playlists | `get_playlist`, `get_library_playlists`, `enqueue_playlist` |
| Playback | `play_music`, `playback_status`, `control_playback`, `seek_music`, `set_volume`, `set_repeat` |
| Queue | `get_queue`, `edit_queue` |
| Authentication | `auth_status`, `import_simpmusic_auth` |
| Shutdown | `shutdown_player` |

`play_music` accepts a **video_id**, not an arbitrary URL: search first and use a returned `videoId`. `enqueue=true` adds without interrupting the current track. `clear_queue` stops playback and removes the current track as well as pending items; `stop` unloads playback from mpv.

Authentication tools return safe metadata only, **never cookies, tokens, authorization headers, or credentials**. `import_simpmusic_auth` imports only the fixed local SimpMusic source, accepts a boolean `force` and a nonnegative `auth_user` account index, and does not accept arbitrary filesystem paths. Importing a session requires explicit user approval; see [authentication](docs/auth.md).

### DSH /music integration

The **DSH plugin is a separate project**, not part of this MCP server. It provides `/music` and invokes the CLI. Its default project discovery path is `~/git/my/simp_mcp`; set `SIMP_MCP_PROJECT` to override that location. DSH commands and MCP tools are distinct interfaces to the same standalone player.

## Authentication

Authentication is optional for public discovery, but account-library operations require a valid session. To reuse a local SimpMusic YouTube session deliberately:

```fish
uv run simp-mcp auth status
uv run simp-mcp auth import-simpmusic
# Replace existing credentials only when intended:
uv run simp-mcp auth import-simpmusic --force
```

Credentials remain **outside the repository** in `$XDG_CONFIG_HOME/rt-music/`, falling back to `~/.config/rt-music/`. The legacy directory name is retained for compatibility. The directory is mode `0700`, and credential files are mode `0600`. The importer uses YouTube session cookies, not recovered Google OAuth refresh tokens; it excludes general Google, Spotify, and Tidal credentials.

After reimporting, reconnect MCP and use `shutdown_player` before the next playback so the player reloads cookies. Never send credential files to chat or commit them. See [authentication and security boundaries](docs/auth.md).

## Audio quality

The resolver selects **`bestaudio/best`**, without MP3 transcoding or deliberate bitrate reduction. This means the best stream made available for the particular track/session, **not guaranteed Premium, 256/320 kbps, or lossless audio**. Track, region, account entitlement, codec, and extractor behavior affect availability. `playback_status` reports actual codec and sample rate; mpv may not know the bitrate.

The verified baseline selected **Opus, format 251, approximately 134.492 kbps at 48 kHz** for a public track. This is an observed result, not a universal maximum. Automated network checks used silent output; actual speaker playback was confirmed separately by the user later. See [verification and limitations](docs/verification.md).

The implementation uses maintained Python libraries (`ytmusicapi`, `yt-dlp`), rather than embedding the Kotlin app or relying on its public fallback services. [The upstream primitive map](docs/simpmusic-primitives.md) records exact revisions, routes, quality behavior, and GPL considerations.

## Tests and maintenance

```fish
uv run pytest -q
uv run ruff check src tests
# Refresh the extractor when YouTube changes:
uv lock --upgrade-package yt-dlp
uv sync
```

Resolved dependencies are recorded in `uv.lock`. The migrated project passes **41 Python tests and lint**; the separate DSH plugin passes **14 tests**, including native command registration. The MCP exposes **19 tools**, including safe auth status/import. Offline tests do not call external services or prove speaker output. [Verification](docs/verification.md) separates reproducible checks from live evidence.

mpv uses its default audio output (PipeWire/PulseAudio/ALSA); keep the user audio service available when working in a TTY. This MVP does not implement offline downloads, library writes, scrobbling, an equalizer, or synchronized lyrics. YouTube login and extraction are not guaranteed public Google APIs and may require updates or reauthentication.

## License and publishing

Original code in this repository is [MIT licensed](LICENSE). SimpMusic and its core are GPLv3 upstream references; no Kotlin implementation is bundled here. Dependencies and mpv retain their own licenses. Do not add the ignored upstream checkout or local auth files to a public commit. See [SECURITY.md](SECURITY.md).
