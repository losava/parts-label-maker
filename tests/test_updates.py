"""Version comparison and release-asset selection. No network except a refused port."""

import updater


def test_parse_version_and_compare():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("1.2") == (1, 2, 0)
    assert updater.parse_version("1.10.0-beta") == (1, 10, 0)
    assert updater.is_newer("1.0.1", "1.0.0")
    assert updater.is_newer("v1.10.0", "1.2.0")
    assert not updater.is_newer("1.0.0", "1.0.0")
    assert not updater.is_newer("0.9.0", "1.0.0")


def test_release_notes_and_version():
    release = {"tag_name": "v1.2.0", "body": "  Fixed the barcode quiet zone.  "}
    assert updater.release_version(release) == "1.2.0"
    assert "quiet zone" in updater.release_notes(release)
    assert updater.release_notes({"tag_name": "v1.2.0", "body": ""}) == "No release notes were published."
    long_body = "x" * 5000
    assert updater.release_notes({"tag_name": "v1.2.0", "body": long_body}).endswith("…")


def test_pick_asset_for_each_platform():
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "PartsLabel-Setup-1.0.0.exe", "browser_download_url": "https://example.invalid/setup.exe"},
            {"name": "parts-label-maker_1.0.0_amd64.deb", "browser_download_url": "https://example.invalid/a.deb"},
            {"name": "PartsLabel-1.0.0-x86_64.AppImage", "browser_download_url": "https://example.invalid/a.AppImage"},
            {"name": "PartsLabel-1.0.0-linux-x86_64.tar.gz", "browser_download_url": "https://example.invalid/a.tar.gz"},
            {"name": "notes.txt", "browser_download_url": "https://example.invalid/notes.txt"},
        ],
    }
    assert updater.pick_asset(release, "win32")["name"].endswith(".exe")
    linux_asset = updater.pick_asset(release, "linux")
    assert linux_asset["name"].endswith(".AppImage")
    assert updater.pick_asset({"tag_name": "v1.0.0", "assets": []}, "win32") is None


def test_fetch_latest_release_is_none_when_offline():
    result = updater.fetch_latest_release(timeout=2, url="http://127.0.0.1:9/releases")
    assert result is None


def test_download_asset_rejects_a_missing_url(tmp_path):
    try:
        updater.download_asset({"name": "x.exe"}, str(tmp_path))
    except RuntimeError as exc:
        assert "download" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError")
