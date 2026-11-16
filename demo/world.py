"""The demo's throwaway world, used by record.sh. Nothing here touches a real Zotero library.

  world.py setup WORK        WORK/home with three papers, a tiny zotero.sqlite linking them, and an API key file;
                             WORK/server.json, the stand-in Web API's items
  world.py serve WORK PORT   answer the Web API calls zotero-relink makes, from WORK/server.json
  world.py view WORK         the library as Zotero would show it: each paper, its file, and whether it opens
"""
import json
import os
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAPERS = [  # attachment key, title, file name
    ("K7D2PQ9A", "Attention Is All You Need", "attention.pdf"),
    ("R4XN8MZB", "Deep Residual Learning for Image Recognition", "resnet.pdf"),
    ("T9WC3HJE", "Highly accurate protein structure prediction with AlphaFold", "alphafold.pdf"),
]
SCHEMA = """
CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY, type TEXT NOT NULL);
CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT, libraryID INT NOT NULL, key TEXT NOT NULL);
CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, linkMode INT, contentType TEXT, path TEXT);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value);
CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
INSERT INTO libraries VALUES (1, 'user');
INSERT INTO fields VALUES (1, 'title');
"""


def setup(work):
    home = os.path.join(work, "home")
    for d in ("Papers", "Zotero", ".config/zotero-relink"):
        os.makedirs(os.path.join(home, d))
    db = sqlite3.connect(os.path.join(home, "Zotero", "zotero.sqlite"))
    db.executescript(SCHEMA)
    server = {"items": {}}
    for item_id, (key, title, name) in enumerate(PAPERS, 1):
        path = os.path.join(home, "Papers", name)
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n% " + title.encode() + b"\n" + os.urandom(4096))
        db.execute("INSERT INTO items VALUES (?, 3, 1, ?)", (item_id, key))
        db.execute("INSERT INTO itemAttachments VALUES (?, NULL, 2, 'application/pdf', ?)", (item_id, path))
        value_id = db.execute("INSERT INTO itemDataValues (value) VALUES (?)", (name,)).lastrowid
        db.execute("INSERT INTO itemData VALUES (?, 1, ?)", (item_id, value_id))
        server["items"][key] = {"key": key, "version": 1, "data": {
            "key": key, "version": 1, "itemType": "attachment", "linkMode": "linked_file", "title": name,
            "path": path, "contentType": "application/pdf", "tags": [], "relations": {}}}
    db.commit()
    with open(os.path.join(home, ".config/zotero-relink/env"), "w") as f:
        f.write("ZOTERO_API_KEY=demo\nZOTERO_USER_ID=1\n")
    with open(os.path.join(work, "server.json"), "w") as f:
        json.dump(server, f)


def serve(work, port):
    state_path = os.path.join(work, "server.json")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            keys = parse_qs(urlparse(self.path).query).get("itemKey", [""])[0].split(",")
            items = json.load(open(state_path))["items"]
            self.reply([items[k] for k in keys if k in items])

        def do_POST(self):
            objects = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state = json.load(open(state_path))
            out = {"successful": {}, "unchanged": {}, "failed": {}}
            for i, obj in enumerate(objects):
                item = state["items"].get(obj["key"])
                if not item or obj.get("version") != item["version"]:
                    out["failed"][str(i)] = {"key": obj["key"], "code": 412, "message": "version mismatch"}
                    continue
                item["version"] += 1
                item["data"] = dict(obj, version=item["version"])
                out["successful"][str(i)] = item
            with open(state_path + ".tmp", "w") as f:
                json.dump(state, f)
            os.replace(state_path + ".tmp", state_path)
            self.reply(out)

    ThreadingHTTPServer(("127.0.0.1", int(port)), Handler).serve_forever()


def view(work):
    home = os.path.join(work, "home")
    green, red, dim, bold, plain = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
    shown = None
    while True:
        try:
            items = json.load(open(os.path.join(work, "server.json")))["items"]
        except (OSError, ValueError):
            time.sleep(0.1)
            continue
        lines = [f" {bold}Zotero{plain}  {dim}My Library{plain}", ""]
        for key, title, _ in PAPERS:
            path = items[key]["data"]["path"]
            short = "~" + path[len(home):] if path.startswith(home + "/") else path
            if os.path.isfile(path):
                lines.append(f" {green}✓{plain} {title[:44]:<44}  {dim}{short}{plain}")
            else:
                lines.append(f" {red}✗{plain} {title[:44]:<44}  {red}The attached file could not be found.{plain}")
        if lines != shown:
            sys.stdout.write("\033[H\033[2J" + "\n".join(lines))
            sys.stdout.flush()
            shown = lines
        time.sleep(0.15)


if __name__ == "__main__":
    {"setup": setup, "serve": serve, "view": view}[sys.argv[1]](*sys.argv[2:])
