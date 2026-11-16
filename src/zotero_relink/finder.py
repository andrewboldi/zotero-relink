"""Finds where missing files went: first by inode, then by content."""
import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass

SKIP_NAMES = {"node_modules", "__pycache__", "site-packages"}


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def identify(path, known=None):
    """What a file is, so it can be recognized after a move. The hash is reused while the file is unchanged."""
    st = os.stat(path)
    rec = {"path": str(path), "dev": st.st_dev, "ino": st.st_ino, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    unchanged = known and known.get("sha256") and all(known.get(k) == rec[k] for k in ("dev", "ino", "size", "mtime_ns"))
    rec["sha256"] = known["sha256"] if unchanged else sha256_file(path)
    return rec


def walk(roots, skip=(), hidden=False):
    """Regular files under roots. Skips symlinks, the folders in skip, dependency folders and,
    unless hidden is set, hidden files and folders (which Zotero may not be allowed to open)."""
    skip = {os.path.abspath(str(s)) for s in skip}
    stack, seen = [os.path.abspath(str(r)) for r in roots], set()
    while stack:
        d = stack.pop()
        if d in skip or d in seen:
            continue
        seen.add(d)
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                if not hidden and e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in SKIP_NAMES:
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        yield e
                except OSError:
                    continue


@dataclass
class Found:
    path: str | None = None    # where the file is now
    how: str | None = None     # "inode" or "content"
    reason: str | None = None  # why it wasn't found


def _scan(entries, wanted):
    by_ino, sizes = defaultdict(list), set()
    for key, (_, rec) in wanted.items():
        by_ino[rec["ino"]].append(key)
        sizes.add(rec["size"])
    inode_hits, same_size = defaultdict(list), defaultdict(list)
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        for key in by_ino.get(st.st_ino, ()):
            rec = wanted[key][1]
            # Same inode, size and modification time: the same file. (FAT and exFAT drives make inode
            # numbers up and may reuse them; a file that also changed is checked by content instead.)
            if st.st_dev == rec["dev"] and st.st_size == rec["size"] and st.st_mtime_ns == rec["mtime_ns"]:
                inode_hits[key].append(e.path)
        if st.st_size in sizes:
            same_size[st.st_size].append(e.path)
    return inode_hits, same_size


def _named_like(paths, old):
    named = [p for p in paths if os.path.basename(p) == os.path.basename(old)]
    return named if len(named) == 1 else paths


def _near(wanted, roots):
    """The closest existing folder to each old path, inside the roots: most moves happen nearby."""
    dirs = set()
    for old, _ in wanted.values():
        d = os.path.dirname(os.path.abspath(old))
        while not os.path.isdir(d) and d != os.path.dirname(d):
            d = os.path.dirname(d)
        if any(d == r or d.startswith(r.rstrip(os.sep) + os.sep) for r in roots):
            dirs.add(d)
        else:
            dirs.update(roots)
    return sorted(d for d in dirs if not any(o != d and d.startswith(o.rstrip(os.sep) + os.sep) for o in dirs))


def find(wanted, roots, skip=(), trash_dirs=(), search_all=None):
    """wanted maps a key to (the path the file was last seen at, its identity). Returns key -> Found.

    The folders near each old path are searched first. Keys in search_all (default: all) that aren't found
    there by inode get a search of all the roots. A file is never guessed: two equally good candidates
    are reported, not picked."""
    roots = [os.path.abspath(str(r)) for r in roots]
    search_all = set(wanted) if search_all is None else set(search_all) & set(wanted)
    near = _near(wanted, roots)
    everything = any(n in roots for n in near)
    near_hits = _scan(walk(roots if everything else near, skip), wanted)
    source = dict.fromkeys(wanted, near_hits)
    rest = {} if everything else {k: wanted[k] for k in search_all if not near_hits[0].get(k)}
    if rest:
        full_hits = _scan(walk(roots, skip), rest)
        source.update(dict.fromkeys(rest, full_hits))
    hashes = {}

    def sha(p):
        if p not in hashes:
            try:
                hashes[p] = sha256_file(p)
            except OSError:
                hashes[p] = None
        return hashes[p]

    out = {}
    for key, (old, rec) in wanted.items():
        inode_hits, same_size = source[key]
        if inode_hits.get(key):
            out[key] = Found(sorted(_named_like(inode_hits[key], old))[0], "inode")
            continue
        matches = _named_like([p for p in same_size.get(rec["size"], ()) if sha(p) == rec["sha256"]], old)
        if len(matches) == 1:
            out[key] = Found(matches[0], "content")
        elif matches:
            out[key] = Found(reason=f"{len(matches)} identical copies")
        else:
            out[key] = Found(reason="not found")

    lost = {k: wanted[k] for k, f in out.items() if f.reason == "not found"}
    if lost and trash_dirs:
        t_inode, t_size = _scan(walk(trash_dirs, hidden=True), lost)
        for key, (_, rec) in lost.items():
            if t_inode.get(key) or any(sha(p) == rec["sha256"] for p in t_size.get(rec["size"], ())):
                out[key] = Found(reason="in the trash")
    return out
