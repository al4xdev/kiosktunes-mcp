# Security

This project controls a local player and may use bearer session cookies from your own SimpMusic installation. It does not run a public HTTP authentication endpoint. MCP uses local stdio, and mpv IPC is inside an owner-only runtime directory.

## Credentials

- Store credentials only in the private XDG config directory, not the checkout.
- Cookie files and browser headers are credentials, even when limited to YouTube domains. Never paste them into chat, issues, logs or screenshots.
- `.gitignore` blocks common accidental credential copies. Gitignore does not protect files already tracked or force-added. Inspect the staged diff before publishing.
- Auth tools return metadata only. The MCP import tool has a fixed app-specific source and does not accept arbitrary paths or credential text.
- Imports do not guarantee remote session validity. Reauthenticate in SimpMusic when the session expires, then explicitly reimport.
- Only connect trusted local MCP clients. Playback and auth-import tools have real local side effects.

## Reports

Report bugs with synthetic fixtures, exact dependency versions, safe error categories and reproduction steps. Do not attach credential files, authentication headers, account databases or signed stream URLs. If a credential was accidentally published, revoke the session immediately; deleting a commit is not sufficient.

Dependencies and YouTube internals may change. Update yt-dlp and its official JavaScript solver before diagnosing playback issues. Premium entitlement and DRM are not bypassed.
