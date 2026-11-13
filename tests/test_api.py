"""The Zotero Web API client: batching, headers, back-off and per-object results."""
import json
from urllib.parse import parse_qs, urlparse

import pytest

from zotero_relink.api import ZoteroAPI


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)   # (status, headers, body) per request, in order
        self.requests = []

    def __call__(self, method, url, headers, body):
        self.requests.append({"method": method, "url": url, "headers": headers,
                              "body": json.loads(body) if body else None})
        status, headers, payload = self.responses.pop(0)
        return status, headers, json.dumps(payload).encode()


def client(http, sleeps=None):
    return ZoteroAPI("SECRETKEY", 123, send=http, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_items_are_read_fifty_keys_at_a_time():
    keys = [f"K{i:07d}" for i in range(120)]
    http = FakeHTTP([(200, {}, [{"key": k} for k in keys[i:i + 50]]) for i in range(0, 120, 50)])
    items = client(http).get_items(keys)
    asked = [parse_qs(urlparse(r["url"]).query)["itemKey"][0].split(",") for r in http.requests]
    assert [len(a) for a in asked] == [50, 50, 20] and sum(asked, []) == keys
    assert [i["key"] for i in items] == keys


def test_the_key_goes_in_a_header_never_in_the_url():
    http = FakeHTTP([(200, {}, [])])
    client(http).get_items(["ABCD1234"])
    req = http.requests[0]
    assert req["headers"]["Zotero-API-Key"] == "SECRETKEY" and req["headers"]["Zotero-API-Version"] == "3"
    assert "SECRETKEY" not in req["url"] and req["url"].startswith("https://api.zotero.org/users/123/items")


def test_it_waits_and_retries_when_told_to_slow_down():
    sleeps = []
    http = FakeHTTP([(429, {"Retry-After": "7"}, {}), (200, {}, [{"key": "ABCD1234"}])])
    assert client(http, sleeps).get_items(["ABCD1234"]) == [{"key": "ABCD1234"}]
    assert sleeps == [7.0]


def test_it_honors_a_backoff_header_on_success():
    sleeps = []
    http = FakeHTTP([(200, {"Backoff": "3"}, [])])
    client(http, sleeps).get_items(["ABCD1234"])
    assert sleeps == [3.0]


def test_a_server_that_keeps_failing_is_an_error():
    http = FakeHTTP([(503, {}, {})] * 8)
    with pytest.raises(RuntimeError):
        client(http).get_items(["ABCD1234"])


def test_writes_report_each_object_by_key():
    objs = [{"key": "AAAA0001", "version": 1}, {"key": "AAAA0002", "version": 1}, {"key": "AAAA0003", "version": 4}]
    http = FakeHTTP([(200, {}, {"successful": {"0": {"key": "AAAA0001"}}, "unchanged": {"1": "AAAA0002"},
                                "failed": {"2": {"key": "AAAA0003", "code": 412, "message": "modified"}}})])
    result = client(http).update_items(objs)
    assert result == {"successful": ["AAAA0001", "AAAA0002"],
                      "failed": [{"key": "AAAA0003", "code": 412, "message": "modified"}]}
    req = http.requests[0]
    assert req["method"] == "POST" and req["body"] == objs and req["headers"]["Zotero-Write-Token"]


def test_a_refused_batch_fails_every_object_in_it():
    http = FakeHTTP([(403, {}, {"error": "Write access denied"})])
    result = client(http).update_items([{"key": "AAAA0001", "version": 1}])
    assert result["successful"] == [] and [(f["key"], f["code"]) for f in result["failed"]] == [("AAAA0001", 403)]


def test_writes_go_fifty_objects_at_a_time():
    objs = [{"key": f"K{i:07d}", "version": 1} for i in range(60)]
    http = FakeHTTP([(200, {}, {"successful": {str(j): {} for j in range(50)}}),
                     (200, {}, {"successful": {str(j): {} for j in range(10)}})])
    result = client(http).update_items(objs)
    assert [len(r["body"]) for r in http.requests] == [50, 10] and len(result["successful"]) == 60
