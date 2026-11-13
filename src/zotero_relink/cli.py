"""zotero-relink: keeps Zotero's linked files linked when you move or rename them.

  zotero-relink           check every linked file and fix the links of files that moved
  zotero-relink check     the same, but only say what would change
  zotero-relink status    what the last run found
"""
import argparse
import contextlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import __version__, config
from .api import ZoteroAPI
from .fixer import fix

KEYS_URL = "https://www.zotero.org/settings/keys"


@contextlib.contextmanager
def _lock(folder):
    """Only one run at a time (the timer and a manual run can overlap)."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # Windows: no lock
        yield True
        return
    with open(folder / "lock", "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def _parser():
    p = argparse.ArgumentParser(prog="zotero-relink", description="Keeps Zotero's linked files linked when you "
                                "move or rename them.")
    p.add_argument("command", nargs="?", default="fix", choices=["fix", "check", "status"])
    p.add_argument("--dry-run", action="store_true", help="say what would change; change nothing")
    p.add_argument("--quiet", action="store_true", help="print only what changed or went wrong")
    p.add_argument("--data-dir", help="Zotero's data directory (found automatically)")
    p.add_argument("--root", action="append", default=[], help="where to look for moved files (default: home)")
    p.add_argument("--skip", action="append", default=[], help="a folder not to look in (repeatable)")
    p.add_argument("--trash-dir", action="append", default=[], help="a trash folder (found automatically)")
    p.add_argument("--state", help="zotero-relink's state file (default: ~/.local/state/zotero-relink/state.json)")
    p.add_argument("--env-file", help="file with ZOTERO_API_KEY and ZOTERO_USER_ID "
                   "(default: ~/.config/zotero-relink/env)")
    p.add_argument("--version", action="version", version=f"zotero-relink {__version__}")
    return p


def main(argv=None, make_api=None, environ=None):
    environ = os.environ if environ is None else environ
    args = _parser().parse_args(argv)
    home = Path(environ.get("HOME") or Path.home())
    state_home = Path(environ.get("XDG_STATE_HOME") or home / ".local/state")
    state = Path(args.state) if args.state else state_home / "zotero-relink" / "state.json"
    if args.command == "status":
        return _status(state.parent)

    dry = args.dry_run or args.command == "check"
    data_dir = Path(args.data_dir) if args.data_dir else config.find_data_dir(home, environ)
    if not data_dir or not (data_dir / "zotero.sqlite").exists():
        print("zotero-relink: can't find zotero.sqlite. Pass --data-dir (Zotero: Settings > Advanced > Files and Folders).")
        return 2
    creds = config.credentials(environ, Path(args.env_file) if args.env_file else home / ".config/zotero-relink/env")
    api = (make_api or ZoteroAPI)(*creds) if creds and not dry else None
    roots = [Path(r) for r in args.root] or [home]
    skip = [data_dir, *map(Path, args.skip)]
    trash = [Path(t) for t in args.trash_dir] or [d for d in (home / ".local/share/Trash/files", home / ".Trash")
                                                   if d.is_dir()]

    with _lock(state.parent) as ok:
        if not ok:
            return 0
        with tempfile.TemporaryDirectory(prefix="zotero-relink-") as tmp:
            copy = Path(tmp) / "zotero.sqlite"
            shutil.copy2(data_dir / "zotero.sqlite", copy)   # Zotero locks the live database
            report = fix(copy, state, roots, api, base_dir=config.find_base_dir(home), dry_run=dry,
                         trash_dirs=trash, skip=skip)
    no_key = not dry and api is None and report.relinked
    return _finish(report, state.parent, dry, no_key, args.quiet,
                   args.env_file or home / ".config/zotero-relink/env")


def _finish(report, folder, dry, no_key, quiet, env_file):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    before = {}
    if (folder / "last-run.json").exists():
        before = {m["key"]: m["reason"] for m in json.loads((folder / "last-run.json").read_text())["missing"]}
    if not dry and not no_key:
        with open(folder / "log.jsonl", "a") as log:
            for r in report.relinked:
                log.write(json.dumps({"t": stamp, "key": r.key, "old": r.old, "new": r.new, "how": r.how}) + "\n")
        (folder / "last-run.json").write_text(json.dumps({
            "t": stamp, "checked": report.checked, "relinked": len(report.relinked), "waiting": report.waiting,
            "missing": [{"key": m.key, "path": m.path, "reason": m.reason} for m in report.missing],
            "failed": [{"key": f.key, "code": f.code, "message": f.message} for f in report.failed]}, indent=1))

    lines = []
    verb = "would relink" if dry or no_key else "relinked"
    for r in report.relinked:
        lines.append(f"  {verb} {r.key}: {r.old} -> {r.new} (same {r.how})")
    for m in report.missing:
        if not quiet or before.get(m.key) != m.reason:
            lines.append(f"  missing {m.key}: {m.path} ({m.reason})")
    for f in report.failed:
        lines.append(f"  failed {f.key}: HTTP {f.code} {f.message}")
    if no_key:
        lines.append(f"  zotero-relink can't fix these without a Zotero API key with write access ({KEYS_URL}).")
        lines.append(f"  Put ZOTERO_API_KEY=... and ZOTERO_USER_ID=... in {env_file}.")
    if lines or not quiet:
        print(f"zotero-relink: checked {report.checked} linked files; {verb} {len(report.relinked)}; "
              f"{len(report.missing)} missing; {len(report.waiting)} waiting for Zotero to sync")
        print("\n".join(lines)) if lines else None
    return 2 if no_key else (1 if report.failed else 0)


def _status(folder):
    last = folder / "last-run.json"
    if not last.exists():
        print("zotero-relink hasn't run yet.")
        return 0
    run = json.loads(last.read_text())
    print(f"last run {run['t']}: checked {run['checked']} linked files, relinked {run['relinked']}, "
          f"{len(run['missing'])} missing, {len(run['waiting'])} waiting for Zotero to sync")
    for m in run["missing"]:
        print(f"  missing {m['key']}: {m['path']} ({m['reason']})")
    for f in run["failed"]:
        print(f"  failed {f['key']}: HTTP {f['code']} {f['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
