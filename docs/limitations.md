# Limitations

- **Zotero sync must be on.** zotlink fixes links on zotero.org, and Zotero desktop applies them when it
  syncs. A library that never syncs can't be fixed this way. zotlink never writes `zotero.sqlite`,
  because Zotero doesn't support that while it runs.
- **Personal library only.** Linked files in group libraries are left alone for now.
- **The key needs write access.** Create it at <https://www.zotero.org/settings/keys/new> with "Allow
  library access" and "Allow write access".
- **zotlink must see a file before it moves.** zotlink recognizes a file by what it recorded on an earlier
  run. A link that was already broken before zotlink's first run is reported, not searched for.
- **Moved and edited in the same 10 minutes.** If a file is both moved and changed between two runs, it
  has a new size and new content at a new path, so zotlink can't be sure it's the same file and reports
  it instead.
- **Hidden folders aren't searched.** Snap and Flatpak builds of Zotero can't open files there anyway.
- **Search roots.** By default zotlink looks under your home folder. Files moved to another disk are
  found if you add that disk with `--root`.
- **The first run reads every linked file once**, to record its SHA-256. With a few thousand PDFs that
  takes a minute or two. Later runs read only files that changed.
- **Windows** isn't tested yet. Contributions are welcome.
- **Zotero versions.** Tested with Zotero 9. The tables zotlink reads have not changed since Zotero 5.
