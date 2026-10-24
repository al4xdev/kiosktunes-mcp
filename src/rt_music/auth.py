"""Explicit, local SimpMusic cookie import. Never log credential values."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

ORIGIN = "https://music.youtube.com"
MAX_SOURCE_BYTES = 1024 * 1024


class AuthError(Exception):
    """Safe, credential-free error suitable for display."""


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not base.is_absolute():
        raise AuthError("XDG_CONFIG_HOME must be an absolute path")
    return base / "kiosktunes-mcp"


@dataclass(frozen=True)
class Cookie:
    domain: str
    subdomains: str
    path: str
    secure: str
    expires: int
    name: str
    value: str = field(repr=False)
    http_only: bool = False

    def netscape(self) -> str:
        domain = ("#HttpOnly_" if self.http_only else "") + self.domain
        return "\t".join(
            (
                domain,
                self.subdomains,
                self.path,
                self.secure,
                str(self.expires),
                self.name,
                self.value,
            )
        )


def _read_source(source: Path) -> str:
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise AuthError("Cookie source must be a regular file owned by you")
            data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise AuthError("Cookie source exceeds the size limit")
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        raise AuthError("Cannot safely read cookie source") from None


def read_cookies(source: Path, *, now: int | None = None) -> list[Cookie]:
    """Keep only unexpired cookies that apply to music.youtube.com."""
    now = int(time.time()) if now is None else now
    text = _read_source(source)
    if not any(
        line.startswith("# Netscape HTTP Cookie File") for line in text.splitlines()
    ):
        raise AuthError("Expected a Netscape HTTP Cookie File")
    cookies = []
    for line in text.splitlines():
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_") :]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            raise AuthError("Malformed Netscape cookie row")
        domain, subdomains, path, secure, expiry, name, value = parts
        if (
            subdomains not in {"TRUE", "FALSE"}
            or secure not in {"TRUE", "FALSE"}
            or not expiry.isdecimal()
            or not path.startswith("/")
            or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
            or any(ord(char) < 32 or ord(char) >= 127 for char in value)
            or any(char in value for char in ';"\\')
        ):
            raise AuthError("Invalid Netscape cookie fields")
        host = domain.lstrip(".").lower()
        # Google-wide cookies are intentionally excluded even though they may
        # authenticate the same account. Never harvest a browser profile.
        applies = host == "music.youtube.com" or (
            host == "youtube.com" and subdomains == "TRUE"
        )
        expires = int(expiry)
        if applies and (expires == 0 or expires > now):
            cookies.append(
                Cookie(
                    domain, subdomains, path, secure, expires, name, value, http_only
                )
            )
    if not cookies:
        raise AuthError("No unexpired YouTube Music cookies found")
    return cookies


def _browser_headers(cookies: list[Cookie], auth_user: int) -> dict[str, str]:
    if auth_user < 0:
        raise AuthError("auth-user must be a nonnegative account index")
    selected: dict[str, Cookie] = {}
    for cookie in cookies:
        if cookie.path != "/":
            continue
        previous = selected.get(cookie.name)
        if previous is None or cookie.domain.lstrip(".") == "music.youtube.com":
            selected[cookie.name] = cookie
    sapisid = selected.get("__Secure-3PAPISID")
    if sapisid is None or not sapisid.value or sapisid.secure != "TRUE":
        raise AuthError(
            "Missing secure __Secure-3PAPISID; browser authentication unavailable"
        )
    stamp = str(int(time.time()))
    digest = hashlib.sha1(f"{stamp} {sapisid.value} {ORIGIN}".encode()).hexdigest()
    # ytmusicapi detects browser mode from SAPISIDHASH, then refreshes this
    # timestamped header on each request using the cookie and origin.
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": ORIGIN,
        "x-origin": ORIGIN,
        "x-goog-authuser": str(auth_user),
        "authorization": f"SAPISIDHASH {stamp}_{digest}",
        "cookie": "; ".join(f"{item.name}={item.value}" for item in selected.values()),
    }


def _private_directory(directory: Path) -> int:
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid():
        os.close(fd)
        raise AuthError("Config directory must be owned by you")
    os.fchmod(fd, 0o700)
    return fd


def import_simpmusic(
    source: Path | None = None,
    *,
    force: bool = False,
    auth_user: int = 0,
    directory: Path | None = None,
) -> dict[str, object]:
    """Write two mode-600 files; only this explicitly called API imports secrets."""
    source = source or Path.home() / ".simpmusic" / "ytdlp-cookie.txt"
    cookies = read_cookies(source)
    headers = _browser_headers(cookies, auth_user)
    payloads = {
        "cookies.txt": "# Netscape HTTP Cookie File\n"
        + "\n".join(c.netscape() for c in cookies)
        + "\n",
        "browser.json": json.dumps(headers, indent=2) + "\n",
    }
    directory = directory or config_dir()
    temporary: list[str] = []
    try:
        fd = _private_directory(directory)
        try:
            lock = os.open(
                ".auth.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd
            )
            with os.fdopen(lock, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise AuthError("Unsafe auth lock file")
                os.fchmod(stream.fileno(), 0o600)
                fcntl.flock(stream, fcntl.LOCK_EX)
                for name in payloads:
                    try:
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                        raise AuthError("Refusing an unsafe credential destination")
                    if not force:
                        raise AuthError(
                            "Credentials already exist; use --force to replace them"
                        )
                for name, content in payloads.items():
                    temp = ".auth-" + secrets.token_hex(16)
                    out = os.open(
                        temp,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=fd,
                    )
                    temporary.append(temp)
                    with os.fdopen(out, "w", encoding="utf-8") as target:
                        os.fchmod(target.fileno(), 0o600)
                        target.write(content)
                        target.flush()
                        os.fsync(target.fileno())
                    if force:
                        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
                    else:
                        # Hard-link publication also prevents an uncooperative
                        # writer from causing accidental credential replacement.
                        os.link(
                            temp,
                            name,
                            src_dir_fd=fd,
                            dst_dir_fd=fd,
                            follow_symlinks=False,
                        )
                        os.unlink(temp, dir_fd=fd)
                    temporary.remove(temp)
                os.fsync(fd)
        finally:
            for temp in temporary:
                os.unlink(temp, dir_fd=fd)
            os.close(fd)
    except OSError:
        raise AuthError(
            "Cannot safely store credentials; check config files and permissions"
        ) from None
    return {
        "directory": str(directory),
        "files": list(payloads),
        "cookie_count": len(cookies),
    }


def status(directory: Path | None = None) -> dict[str, object]:
    """Return paths/modes only, never read credential file contents."""
    directory = directory or config_dir()
    result: dict[str, object] = {"directory": str(directory)}
    for name in ("cookies.txt", "browser.json"):
        path = directory / name
        try:
            info = path.lstat()
            result[name] = {
                "exists": True,
                "private": stat.S_ISREG(info.st_mode)
                and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600,
            }
        except FileNotFoundError:
            result[name] = {"exists": False}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show credential file metadata only")
    for command in ("inspect-simpmusic", "import-simpmusic"):
        sub = commands.add_parser(command)
        sub.add_argument(
            "--source",
            type=Path,
            default=Path.home() / ".simpmusic" / "ytdlp-cookie.txt",
        )
        sub.add_argument("--auth-user", type=int, default=0)
        if command == "import-simpmusic":
            sub.add_argument(
                "--force",
                action="store_true",
                help="Explicitly replace existing credentials",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = status()
        elif args.command == "inspect-simpmusic":
            cookies = read_cookies(args.source)
            _browser_headers(cookies, args.auth_user)
            result = {
                "source": str(args.source),
                "cookie_count": len(cookies),
                "browser_auth_feasible": True,
                "credentials_written": False,
            }
        else:
            result = import_simpmusic(
                args.source, force=args.force, auth_user=args.auth_user
            )
        print(json.dumps(result, indent=2))
        return 0
    except AuthError as error:
        parser.exit(1, f"Auth error: {error}\n")
    except OSError:
        parser.exit(1, "Auth error: cannot inspect local authentication metadata\n")


if __name__ == "__main__":
    raise SystemExit(main())
