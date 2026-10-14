# Verification and limitations

## Reproducible offline checks

From the standalone checkout:

```fish
uv sync
uv run pytest -q
uv run ruff check src tests
uv run simp-mcp --help
uv run simp-mcp music --help
uv run simp-mcp auth status
```

**Current standalone validation: 41 passing Python tests and passing lint.** The earlier 26-test baseline was rerun with CLI and safe-auth contract tests added. The separate DSH plugin passed 14 tests, including native command lifecycle, real subprocess pipes, cancellation, Unicode output and secret-safe logging.

Baseline coverage included input validation (IDs, volume, search), event-aware mpv IPC, private runtime/config directories, synthetic authentication/domain/expiry/permissions/symlink/no-clobber cases, credential-free failures, real subprocess MCP protocol, hard queue limits, signed-URL redaction, complete queue clearing, and duplicate/orphan process prevention. Offline tests do not call external services or play audio.

For current MCP validation, connect a stdio client using [the README configuration](../README.md), list tools, and verify that authentication status/import return only safe metadata. Import must use the fixed SimpMusic source, boolean `force`, and nonnegative `auth_user`; reject arbitrary paths and invalid input. Use synthetic credentials for automated tests, not personal session captures.

## Migration and direct DSH validation

- The migrated environment exposes 19 MCP tools. A repeated end-to-end test decoded real Opus/48 kHz audio with volume zero, exercised pause/seek/enqueue/repeat/reordering/clear, preserved queue/player across two MCP sessions, and explicitly shut down its isolated test player.
- A native DSH command registry invoked `/music status` against the real standalone CLI successfully, with zero model requests and no raw input recorded in session command events.
- The music plugin was registered in the local dsh-tui and companion host profiles using narrow edits. A fresh DSH process is needed to load it. Full profile generation was not applied because it also contained unrelated pending changes.
- Gitignore checks confirmed common credential filenames and local runtime/upstream artifacts are ignored. Credentials remain outside the checkout; no actual credential fixture is distributed.

## Previously verified live baseline

These observations are historical evidence, not promises that upstream services or every environment will behave identically:

- Anonymous YouTube Music search for “Daft Punk Get Lucky” returned tracks with valid video IDs.
- An explicitly authorized local session import produced private configuration files (directory `0700`, files `0600`); an authenticated library request succeeded without displaying private library contents. General Google, Spotify, and Tidal credentials were excluded; no OAuth refresh token was imported.
- Resolution of public track **`4D7u5KF7SP8`** selected **format 251, Opus, approximately 134.492 kbps nominal bitrate, 48 kHz, WebM**, without transcoding. This is a track/session-specific observation, not a universal service maximum or proof of Premium availability.
- Real mpv IPC loaded a silent PCM fixture and verified pause, seek, volume, and queue behavior with `ao=null`.
- Real network playback decoded the public track in Opus/48 kHz with position advancing, using silent `ao=null` output.
- End-to-end MCP verified playback loading/decoding, zero volume, pause, seek, enqueue, repeat, and queue reordering. Closing one MCP session preserved the player/queue; another session recovered both. Complete queue clearing and explicit player shutdown were also verified. No current tool count is claimed here.
- **Actual speaker playback was confirmed separately by the user later.** That is distinct from automated silent decoding tests and is not a general hardware compatibility result.

The original private smoke reports/scripts are not distribution artifacts or prerequisites. Do not publish workstation reports, credentials, authorization headers, signed stream URLs, or private library/account data.

## Repeating a live smoke check

1. Install mpv and Deno, run `uv sync`, and ensure the user audio service is available.
2. Search/play a public query with `uv run simp-mcp music play "Daft Punk Get Lucky"`; check `music status` for actual codec, sample rate, and advancing position.
3. Exercise `music pause`, `music resume`, `music volume 0`, and `music queue`. Use an isolated player/test queue when testing destructive queue operations; do not alter an existing listening session without consent.
4. Connect/reconnect a stdio MCP client and check that player state survives client closure. Explicitly shut down the test player afterward.
5. If account-library validation is needed, obtain owner approval, import through `simp-mcp auth import-simpmusic`, and check safe status metadata. Test the library without printing private results.
6. Check actual audible output separately and with an appropriate volume; `ao=null`, zero-volume tests, codec detection, and playback clocks alone cannot prove speaker output.

Keep reports limited to pass/fail, safe metadata, and actual format facts. Do not convert authenticated network responses into test fixtures.

## Limits

- Network behavior has not been exhaustively tested for all album/artist/radio/lyrics cases, very large playlists, live streams, multiple/brand accounts, expired sessions, region changes, or anti-bot challenges.
- The upstream reference revisions are SimpMusic **`9a93ca8e103d9b66d3f9ec0d91cd833f2a40375a`** and core **`b9f4ceac52e7c25cb059ea78141784dc164e0161`**; they do not prove that an installed desktop binary matches. See [source and route mapping](simpmusic-primitives.md).
- The official yt-dlp JavaScript solver (`yt-dlp[default]`, including `yt-dlp-ejs`) and an available runtime are necessary for the verified extraction path. YouTube changes can require dependency updates or reauthentication.
- A queue persists only while the player remains alive, not across reboot or explicit shutdown. No global chat-client configuration is modified automatically.
- `bestaudio/best` selects from formats actually available. No Premium/DRM bypass was verified or promised; 256 kbps, 320 kbps, and lossless are not guaranteed.
