# kiosktunes-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://www.python.org/)
[![MCP Ready](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![al4xdev/kiosktunes-mcp MCP server](https://glama.ai/mcp/servers/al4xdev/kiosktunes-mcp/badges/score.svg)](https://glama.ai/mcp/servers/al4xdev/kiosktunes-mcp)

A standalone, zero-bloat music server and **Model Context Protocol (MCP)** tool suite designed for developers, autonomous AI agents, and TTY/terminal power users. 

Stream YouTube Music audio directly to your local hardware using **mpv** and **yt-dlp**, with persistent daemon playback, real-time DSP audio enhancement, automatic taste/history logging for AI agents, and zero GPU/VRAM overhead.

---

## 💡 Why This Exists: The Problem & The Solution

When working in low-resource environments (e.g., pure TTY sessions, heavy build/compilation jobs like Kotlin/Rust, or training/running local LLMs and Diffusion models on your GPU):

1. **Desktop/Browser Bloat:** Opening YouTube or a desktop streaming client consumes **800 MB to 2 GB of RAM** and reserves precious GPU/VRAM for window compositing and video decoding.
2. **Disconnected Chats & Process Lifecycles:** Typical terminal audio scripts run inside your shell session; when an AI agent chat restarts, reconnects, or finishes, the music stops and the queue is lost.
3. **Subpar Audio Compression:** Streaming lossy web audio without hardware equalization often sounds dull, muddy, or lacks dynamic presence.

### The Solution:
- **Detached Daemon Architecture:** A dedicated `mpv` instance runs in background with a Unix IPC socket (`mpv.sock`). Closing the agent, disconnecting chats, or switching TTYs **never interrupts playback**.
- **Real-Time DSP Hardware Enhancement (Zero VRAM):** Rather than slow, heavy AI upscaling (AudioSR) that consumes gigabytes of VRAM, `kiosktunes-mcp` leverages native real-time DSP filters (`crystalizer` for transient attack/air recovery and `extrastereo` for spatial headstage expansion).
- **Persistent Agent Memory & User Taste Profiling:** Every track played is logged to structured `JSONL` format. Users and agents can classify and rate songs on a 0–5 star scale (`rate_music`, `get_user_ratings`) to curate personalized playlists and discover new music based on verified favorites.
- **Compact & Batch-First for LLMs:** High-leverage, polymorphic tools accept single items or lists. Search runs multi-query lookups concurrently, playback defaults to non-interrupting `enqueue=True`, and pruned compact metadata cuts LLM context token usage by over 80%.
- **Lazy Turnkey MCP:** Instant startup with zero background overhead until an audio command is actually dispatched.

---

## 🚀 Key Features

- **21 MCP Tools** for search, playback, batch queueing, volume, seek, radio recommendations, lyrics, history, and taste ratings.
- **Small-Model Optimized:** Polymorphic single/batch operations without tool bloat; compact search outputs keep LLM context clean.
- **Strict Opus Stream Selection:** Prefers raw 48 kHz Opus (`format 251`) without lossy-to-lossy MP3 re-encoding.
- **Zero VRAM footprint:** Keeps your GPU 100% free for LLMs (Ollama/vLLM) and Diffusion models (Flux/SDXL).
- **CLI & Agent Friendly:** Use it via conversational AI agents (Claude Code, Cursor, OpenCode, DSH) or standard terminal CLI.
- **Safe Authentication:** Clean isolation for optional YouTube Music session import without exposing tokens or cookies to chat context.

---

## 📦 System Requirements & Dependencies

`kiosktunes-mcp` is designed to be lightweight by delegating playback to standard system tools rather than embedding bulky multimedia frameworks.

### Prerequisites

| Component | Purpose | Installation |
|---|---|---|
| **Python 3.11+** | Application runtime | Managed via [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh \| sh`) |
| **mpv** | Detached background audio engine | **Arch Linux:** `sudo pacman -S mpv`<br>**Debian / Ubuntu:** `sudo apt install mpv`<br>**Fedora:** `sudo dnf install mpv`<br>**macOS:** `brew install mpv` |
| **FFmpeg** | DSP audio filters (`crystalizer`, `extrastereo`) | Usually bundled with `mpv` on modern distros |
| **Deno** *(Recommended)* | Fast headless JS runtime for YouTube signature deciphering | `curl -fsSL https://deno.land/install.sh \| sh` |

> **Note on PipeWire / PulseAudio:** The player outputs audio through your active user audio server. If running in a raw headless TTY, ensure your user audio daemon (PipeWire/PulseAudio) is running (`systemctl --user status pipewire`).

---

## 🛠️ Quick Start & Installation

Clone the repository and install dependencies using `uv`:

```bash
git clone https://github.com/al4xdev/kiosktunes-mcp.git
cd kiosktunes-mcp
uv sync
```

### Direct CLI Usage

```bash
# Search and play a track immediately
uv run kiosktunes-mcp music play "Perturbator Future Club"

# Playback controls
uv run kiosktunes-mcp music pause
uv run kiosktunes-mcp music resume
uv run kiosktunes-mcp music next
uv run kiosktunes-mcp music volume 85

# Inspect live audio codec, bitrate, and queue
uv run kiosktunes-mcp music status
uv run kiosktunes-mcp music queue

# Rate/like the currently playing track (0.0 to 5.0 score)
uv run kiosktunes-mcp music rate --score 5.0 --notes "Favorite track"

# View rated tracks and listening history
uv run kiosktunes-mcp music ratings --min 4.0
uv run kiosktunes-mcp history
```

---

## 🤖 MCP Agent Integration (Claude, Cursor, OpenCode, DSH)

`kiosktunes-mcp` operates as a standard stdio Model Context Protocol (MCP) server.

### Automatic Setup

Print ready-to-paste configurations for any tool:
```bash
uv run kiosktunes-mcp mcp --config
```

Or write turnkey configuration into your current project:
```bash
uv run kiosktunes-mcp mcp --setup
```

### Community Registries & 1-Click Install

* **[Glama.ai](https://glama.ai/mcp/servers/al4xdev/kiosktunes-mcp):** View verified server health, tool schemas, and connect directly.
* **Smithery CLI:** Install directly into your client of choice without manual configuration:
  ```bash
  npx -y @smithery/cli install @al4xdev/kiosktunes-mcp --client claude
  ```

### Manual Configuration Snippets

#### 1. Claude Code CLI
```bash
claude mcp add music uv -- run --directory /absolute/path/to/kiosktunes-mcp kiosktunes-mcp
```

#### 2. OpenCode / Cursor / DSH / Claude Desktop (`mcp.json`)
Add the following to your agent configuration (`.agents/mcp.json` or `~/.dsh/mcp.json`):

```json
{
  "mcpServers": {
    "music": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/kiosktunes-mcp", "kiosktunes-mcp"]
    }
  }
}
```

---

## 🎵 Complete MCP Tool Catalog

| Category | Tools | Description |
|---|---|---|
| **Discovery** | `search_music`, `get_album`, `get_artist`, `get_radio`, `get_lyrics` | Search songs/albums/artists (compact by default, concurrent multi-query support) and fetch related tracks or lyrics |
| **Playback** | `play_music`, `playback_status`, `control_playback`, `seek_music`, `set_volume`, `set_repeat` | Real-time audio control; non-interrupting `enqueue=True` by default, batch video_id queuing |
| **Queue** | `get_queue`, `edit_queue`, `enqueue_playlist` | Manage, reorder, or batch remove playlist tracks |
| **Intelligence** | `get_listening_history`, `rate_music`, `get_user_ratings` | Log listening activity, rate tracks (0–5), and retrieve taste profiles for AI-powered discovery |
| **Auth & Lifecycle** | `auth_status`, `import_simpmusic_auth`, `shutdown_player` | Safe session inspection and graceful mpv shutdown |

---

## 🎧 Real-Time Audio DSP & Quality Specs

The player configures `mpv` to bypass arbitrary transcoders and apply real-time Psychoacoustic DSP:

```bash
--ytdl-format="bestaudio[acodec=opus]/bestaudio[acodec=m4a]/bestaudio/best"
--af="lavfi=[crystalizer=i=2.0],lavfi=[extrastereo=m=1.1]"
```

- **Bitstream:** Direct Opus stream at 48 kHz (~128-160 kbps VBR).
- **`crystalizer=i=2.0`:** Re-expands dynamic transients and high-frequency harmonics dampened by lossy codecs.
- **`extrastereo=m=1.1`:** Subtle 10% stereo widening designed specifically for headphones.
- **Resource Usage:** < 1% single CPU core, **0 MB VRAM**.

---

## 🔒 Security & Privacy Boundary

- **No Credentials in Diagnostics:** All MCP tool errors and status returns sanitize tokens, cookies, and signed URLs.
- **Local Isolation:** Credentials (if imported) remain in `$XDG_CONFIG_HOME/kiosktunes-mcp/` with `0700/0600` permissions and are never committed or returned through MCP.
- **Safe History & Ratings:** `logs/history.jsonl` and `logs/ratings.jsonl` track solely music metadata (`video_id`, `title`, `artists`, `rating`, `timestamp`), never private credentials.

---

## 🧪 Testing & Verification

Run the comprehensive unit test suite:

```bash
uv run pytest -q
```
*Current test suite: **54 passed tests** covering concurrent multi-query search, compact output, batch playback, reverse queue removal, rating profiles, audio DSP, and authentication sanitization.*

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
