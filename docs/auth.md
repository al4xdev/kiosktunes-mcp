# Local authentication

## Source and scope

SimpMusic desktop data uses `~/.simpmusic/`. The relevant export is **`~/.simpmusic/ytdlp-cookie.txt`**, a Netscape cookie file that may contain both YouTube and broader Google session cookies. Treat it as a bearer credential, not an ordinary setting. This importer does not read account rows, AndroidX preferences, browser profiles, keyrings, or unrelated service credentials, and never selects old backups automatically.

Upstream evidence at the [documented revisions](simpmusic-primitives.md):

- `composeApp/src/jvmMain/kotlin/com/maxrave/simpmusic/DesktopApp.kt` references `~/.simpmusic/settings.preferences_pb`.
- `composeApp/src/commonMain/kotlin/com/maxrave/simpmusic/viewModel/SettingsViewModel.kt` stores the Cookie header in preferences/account cache, stores account-specific Netscape exports, and writes `ytdlp-cookie.txt` during sign-in/account switching.

This is **session-cookie authentication**, not import of a Google OAuth refresh token. The upstream checkout establishes architecture, not the version of any installed desktop binary.

## CLI

Inspect configured authentication without displaying credentials:

```fish
uv run kiosktunes-mcp auth status
```

After explicitly deciding to reuse the local SimpMusic session:

```fish
uv run kiosktunes-mcp auth import-simpmusic
# Replace existing credentials only when intended:
uv run kiosktunes-mcp auth import-simpmusic --force
# Select a nonnegative account index if necessary:
uv run kiosktunes-mcp auth import-simpmusic --auth-user 0
```

`kiosktunes-mcp` is the public entry script. Use `uv run kiosktunes-mcp auth --help` for available CLI inspection options.

The import writes `$XDG_CONFIG_HOME/kiosktunes-mcp/cookies.txt` and `browser.json`, falling back to `~/.config/kiosktunes-mcp/`. `XDG_CONFIG_HOME` must be absolute. The directory is mode `0700`; files are mode `0600`. `cookies.txt` is used by yt-dlp/mpv, while `browser.json` is used by ytmusicapi. Existing files are not replaced without `--force`; unsafe symlink/non-regular destinations remain rejected even with replacement enabled.

The source must be a regular file owned by the current user, not a final-component symlink, and at most 1 MiB. Only unexpired cookies whose domain rules cover `music.youtube.com` are retained. General Google/account cookies, country-specific Google domains, and unrelated YouTube subdomains are excluded. HttpOnly metadata and scope are preserved. Browser authentication requires a valid secure root-path `__Secure-3PAPISID` cookie. Errors must not disclose credential values.

`--auth-user N` is a nonnegative Google account index, defaulting to `0`. It does **not** automatically reproduce SimpMusic's selected account or brand/channel `page_id`. Multi-account and brand-account behavior require separate verification, potentially including ytmusicapi's `user` parameter; no account IDs are harvested from the database.

Import makes no network calls and does not log in/out, refresh tokens, change the remote library, or play music. Local structural validity does not prove that a session is still accepted remotely.

## Safe MCP tools

- **`auth_status`** returns safe configuration/permission metadata, not tokens, Cookie values, authorization headers, account names, or credential-bearing payloads.
- **`import_simpmusic_auth`** deliberately imports the **fixed** `~/.simpmusic/ytdlp-cookie.txt` source. Its controls are boolean `force` and nonnegative integer `auth_user` (default `0`). It accepts **no arbitrary source or destination path** and returns only safe import metadata.

Ask the owner before invoking the import: stored credentials in another application are not implicit permission to reuse the session. Never pass secrets as MCP arguments, resources, prompts, or tool results. Do not infer remote authentication success from `auth_status` alone.

After reimporting, reconnect the MCP client and use `shutdown_player` before the next playback so mpv reloads cookies.

## Signing and security boundaries

The browser configuration includes a generated `SAPISIDHASH` to identify browser mode. ytmusicapi regenerates timestamped Authorization headers for requests. References: [browser authentication](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html), [auth-mode detection](https://github.com/sigma67/ytmusicapi/blob/master/ytmusicapi/auth/auth_parse.py), and [request-time signing](https://github.com/sigma67/ytmusicapi/blob/master/ytmusicapi/ytmusic.py).

- Domain filtering reduces disclosure but does not turn session cookies into narrowly scoped OAuth credentials. Theft can compromise the session/account. Never paste output files into chat, logs, bug reports, or public backups; keep them out of Git.
- Expiry metadata cannot establish server-side validity. Logout, security changes, rotation, and anti-bot checks can invalidate structurally valid cookies.
- Publication uses private temporary files, fsync, a cooperating importer lock, and no-clobber hard links without `--force`. Each file is atomic, but the two-file import is not one filesystem transaction: a disk failure can leave only one file updated. Check safe metadata after errors before explicitly retrying replacement.
- SimpMusic source data stays untouched. Unrelated Google, Spotify, and Tidal credentials are unsupported; the importer does not search the home directory, browser profiles, password stores, or keyrings.
- Authentication APIs must never return, log, or stringify credential-bearing payloads. Status/import results contain metadata only, and internal Cookie values must remain excluded from representations.
