# How zotero-relink works

Each run (every 10 minutes, and soon after login) does one pass. Every step only reads, except step 4.

1. **Read the library.** zotero-relink copies `zotero.sqlite` to a temporary file and reads the copy, because
   Zotero keeps the live database locked. It reads the linked files ("Link to File…") in your personal
   library, leaving out anything in Zotero's trash. Files Zotero stores itself, in its `storage` folder,
   never break when you move your own files, so zotero-relink leaves them alone.

2. **Remember what each file is.** For every linked file that exists, zotero-relink records its device, inode,
   size, modification time and SHA-256 in `~/.local/state/zotero-relink/state.json`. It reads a file again only
   when its size or modification time changes, so after the first run a pass takes seconds.

3. **Find the files that moved.** For each linked file that is missing, zotero-relink looks in this order:
   - **Near where it was.** It searches the closest folder that still exists, which covers renames and
     most moves in milliseconds.
   - **Everywhere under your home folder and on mounted external drives** (`/media`, `/run/media`, `/mnt`,
     `/Volumes`). Hidden folders and Zotero's own data folder are skipped.
   - **By inode first.** A rename or a move on the same disk keeps the inode, so the file is certain.
     The size and modification time must match as well, so an inode number reused by an unrelated file
     (FAT and exFAT drives make them up) is never taken.
   - **Then by content.** A copy, a move to another disk, or a checkout by `git` gives a new inode but
     keeps the SHA-256.

   If two copies fit equally well, the one with the old file name wins. If they also share the name,
   zotero-relink reports them and changes nothing.

   A file that can't be found is searched for everywhere again after an hour, then after 2, 4 and so on,
   up to once a week. The nearby search still runs every time. A file found in the trash is reported as
   being in the trash.
   A file on an external drive that isn't plugged in is reported as such and left alone, so a copy
   elsewhere never replaces it.

4. **Fix the link.**
   - zotero-relink reads the attachment from zotero.org.
   - If the path there is still the one Zotero had locally (or one zotero-relink wrote itself), zotero-relink writes
     the new path, along with the version it read. Zotero then refuses the write if anyone changed the item
     in between, and zotero-relink reads the item again and retries once.
   - If the attachment's title was just the old file name, the title follows the new name.
   - Paths stored relative to Zotero's linked attachment base directory stay relative.
   - Zotero desktop gets the change at its next sync. Until then, zotero-relink waits and does not send the
     fix again.

Every link zotero-relink fixes is appended to `~/.local/state/zotero-relink/log.jsonl` (time, key, old path,
new path, and whether the inode or the content matched).

## Commands

| Command | What it does |
|---|---|
| `zotero-relink` | one pass: remember files, find moved ones, fix their links |
| `zotero-relink check` | the same pass, but only says what it would change |
| `zotero-relink status` | what the last run found, including files it couldn't find |

Options: `--data-dir` (Zotero's data directory, found automatically), `--root` (where to look; default
your home folder; repeatable), `--skip` (a folder not to look in), `--env-file` (default
`~/.config/zotero-relink/env`), `--quiet`.

The API key is read from `ZOTERO_API_KEY` and `ZOTERO_USER_ID`, in the environment or in the env file.
`ZOTERO_API_URL` points zotero-relink at another Zotero-compatible server; the demo uses a local
stand-in.

## Uninstall

```sh
systemctl --user disable --now zotero-relink.timer      # Linux
launchctl unload ~/Library/LaunchAgents/io.github.zotero-relink.plist   # macOS
uv tool uninstall zotero-relink
```

Then delete `~/.config/zotero-relink` and `~/.local/state/zotero-relink`, and revoke the API key on zotero.org.
