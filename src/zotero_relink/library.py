"""Reads the linked files in a Zotero library from zotero.sqlite, opened read-only."""
import os
import sqlite3
from dataclasses import dataclass

LINKED_FILE = 2           # itemAttachments.linkMode for "link to file"
RELATIVE = "attachments:"  # prefix of paths stored relative to the linked attachment base directory


@dataclass(frozen=True)
class Link:
    key: str           # the attachment's item key
    stored: str        # the path exactly as Zotero stores it
    path: str          # where that is on this computer ("" if it can't be resolved)
    title: str | None  # the attachment's title


def resolve(stored, base_dir):
    if stored.startswith(RELATIVE):
        if not base_dir:
            return ""
        return os.path.join(str(base_dir), *stored[len(RELATIVE):].split("/"))
    return stored


def store(new_path, old_stored, base_dir):
    """The value to store for new_path: relative to the base directory if the old value was and it still fits."""
    if old_stored.startswith(RELATIVE) and base_dir:
        rel = os.path.relpath(new_path, base_dir)
        if not rel.startswith(os.pardir):
            return RELATIVE + rel.replace(os.sep, "/")
    return new_path


def linked_files(db_path, base_dir=None):
    """Linked files in the personal library, leaving out anything in Zotero's trash."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT i.itemID, i.key, a.path FROM itemAttachments a"
            " JOIN items i ON i.itemID = a.itemID"
            " JOIN libraries l ON l.libraryID = i.libraryID"
            " WHERE a.linkMode = ? AND l.type = 'user' AND a.path IS NOT NULL AND a.path != ''"
            " AND a.itemID NOT IN (SELECT itemID FROM deletedItems)"
            " AND (a.parentItemID IS NULL OR a.parentItemID NOT IN (SELECT itemID FROM deletedItems))",
            (LINKED_FILE,)).fetchall()
        titles = dict(conn.execute(
            "SELECT d.itemID, v.value FROM itemData d JOIN fields f ON f.fieldID = d.fieldID"
            " JOIN itemDataValues v ON v.valueID = d.valueID WHERE f.fieldName = 'title'").fetchall())
    finally:
        conn.close()
    return [Link(key, stored, resolve(stored, base_dir), titles.get(iid)) for iid, key, stored in rows]
