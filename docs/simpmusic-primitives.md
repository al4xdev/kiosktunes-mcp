# SimpMusic primitives: upstream reference for a Python MCP

## Revisions and scope

- [SimpMusic](https://github.com/maxrave-dev/SimpMusic) inspected revision: **`9a93ca8e103d9b66d3f9ec0d91cd833f2a40375a`**.
- Its `core` submodule (`.gitmodules`, [maxrave-dev/core](https://github.com/maxrave-dev/core)) is pinned to **`b9f4ceac52e7c25cb059ea78141784dc164e0161`**. Both the parent tree entry and initialized submodule HEAD were checked.
- This mapping is static source analysis, not a live availability, login, or playback test. No personal credentials or database contents were required for it. An optional ignored `upstream/SimpMusic` checkout is reference material, not a runtime dependency.
- Compose navigation/deep links and internal provider HTTP routes are different interfaces. **The inspected SimpMusic source does not provide a public HTTP player-control API or a ready-made MCP server.** Login-sync HTTP is not a player API.

All source paths below are relative to the upstream checkout, at these revisions. Line references are revision-specific.

| Prefix | Exact path |
|---|---|
| `UI/` | `composeApp/src/commonMain/kotlin/com/maxrave/simpmusic/` |
| `DATA/` | `core/data/src/commonMain/kotlin/com/maxrave/data/` |
| `DOMAIN/` | `core/domain/src/commonMain/kotlin/com/maxrave/domain/` |
| `YTM/` | `core/service/kotlinYtmusicScraper/src/commonMain/kotlin/com/maxrave/kotlinytmusicscraper/` |
| `COMMON/` | `core/common/src/commonMain/kotlin/com/maxrave/common/` |
| `MPV/` | `core/media/media-jvm/src/main/java/com/simpmusic/media_jvm/mpv/` |
| `MEDIA3/` | `core/media/media3/src/main/java/com/maxrave/media3/` |

## Architecture and entry points

Main flow: Compose screen → ViewModel → `DOMAIN/repository/` interface → `DATA/repository/` implementation → `YTM/YouTube.kt` operations/parsing → `YTM/Ytmusic.kt` HTTP/Ktor. Playback uses `DOMAIN/mediaservice/handler/MediaPlayerHandler.kt` and platform backends.

- `UI/App.kt`: external links, overall composition, and player.
- `UI/ui/navigation/graph/AppNavigationGraph.kt:33–150`: `NavHost`, initial Home, Search, Library, MixForYou, Analytics, Wrapped, Fullscreen; incorporates Home/List/Library/Login graphs.
- `UI/ui/navigation/graph/ListScreenGraph.kt:28–97`: typed screen arguments.
- `UI/di/ViewModelModule.kt`: ViewModel composition; UI singletons are not Python network services.

## UI routes and deep links

Typed `@Serializable` destinations under `UI/ui/navigation/destination/` are **not REST endpoints**:

| Destination file | Arguments |
|---|---|
| `home/HomeDestination.kt`, `search/SearchDestination.kt`, `library/LibraryDestination.kt` | None |
| `library/MixForYouDestination.kt` | None; authenticated YouTube session tab |
| `list/AlbumDestination.kt` | `browseId: String` |
| `list/ArtistDestination.kt` | `channelId: String` |
| `list/PlaylistDestination.kt` | `playlistId: String`, `isYourYouTubePlaylist: Boolean = false` |
| `list/BrowseDestination.kt` | `browseId: String`, `params: String? = null`, `title: String? = null` |
| `list/PodcastDestination.kt` | `podcastId: String` |
| `list/LocalPlaylistDestination.kt` | `id: Long` |
| `list/MoreAlbumsDestination.kt` | `id: String`, `type: String = "album"`; also `"single"` |
| `home/MoodDestination.kt` | `params: String` |
| `library/LibraryDynamicPlaylistDestination.kt` | `type: String` |
| `player/FullscreenDestination.kt` | None |
| `login/LoginDestination.kt`, `SpotifyLoginDestination.kt`, `DiscordLoginDestination.kt`, `LastfmLoginDestination.kt` | None |

Other Home destinations include Settings, Notification, RecentlySongs, Credit, AppLog, and ListenTogether. Analytics/Wrapped require local tracking; they are not anonymous public account data.

Actual routing: `UI/App.kt:227–423`, `UI/utils/AppLinks.kt:8–51`.

| Link | Effect |
|---|---|
| `simpmusic://watch?v=<videoId>` / `https://simpmusic.org/app/watch?v=<videoId>` | `SharedViewModel.loadSharedMediaItem`; **starts playback**, not just details |
| `simpmusic://playlist?list=<id>` / `/app/playlist` variant | `OLAK5uy_…` opens an album; `VL…` stays unchanged; other playlist browse IDs get `VL` |
| `simpmusic://album?id=<browseId>` | Album |
| `simpmusic://channel/<UC…>` / `simpmusic://c/<UC…>` / `/app/channel/…` variants | Artist; requires `UC` prefix |
| `simpmusic://library` | Library |
| `simpmusic://library?type=favorite` | Dynamic collection; `type` takes precedence over `tab` |
| `simpmusic://library?tab=wrapped` | Library chip; subject to local tracking |
| `simpmusic://analytics`, `simpmusic://taste` | Analytics or library/Your library; subject to local tracking |
| `simpmusic://notification` | Notifications |
| `wordbyword://lastfm-auth?token=<token>` | Last.fm callback to SharedViewModel, without stacking another login screen |

External links also recognize `watch?v=…`, `youtu.be/<id>`, playlists, and channels. Do not copy permissive host handling into MCP: validate domain and ID type explicitly. No search-query deep link was found; `SearchDestination` has no query argument. Opening a deep link does not return structured search results.

## Provider HTTP: search, browse, and queue

Ktor base: **`https://music.youtube.com/youtubei/v1/`**, `YTM/Ytmusic.kt:220–222`. This is **unofficial InnerTube**, dependent on client context/version and renderer formats, not YouTube Data API. These publicly named routes are implementation references, not supported public API contracts.

| Method and route | `Ytmusic.kt` lines | Body/use |
|---|---|---|
| `POST search` | 286–302 | `SearchBody(context, query, params)`; continuation query parameters `continuation`, `ctoken` |
| `POST music/get_search_suggestions` | 860–871 | `GetSearchSuggestionsBody(context, input)`; no `setLogin` in this method |
| `POST browse` | 749–794 | `BrowseBody(context, browseId, params, continuation)`; charts use country-code `formData` |
| `POST next` | 837–858 | `NextBody(context, videoId, playlistId, playlistSetVideoId, index, params, continuation)`; session enabled |
| `POST browse?ctoken=…&continuation=…&type=next` | 821–835 | `nextCtoken` variant, not search |
| `POST music/get_queue` | 873–886 | `GetQueueBody(context, videoIds, playlistId)` |
| `POST player` | 466–509 | `PlayerBody(context, videoId, playlistId, cpn, playbackContext.contentPlaybackContext.signatureTimestamp)` |
| `GET https://music.youtube.com/sw.js_data` | 888 | Visitor-data material |
| `POST account/account_menu` / `GET https://music.youtube.com/getAccountSwitcherEndpoint` | 890 onward | Private account/validation operations, not automatic account harvesting |

Also present: `playlist/create`, `browse/edit_playlist`, `like/like`, `like/removelike`, `subscription/subscribe`, `subscription/unsubscribe`. These change remote state and are outside a read-only MVP. Legacy autocomplete `http://suggestqueries.google.com/complete/search` exists at line 519; prefer the app's structured suggestion mechanism.

### Search and suggestions

- `UI/viewModel/SearchViewModel.kt:57–66,190–337`: `ALL`, `SONGS`, `VIDEOS`, `ALBUMS`, `ARTISTS`, `PLAYLISTS`, `FEATURED_PLAYLISTS`, `PODCASTS`. `searchAll` performs **seven parallel searches**, not one ALL-filter request. It combines up to three artists, then songs, videos, albums, community playlists, featured playlists, and podcasts. Individual failures can disappear while the aggregate reports Success.
- `DATA/repository/SearchRepositoryImpl.kt` selects filters and `DATA/parser/search/` parsers. Song/video/podcast requests load the first page and up to two continuations, not unlimited results.
- `YTM/YouTube.kt:275–353` parses the last music shelf of the first tab; continuation uses `continuationContents.musicShelfContinuation`, returning items and a token.
- `YTM/YouTube.kt:1968–1978` defines opaque, revisioned filters:

| Kind | `params` |
|---|---|
| Song | `EgWKAQIIAWoKEAkQBRAKEAMQBA%3D%3D` |
| Video | `EgWKAQIQAWoKEAkQChAFEAMQBA%3D%3D` |
| Album | `EgWKAQIYAWoKEAkQChAFEAMQBA%3D%3D` |
| Artist | `EgWKAQIgAWoKEAkQChAFEAMQBA%3D%3D` |
| Featured playlist | `EgeKAQQoADgBagwQDhAKEAMQBRAJEAQ%3D` |
| Community playlist | `EgeKAQQoAEABagoQAxAEEAoQCRAF` |
| Podcast | `EgWKAQJQAWoIEBAQERADEBU%3D` |

`SearchViewModel.kt:339–360` returns both `queries` and `recommendedItems`. Upstream local search-history persistence should not become an implicit MCP search side effect.

### Browse, home, categories, and radio

- `DATA/repository/HomeRepositoryImpl.kt:64–73,213–439`: home `FEmusic_home`, charts `FEmusic_charts`; home retains continuation/appends shelves. Moods serve cache before network and preserve section order.
- `YTM/YouTube.kt:1019–1045` and subsequent parsers extract generic browse titles/sections (grid, carousel, music shelf, playlist shelf, mood buttons). Unsupported renderers can yield empty results; do not claim complete page support.
- `UI/viewModel/BrowseViewModel.kt:20–34`: `HomeRepository.getBrowsePage(browseId, params)` needs nonempty content or moods for Success.
- `MoodViewModel.kt:42–49` → `getMoodData(params)`; `HomeRepositoryImpl.kt:331–402` uses `FEmusic_moods_and_genres_category` with opaque `params`. Category browse references `FEmusic_moods_and_genres`.
- `SearchViewModel.kt:130–154` loads categories once per ViewModel; covers load on demand, deduplicated by params.
- `YTM/YouTube.kt:1738–1867` reads `playlistPanelContinuation` or the initial panel and recursively follows `automixPreviewVideoRenderer`, preserving lyrics/related endpoints. `NextPage.fromPlaylistPanelContent` handles wrappers, primary renditions, and counterparts needed for authenticated sessions.
- `BaseViewModel.kt:151–175` calls `SongRepository.getRadioFromEndpoint`, preserves tokens, distinguishes RADIO/PLAYLIST by ID, sets the queue, and starts the first track. `SharedViewModel.kt:853–895` creates `RDAMVM<videoId>` radio, trying local metadata before `StreamRepository.getFullMetadata`. Queue, browse, and video IDs are distinct; do not indiscriminately prefix radio IDs with `VL`.

## Playback, extraction, and actual quality

### Backends and state

- `UI/viewModel/base/BaseViewModel.kt:121–142`: `reset`, `setQueueData`, `loadMediaItem`, `shufflePlaylist`.
- `SharedViewModel.kt:897–1027`: metadata/insertion → `addMediaItem(playWhenReady)` → related radio or album/playlist; events include PlayPause, Next, Previous, SkipToPrevious, Forward, Backward, Stop, UpdateProgress, Repeat, Shuffle, ToggleLike, UpdateVolume.
- States include `queueData`, `nowPlayingState`, `controlState`, `simpleMediaState`, `sleepTimerState`. A resolved URL is **not** proof of audible playback.
- Android: `core/data/src/androidMain/kotlin/com/maxrave/data/mediaservice/MediaServiceHandlerImpl.kt`, `MEDIA3/exoplayer/CrossfadeExoPlayerAdapter.kt`, `MEDIA3/di/Media3ServiceModule.kt`, `MEDIA3/service/mediasourcefactory/MergingMediaSourceFactory.kt` (merges audio/video).
- Desktop: `core/data/src/jvmMain/kotlin/com/maxrave/data/mediaservice/JvmMediaPlayerHandlerImpl.kt`; `MPV/MpvPlayerAdapter.kt:3120–3232` tries local download, a resolved format checked for 403, then extraction. `MPV/MpvLibrary.kt:652–684` builds EDL for separate audio/video. The backend is libmpv/JNA, not VLC.

### Extraction pipeline

1. `DATA/repository/StreamRepositoryImpl.kt:86–306` requests `YouTube.player`, chooses a format, and stores `NewFormatEntity` bitrate/sampleRate/codecs/contentLength/expiry/URLs.
2. `YTM/YouTube.kt:1489–1615` calls WEB_REMIX player, creates a 16-character CPN, handles live streams, and merges extractor URLs with player metadata by itag.
3. `YTM/YouTube.kt:1320–1424` requires playability OK, orders audio-language variants, injects extractor URLs, and checks a random URL for 403. Receiving `/player` JSON alone is insufficient.
4. Desktop `core/service/kotlinYtmusicScraper/src/jvmMain/kotlin/com/maxrave/kotlinytmusicscraper/extractor/Extractor.jvm.kt:33–61`: **PipePipe + local Faraday → PipePipe with remote decoder `api.pipepipe.dev` → BravePipe**. `YTM/cipher/FaradayCipherEngine.kt` and adapters handle player-JS challenges. A remote decoder is an external dependency/privacy consideration, not a necessary MCP feature.
5. Live uses HLS, without normal itag ranking/persistence. WEB live segments can fail with 403; there is a special anonymous path and extractor fallback.

### Meaning of upstream “highest”

Normative sources: `COMMON/Config.kt:266–362`, `DATA/repository/StreamRepositoryImpl.kt:94–175`.

| Stored preference (upstream spelling) | itag |
|---|---:|
| `Low - 66kps` | 250 (Opus) |
| `Medium - 129kps` | 251 (Opus) |
| `High Opus - 256kps (YT Premium)` | **774** |
| `High AAC - 256kps (YT Premium)` | **141** |

- Selection is **not `maxBy(bitrate)`**: it looks for the configured itag and tries 141 as the twin of 774, or vice versa. Non-twin qualities first try an audio-marked format with a URL.
- If selection fails, global `lastOrNull` with a URL is used. For High with neither twin, it does **not** first try any audio format; fallback can select an unsuitable format. Do not copy that behavior into Python.
- Input order is `formats` then `adaptiveFormats`, filtered by nonempty URL; order is not a quality ranking. Muxed manifests are ranked by width, not audio bitrate.
- Legacy `High - 256kps (YT Premium)` migrates to High Opus; invalid/null values normalize to Low. Download and streaming preferences differ.
- 256 kbps options depend on formats actually served and account entitlement. UI string `prefer_320kbps_stream` and historical AutoMix comments do not establish a functional 320 kbps selection branch. Tidal is queried for **BPM/key/keyScale** (`StreamRepositoryImpl.kt:191–222`), not replacement 320 kbps audio.
- `UI/ui/screen/player/content/NowPlayingContentState.kt:82–101` displays selected-format bitrate/sample rate without inventing missing fields.

Standalone `simp_mcp` instead uses yt-dlp **`bestaudio/best`**. Its observed baseline was **Opus 251, approximately 134.492 kbps, 48 kHz**. Neither that observation nor upstream preference labels guarantee Premium, 256/320 kbps, lossless, or upsampling. See [verification](verification.md).

## Authentication and security references

These are source mechanisms, not permission to retrieve another application's stored session:

- Android `UI/ui/screen/login/LogInScreen.kt:91–159` opens `Config.LOG_IN_URL`, captures cookies at `Config.YOUTUBE_MUSIC_MAIN_URL`, calls `SettingsViewModel.addAccount`, and clears WebView cookies. Android implementation: `composeApp/src/androidMain/kotlin/com/maxrave/simpmusic/expect/ui/Cookies.android.kt:17–71`.
- `SettingsViewModel.kt:1535–1623` stores accounts with `pageId/authUser`, chooses an active account, and writes Netscape `ytdlp-cookie.txt`.
- `YTM/Ytmusic.kt:228–273` sets client headers, `X-Goog-Authuser`, `X-Goog-Pageid`, `x-origin`, Cookie, and `Authorization: SAPISIDHASH …`; SHA-1 input is timestamp + cookie + origin. Review rather than transplant the cookie OR guard/fallback inconsistency and division of `epochSeconds` by 1000. Authorization-hash logging must not be reproduced.
- Spotify `LogInViewModel.kt:29–41` captures `sp_dc` into DataStore. This is not public OAuth and must never be returned through MCP.
- Desktop `composeApp/src/jvmMain/kotlin/com/maxrave/simpmusic/expect/ui/Cookies.jvm.kt:44–78` is a guidance-link placeholder, not a working WebView.
- Login-sync `LoginSyncSenderViewModel.kt` requires scan → Trust → selection → send; `LoginSyncHostViewModel.kt` expires after five minutes. `core/service/loginSync/src/commonMain/kotlin/org/simpmusic/loginsync/LoginSyncWire.kt` uses invitation `simpmusic://login-sync?h=<ip>&p=<port>&k=<key>`, 32-byte key, 12-byte nonce, AES-256-GCM/128-bit tag, and per-message/direction AAD. JVM routes: `POST /v1/hello`, `/v1/logins`, `/v1/cancel`. Invitations contain secrets: do not log/publish QR codes or automate session transfer.
- Last.fm `LogInViewModel.kt:90–148` uses browser approval and token-to-session exchange with callback/manual input, not a password. Discord Android WebView token capture should not be reproduced in a music MCP.

The standalone [authentication interface](auth.md) uses explicit local import, keeps credentials outside the repository in the compatibility `rt-music` config directory, and exposes only safe metadata. MCP import uses a fixed SimpMusic source, boolean `force`, and nonnegative `auth_user`; arbitrary paths and credential-returning tools are excluded.

## Licensing and reuse boundaries

Upstream `LICENSE` and `core/LICENSE` contain **GNU GPL version 3**. License text alone does not resolve every file's SPDX distinction between `GPL-3.0-only` and `GPL-3.0-or-later`; check origin-specific notices before publishing.

- Copying or porting GPL Kotlin to Python does not remove copyleft. Distribution of a derivative work requires preserving notices/licenses and providing corresponding source under GPLv3; review integration/linking and extractor/dependency licenses separately.
- A separate process is not an automatic exemption: program independence must be real. Independently implementing behavior/contracts without incorporating source still requires provenance and legal review where appropriate.
- Private use and distribution differ. GPLv3 is not AGPL and does not by itself impose source-publication obligations merely for network use; this does not settle other obligations.
- Software licensing grants no rights to recordings or content redistribution, and does not replace YouTube/Spotify/Tidal terms. Internal APIs may change, block access, or require authorization. Do not promise Premium access without entitlement, restriction bypass, or unauthorized downloads.

## Python design lessons and proposed extensions

The following is **design guidance, not a list of implemented tools**. Current tool names are listed in the [README](../README.md). Separate `CatalogProvider`, `StreamResolver`, and `PlaybackBackend`; Kotlin repositories describe boundaries, not directly importable Python components.

| Proposed capability | Upstream reference | Contract |
|---|---|---|
| Search/suggestions | SearchRepository; `search/searchContinuation`; `music/get_search_suggestions` | Typed results, bounded opaque cursors, `{queries, recommended_items}`, no implicit history writes |
| Browse/categories | HomeRepository/BrowseViewModel; moods/genres | Ordered sections and opaque params; declare continuation only when supported |
| Album/artist/playlist | Typed destinations and repositories | Distinct ID types; `VL` only where the browse adapter requires it |
| Radio | SongRepository; `YouTube.next` | Tracks, cursor, counterpart, music/video; preserve wrappers/automix and bound recursion |
| Resolve | StreamRepository | Temporary stream handle, expiry, actual format, fallback reason; does not start playback |
| Play/state/queue | MediaPlayerHandler and Flow states | Explicit local side effect; snapshots of track, queue, position, playing/loading; no cookie/tracking URLs |
| Pause/resume/next/previous/seek/volume | PlayerEvent | Idempotent where possible, bounded input, confirmed backend |
| Authentication status | Login state | Safe metadata only; no names, emails, cookies, or tokens |

Recommended constraints:

1. Use maintained Python adapters (`ytmusicapi`, `yt-dlp`) and `uv`; review their versions/licenses independently. These are standalone choices, not dependencies discovered in the Kotlin clone.
2. Model tracks, browse sections, watch endpoints, cursor pages, and actual resolved formats explicitly, including codec, bitrate, sample rate, expiry, and source when known.
3. A general “highest” policy should consider only eligible available audio, respect language/codec/entitlement, report downgrades, and never rank by itag number or invent bitrate from a label. Such a policy would correct upstream fallback, not duplicate it; the present standalone selector remains `bestaudio/best`.
4. Keep local playback separate (for example mpv IPC). Deep links are consented handoff, not a replacement for catalog/control/state. Never execute title/ID-derived shell commands or arbitrary URLs.
5. Namespace catalog caches by locale/region/session. Bound cursors and resolver retries; renew expired/403 streams. Live needs fresh manifests and no guaranteed duration/seek contract.
6. Authentication must be explicitly owner-authorized. Do not automatically search preferences, cookie files, browser profiles, keyrings, or login-sync invitations. Never expose secrets in MCP responses/logs/prompts.
7. Do not return googlevideo URLs by default: they can carry IP/sensitive parameters. Prefer opaque handles, finite expiry, and no redistribution. Remote tracking, likes, subscriptions, scrobbling, and account export are out of scope by default.
8. Provide timeouts, rate limiting, cancellation, and structured failures such as `AUTH_REQUIRED`, `NOT_AVAILABLE`, `UPSTREAM_CHANGED`, `RATE_LIMITED`, `STREAM_EXPIRED`, `PLAYBACK_BACKEND_UNAVAILABLE`. Aggregate searches should disclose partial failures.

Recommended fixtures are synthetic or public, never personal authenticated captures: search pagination; empty/unknown browse renderers; next wrappers/counterparts; 774 present, 141 only, neither twin, missing bitrate; legacy quality; original/dubbed audio; expiry/403; live HLS; playback controls/queue; and header/callback/URL redaction. Report the **actual selected format**, not just a requested preference.

The most reusable lesson is the separation of catalog/browse → endpoints/queue → resolver → player, with explicit ID and continuation models. Upstream's highest configured option is conditional 256 kbps Opus/AAC with itag-specific fallback, not guaranteed 320 kbps or a general highest-quality algorithm. A standalone MCP needs its own adapters, authorization boundaries, license review, and unavailable-format handling.
