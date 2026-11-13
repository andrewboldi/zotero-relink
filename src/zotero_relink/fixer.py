"""One pass: check every linked file, find the ones that moved, and fix their paths through the Web API.

zotero-relink never writes zotero.sqlite. It changes a linked attachment's path (and its title, when that was
just the old file name) on zotero.org, and Zotero desktop picks the change up at its next sync.
"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .finder import find, identify
from .library import linked_files, resolve, store

NEVER_SEEN = "missing before zotero-relink first saw it"
CHANGED = "changed in Zotero since"
RACE = 412  # the item changed between zotero-relink reading and writing it
HOUR, WEEK = 3600, 7 * 86400  # a lost file's full search waits an hour, doubling up to a week


@dataclass
class Relinked:
    key: str
    old: str
    new: str
    how: str


@dataclass
class Missing:
    key: str
    path: str
    reason: str


@dataclass
class Failed:
    key: str
    code: int
    message: str


@dataclass
class Report:
    checked: int = 0
    relinked: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    waiting: list = field(default_factory=list)  # fixed on zotero.org, not yet synced to Zotero desktop
    failed: list = field(default_factory=list)
    dry_run: bool = False


def load_state(path):
    try:
        state = json.loads(Path(path).read_text())
    except FileNotFoundError:
        state = {}
    state.setdefault("files", {})
    state.setdefault("pending", {})
    return state


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, path)


def fix(db_path, state_path, roots, api, *, base_dir=None, dry_run=False, trash_dirs=(), skip=(), now=None):
    now = time.time() if now is None else now
    state = load_state(state_path)
    files, pending, lost = state["files"], state["pending"], state.setdefault("lost", {})
    report = Report(dry_run=dry_run)
    links = {link.key: link for link in linked_files(db_path, base_dir)}
    report.checked = len(links)

    wanted = {}
    for key, link in links.items():
        if link.path and os.path.isfile(link.path):
            known = files.get(key)
            files[key] = identify(link.path, known if known and known["path"] == link.path else None)
            lost.pop(key, None)
            if pending.get(key, {}).get("to") == link.stored:
                del pending[key]  # Zotero desktop has synced the fix
            continue
        pend = pending.get(key)
        if pend and pend["from"] == link.stored and os.path.isfile(resolve(pend["to"], base_dir)):
            report.waiting.append(key)
            continue
        if key not in files:
            report.missing.append(Missing(key, link.path or link.stored, NEVER_SEEN))
            continue
        wanted[key] = (files[key]["path"], files[key])

    due = {k for k in wanted if k not in lost or now >= lost[k]["at"] + lost[k]["wait"]}
    found = find(wanted, roots, skip, trash_dirs, search_all=due) if wanted else {}
    fixes = {}
    for key, f in found.items():
        if f.path:
            fixes[key] = f
            lost.pop(key, None)
            continue
        if key in due:
            lost[key] = {"at": now, "wait": min(max(2 * lost.get(key, {}).get("wait", 0), HOUR), WEEK)}
        report.missing.append(Missing(key, links[key].path or links[key].stored, f.reason))

    if fixes and (dry_run or api is None):
        report.relinked = [Relinked(k, links[k].path, f.path, f.how) for k, f in fixes.items()]
    elif fixes:
        _write(api, fixes, links, files, pending, base_dir, report)

    if not dry_run:
        for gone in [k for k in files if k not in links]:
            del files[gone]
        for table in (pending, lost):
            for gone in [k for k in table if k not in links]:
                del table[gone]
        save_state(state_path, state)
    return report


def _write(api, fixes, links, files, pending, base_dir, report):
    todo = dict(fixes)
    for attempt in (1, 2):
        server = {item["key"]: item for item in api.get_items(list(todo))}
        updates = {}
        for key, f in todo.items():
            link, item = links[key], server.get(key)
            data = item["data"] if item else {}
            if data.get("linkMode") != "linked_file":
                report.missing.append(Missing(key, link.path, CHANGED))
                continue
            ours = {link.stored} | ({pending[key]["to"]} if key in pending else set())
            if data.get("path") not in ours:
                if resolve(data.get("path", ""), base_dir) == f.path:
                    pending[key] = {"from": link.stored, "to": data["path"]}
                    report.waiting.append(key)
                else:
                    report.missing.append(Missing(key, link.path, CHANGED))
                continue
            new = dict(data, path=store(f.path, link.stored, base_dir))
            if data.get("title") == os.path.basename(resolve(data["path"], base_dir)):
                new["title"] = os.path.basename(f.path)
            updates[key] = new
        if not updates:
            return
        result = api.update_items(list(updates.values()))
        for key in result["successful"]:
            f = todo[key]
            pending[key] = {"from": links[key].stored, "to": updates[key]["path"]}
            files[key] = identify(f.path, dict(files[key], path=f.path))
            report.relinked.append(Relinked(key, links[key].path, f.path, f.how))
        retry = {}
        for fail in result["failed"]:
            if attempt == 1 and fail.get("code") == RACE:
                retry[fail["key"]] = todo[fail["key"]]
            else:
                report.failed.append(Failed(fail["key"], fail.get("code"), fail.get("message", "")))
        if not retry:
            return
        todo = retry
