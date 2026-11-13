# Contributing

```sh
git clone https://github.com/andrewboldi/zotero-relink && cd zotero-relink
uv sync
uv run pytest
```

zotero-relink has no runtime dependencies beyond Python's standard library. Please keep it that way.

## Two rules every change keeps

1. **Never write `zotero.sqlite`.** Read a copy. Changes go through the Zotero Web API.
2. **Never guess.** When two files fit equally well, report them and change nothing. A wrong link is
   worse than a broken one, because nobody notices it.

## Tests

- Every change comes with a test that fails without it.
- The tests use a tiny `zotero.sqlite` with the real table names and an in-memory stand-in for the
  Web API (`tests/conftest.py`). They move real files around in a temporary folder.
- No test touches the network or your real library.

## Ideas that would help

- Group libraries (the API path is `/groups/<id>` instead of `/users/<id>`).
- Windows: `st_ino` is the NTFS file ID there, and scheduling would use Task Scheduler.
- A desktop notification when a file can't be found.
