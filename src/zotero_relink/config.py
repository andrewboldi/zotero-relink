"""Where Zotero keeps its database and settings, and where zotero-relink finds its API key."""
import json
import os
import re
from pathlib import Path

# Zotero's default data directory for each way it is installed.
DATA_DIRS = ["Zotero", "snap/zotero-snap/common/Zotero", ".var/app/org.zotero.Zotero/data/Zotero"]
# Zotero's profile folders (prefs.js), on Linux (plain, snap, flatpak), macOS and Windows.
PREFS = [".zotero/zotero/*/prefs.js", "snap/zotero-snap/common/.zotero/zotero/*/prefs.js",
         ".var/app/org.zotero.Zotero/.zotero/zotero/*/prefs.js",
         "Library/Application Support/Zotero/Profiles/*/prefs.js",
         "AppData/Roaming/Zotero/Zotero/Profiles/*/prefs.js"]


def _prefs_files(home):
    for pattern in PREFS:
        yield from sorted(Path(home).glob(pattern))


def read_pref(prefs_js, name):
    text = Path(prefs_js).read_text(errors="replace")
    m = re.search(r'user_pref\("' + re.escape(name) + r'",\s*("(?:[^"\\]|\\.)*")\);', text)
    return json.loads(m.group(1)) if m else None


def find_data_dir(home, environ):
    if environ.get("ZOTERO_DATA_DIR"):
        return Path(environ["ZOTERO_DATA_DIR"])
    for prefs in _prefs_files(home):
        custom = read_pref(prefs, "extensions.zotero.dataDir")
        if custom and (Path(custom) / "zotero.sqlite").exists():
            return Path(custom)
    for rel in DATA_DIRS:
        d = Path(home) / rel
        if (d / "zotero.sqlite").exists():
            return d
    return None


def find_base_dir(home):
    """The linked attachment base directory, if one is set (paths under it are stored relative)."""
    for prefs in _prefs_files(home):
        base = read_pref(prefs, "extensions.zotero.baseAttachmentPath")
        if base:
            return Path(base)
    return None


def load_env_file(path):
    out = {}
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.removeprefix("export ").strip()] = v.strip().strip("'\"")
    return out


def credentials(environ, env_file):
    """(API key, user ID) from the environment or the env file, or None."""
    file = load_env_file(env_file) if env_file else {}
    key = environ.get("ZOTERO_API_KEY") or file.get("ZOTERO_API_KEY")
    uid = environ.get("ZOTERO_USER_ID") or file.get("ZOTERO_USER_ID")
    return (key, int(uid)) if key and uid else None


# Where external drives get mounted: Linux desktops (udisks), plain mounts, macOS.
DRIVE_BASES = ["/media/{user}", "/run/media/{user}", "/media", "/mnt", "/Volumes"]


def find_drives(user, bases=DRIVE_BASES, ismount=os.path.ismount):
    """Mounted external drives, which are searched along with the home folder."""
    out = []
    for base in bases:
        try:
            entries = sorted(Path(base.format(user=user)).iterdir())
        except OSError:
            continue
        for d in entries:
            if d.name.startswith(".") or d in out or not d.is_dir() or not ismount(d):
                continue
            if os.path.realpath(d) != "/":  # macOS lists the startup disk in /Volumes too
                out.append(d)
    return out


def offline_check(user, bases=DRIVE_BASES, ismount=os.path.ismount):
    """A test for paths on an external drive that isn't mounted right now."""
    roots = [base.format(user=user).rstrip("/") for base in bases]

    def offline(path):
        for root in roots:
            if str(path).startswith(root + "/"):
                return not ismount(Path(root) / str(path)[len(root) + 1:].split("/")[0])
        return False
    return offline


def drive_trash(drives, uid):
    """Trash folders on drives (freedesktop and macOS layouts)."""
    found = []
    for d in drives:
        for t in (d / f".Trash-{uid}" / "files", d / ".Trash" / str(uid) / "files", d / ".Trashes" / str(uid)):
            if t.is_dir():
                found.append(t)
    return found
