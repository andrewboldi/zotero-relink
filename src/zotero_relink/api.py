"""A small client for the Zotero Web API (v3): read items by key and write them back with version checks."""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

API = "https://api.zotero.org"
BATCH = 50   # the API's limit per request
TRIES = 8


def urllib_send(method, url, headers, body):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _header(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


class ZoteroAPI:
    def __init__(self, api_key, user_id, send=urllib_send, sleep=time.sleep, base_url=None):
        self.base = f"{(base_url or API).rstrip('/')}/users/{int(user_id)}"
        self.headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                        "User-Agent": f"zotero-relink/{__version__}"}
        self.send, self.sleep = send, sleep

    def _request(self, method, url, body=None, extra=None):
        headers = dict(self.headers, **(extra or {}))
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        status = None
        for attempt in range(TRIES):
            status, rheaders, rbody = self.send(method, url, headers, data)
            if status == 429 or status >= 500:
                wait = _header(rheaders, "Retry-After") or _header(rheaders, "Backoff")
                self.sleep(float(wait) if wait else min(2 ** attempt, 60))
                continue
            if _header(rheaders, "Backoff"):
                self.sleep(float(_header(rheaders, "Backoff")))
            return status, rbody
        raise RuntimeError(f"{method} {url.split('?')[0]}: Zotero still failing after {TRIES} tries (HTTP {status})")

    def get_items(self, keys):
        out = []
        for i in range(0, len(keys), BATCH):
            query = urllib.parse.urlencode({"itemKey": ",".join(keys[i:i + BATCH]), "format": "json"})
            status, body = self._request("GET", f"{self.base}/items?{query}")
            if status != 200:
                raise RuntimeError(f"reading items from Zotero: HTTP {status} {body[:200]!r}")
            out.extend(json.loads(body))
        return out

    def update_items(self, objects):
        """Write objects back (each with its key and version). Returns the keys that succeeded and the failures."""
        result = {"successful": [], "failed": []}
        for i in range(0, len(objects), BATCH):
            batch = objects[i:i + BATCH]
            status, body = self._request("POST", f"{self.base}/items", body=batch,
                                         extra={"Zotero-Write-Token": secrets.token_hex(16)})
            if status != 200:
                message = body.decode("utf-8", "replace")[:300]
                result["failed"] += [{"key": o["key"], "code": status, "message": message} for o in batch]
                continue
            r = json.loads(body)
            for idx in [*r.get("successful", {}), *r.get("unchanged", {})]:
                result["successful"].append(batch[int(idx)]["key"])
            for idx, err in r.get("failed", {}).items():
                result["failed"].append({"key": batch[int(idx)]["key"], "code": err.get("code"),
                                         "message": err.get("message", "")})
        return result
