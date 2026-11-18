"""Look up GitHub releases for losava/parts-label-maker.

Nothing in this module installs software. Download helpers only save a file
and hand it to the normal installer, which still waits for the user.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request

GITHUB_REPO = "losava/parts-label-maker"
LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def app_version() -> str:
    try:
        from version import __version__
        return __version__
    except Exception:
        return "0.0.0"


def parse_version(value: str) -> tuple[int, int, int]:
    """Turn 'v1.2.3' or '1.2' into a three-part number. Extra text is ignored."""
    text = (value or "").strip()
    if text[:1].lower() == "v":
        text = text[1:]
    numbers: list[int] = []
    for part in text.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        numbers.append(int(digits) if digits else 0)
    while len(numbers) < 3:
        numbers.append(0)
    return (numbers[0], numbers[1], numbers[2])


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def _user_agent() -> str:
    return f"parts-label-maker/{app_version()}"


def fetch_latest_release(timeout: float = 8, url: str | None = None) -> dict | None:
    """Latest GitHub release, or None when offline or the request fails."""
    request = urllib.request.Request(
        url or LATEST_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _user_agent(),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get("tag_name"):
        return None
    return payload


def release_version(release: dict) -> str:
    tag = str(release.get("tag_name") or "").strip()
    if tag[:1].lower() == "v":
        return tag[1:]
    return tag


def release_notes(release: dict, limit: int = 4000) -> str:
    body = str(release.get("body") or "").strip()
    if not body:
        return "No release notes were published."
    if len(body) > limit:
        return body[:limit].rstrip() + "\n…"
    return body


def pick_asset(release: dict, platform: str | None = None) -> dict | None:
    """Installer for this operating system, or None when the release has no match.

    Windows uses the Inno Setup exe. Linux prefers the AppImage (no admin),
    then the .deb, then the tarball.
    """
    system = platform or sys.platform
    assets = [item for item in (release.get("assets") or []) if isinstance(item, dict)]

    def name_of(asset: dict) -> str:
        return str(asset.get("name") or "")

    if system.startswith("win"):
        for asset in assets:
            name = name_of(asset)
            if name.lower().endswith(".exe") and "setup" in name.lower():
                return asset
        return None

    for suffix in (".AppImage", ".deb", ".tar.gz"):
        for asset in assets:
            if name_of(asset).endswith(suffix):
                return asset
    return None


def download_asset(asset: dict, dest_dir: str, timeout: float = 120) -> str:
    """Save a release asset. Raises RuntimeError if the download fails."""
    url = str(asset.get("browser_download_url") or "")
    name = str(asset.get("name") or "update.bin")
    if not url:
        raise RuntimeError("This release has no download link.")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    request = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(dest, "wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc
    return dest


def _open_path(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path])


def launch_installer(path: str) -> str:
    """Hand a downloaded file to the user. Never passes a silent-install flag.

    The returned text is what the window should show. The installed copy is
    unchanged until the user finishes the installer or starts the new AppImage.
    """
    if sys.platform.startswith("win") and path.lower().endswith(".exe"):
        os.startfile(path)  # type: ignore[attr-defined]
        return (
            "The installer is opening. Parts Label is not updated until you "
            "finish that window. Close this copy if the installer asks."
        )
    if path.endswith(".AppImage"):
        os.chmod(path, 0o755)
        try:
            _open_path(os.path.dirname(path) or ".")
        except Exception:
            pass
        return (
            "Downloaded the AppImage. Nothing was replaced.\n\n"
            f"{path}\n\n"
            "Start that file when you want the new version."
        )
    if path.endswith(".deb"):
        try:
            _open_path(path)
        except Exception as exc:
            return f"Downloaded to:\n{path}\n\nCouldn't open it automatically ({exc})."
        return (
            "The package is opening. Confirm the install there. "
            "Nothing changes until you do.\n\n"
            f"{path}"
        )
    folder = os.path.dirname(path) or path
    try:
        _open_path(folder)
    except Exception:
        pass
    return f"Downloaded to:\n{path}\n\nNothing was installed."
