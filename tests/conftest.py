"""Test helpers: a tiny zotero.sqlite, a fake Zotero Web API, and a home folder of real files."""
import os
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

# Only the tables and columns zotlink reads, with the real names.
SCHEMA = """
CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY, type TEXT NOT NULL);
CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT, libraryID INT NOT NULL, key TEXT NOT NULL);
CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, linkMode INT,
                              contentType TEXT, path TEXT);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value);
CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
INSERT INTO libraries VALUES (1, 'user'), (2, 'group');
INSERT INTO fields VALUES (1, 'title');
"""


class ZoteroDB:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def _item(self, key, library=1, deleted=False):
        cur = self.conn.execute("INSERT INTO items (itemTypeID, libraryID, key) VALUES (3, ?, ?)", (library, key))
        if deleted:
            self.conn.execute("INSERT INTO deletedItems VALUES (?)", (cur.lastrowid,))
        return cur.lastrowid

    def parent(self, key, deleted=False):
        iid = self._item(key, deleted=deleted)
        self.conn.commit()
        return iid

    def attachment(self, key, path, title=None, link_mode=2, parent=None, library=1, deleted=False):
        iid = self._item(key, library, deleted)
        self.conn.execute("INSERT INTO itemAttachments VALUES (?, ?, ?, 'application/pdf', ?)",
                          (iid, parent, link_mode, str(path)))
        if title is not None:
            vid = self.conn.execute("INSERT INTO itemDataValues (value) VALUES (?)", (title,)).lastrowid
            self.conn.execute("INSERT INTO itemData VALUES (?, 1, ?)", (iid, vid))
        self.conn.commit()
        return iid

    def set_path(self, key, path):
        """What Zotero desktop does when a change syncs down."""
        self.conn.execute("UPDATE itemAttachments SET path = ? WHERE itemID = "
                          "(SELECT itemID FROM items WHERE key = ?)", (str(path), key))
        self.conn.commit()


class FakeZotero:
    """The Zotero Web API as zotlink uses it: items carry versions, and a write must name the current one."""

    def __init__(self):
        self.items = {}
        self.writes = []    # every object zotlink sent
        self.refuse = {}    # key -> list of (code, message), one used per write attempt

    def add(self, key, path, title):
        data = {"key": key, "version": 1, "itemType": "attachment", "linkMode": "linked_file",
                "title": title, "path": str(path), "contentType": "application/pdf", "tags": [],
                "relations": {}}
        self.items[key] = {"key": key, "version": 1, "data": data}

    def get_items(self, keys):
        return [deepcopy(self.items[k]) for k in keys if k in self.items]

    def update_items(self, objects):
        result = {"successful": [], "failed": []}
        for obj in objects:
            self.writes.append(deepcopy(obj))
            key = obj["key"]
            if self.refuse.get(key):
                code, message = self.refuse[key].pop(0)
                result["failed"].append({"key": key, "code": code, "message": message})
                continue
            item = self.items[key]
            if obj["version"] != item["version"]:
                result["failed"].append({"key": key, "code": 412, "message": "version mismatch"})
                continue
            item["version"] += 1
            item["data"] = dict(deepcopy(obj), version=item["version"])
            result["successful"].append(key)
        return result

    def bump(self, key):
        """Someone else edited the item (a tag, say) since zotlink last looked."""
        self.items[key]["version"] += 1
        self.items[key]["data"]["version"] = self.items[key]["version"]

    def path(self, key):
        return self.items[key]["data"]["path"]

    def title(self, key):
        return self.items[key]["data"]["title"]


class Env:
    """A home folder with real files, a Zotero database, the fake API and zotlink's state file."""

    def __init__(self, tmp):
        self.home = tmp / "home"
        self.home.mkdir()
        self.trash = self.home / ".local/share/Trash/files"
        self.db = ZoteroDB(tmp / "zotero.sqlite")
        self.server = FakeZotero()
        self.state = tmp / "state" / "state.json"

    def file(self, rel, content=b"%PDF-1.4 some paper"):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def link(self, key, path, title=None):
        title = os.path.basename(str(path)) if title is None else title
        self.db.attachment(key, path, title)
        self.server.add(key, path, title)

    def fix(self, **kw):
        from zotlink.fixer import fix
        kw.setdefault("trash_dirs", [self.trash])
        return fix(self.db.path, self.state, roots=[self.home], api=self.server, **kw)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
