# How zotlink works

Each run (every 10 minutes, and soon after login) does one pass. Every step only reads, except step 4.

1. **Read the library.** zotlink copies `zotero.sqlite` to a temporary file and reads the copy, because
   Zotero keeps the live database locked. It reads the linked files ("Link to File…") in your personal
   library, leaving out anything in Zotero's trash. Files Zotero stores itself, in its `storage` folder,
   never break when you move your own files, so zotlink leaves them alone.

2. **Remember what each file is.** For every linked file that exists, zotlink records its device, inode,
   size, modification time and SHA-256 in `~/.local/state/zotlink/state.json`. It reads a file again only
   when its size or modification time changes, so after the first run a pass takes seconds.

3. **Find the files that moved.** For each linked file that is missing, zotlink looks in this order:
   - **Near where it was.** It searches the closest folder that still exists, which covers renames and
     most moves in milliseconds.
   - **Everywhere under your home folder.** Hidden folders and Zotero's own data folder are skipped.
   - **By inode first.** A rename or a move on the same disk keeps the inode, so the file is certain.
     The size must match as well, so an inode number reused by an unrelated file is never taken.
   - **Then by content.** A copy, a move to another disk, or a checkout by `git` gives a new inode but
     keeps the SHA-256.

   If two copies fit equally well, the one with the old file name wins. If they also share the name,
   zotlink reports them and changes nothing.

   A file that can't be found is searched for everywhere again after an hour, then after 2, 4 and so on,
   up to once a week. The nearby search still runs every time. A file found in the trash is reported as
   being in the trash.

4. **Fix the link.**
   - zotlink reads the attachment from zotero.org.
   - If the path there is still the one Zotero had locally (or one zotlink wrote itself), zotlink writes
     the new path, along with the version it read. Zotero then refuses the write if anyone changed the item
     in between, and zotlink reads the item again and retries once.
   - If the attachment's title was just the old file name, the title follows the new name.
   - Paths stored relative to Zotero's linked attachment base directory stay relative.
   - Zotero desktop gets the change at its next sync. Until then, zotlink waits and does not send the
     fix again.

Every link zotlink fixes is appended to `~/.local/state/zotlink/log.jsonl` (time, key, old path,
new path, and whether the inode or the content matched).

## Commands

| Command | What it does |
|---|---|
| `zotlink` | one pass: remember files, find moved ones, fix their links |
| `zotlink check` | the same pass, but only says what it would change |
| `zotlink status` | what the last run found, including files it couldn't find |

Options: `--data-dir` (Zotero's data directory, found automatically), `--root` (where to look; default
your home folder; repeatable), `--skip` (a folder not to look in), `--env-file` (default
`~/.config/zotlink/env`), `--quiet`.

The API key is read from `ZOTERO_API_KEY` and `ZOTERO_USER_ID`, in the environment or in the env file.

## Uninstall

```sh
systemctl --user disable --now zotlink.timer      # Linux
launchctl unload ~/Library/LaunchAgents/io.github.zotlink.plist   # macOS
uv tool uninstall zotlink
```

Then delete `~/.config/zotlink` and `~/.local/state/zotlink`, and revoke the API key on zotero.org.
