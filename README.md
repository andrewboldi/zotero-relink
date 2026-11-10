<p align="center"><img src="docs/logo.svg" width="96" alt="zotlink logo"></p>

<h1 align="center">zotlink</h1>

<p align="center">
  <a href="https://github.com/andrewboldi/zotlink/actions/workflows/test.yml"><img src="https://github.com/andrewboldi/zotlink/actions/workflows/test.yml/badge.svg" alt="tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Zotero-7%2B-cc2936.svg" alt="Zotero 7+">
</p>

Have you ever renamed a PDF, tidied a folder, or let a script reorganize your files, and then found
half your Zotero library saying *"The attached file could not be found"*?

**zotlink keeps Zotero's linked files linked.** Move or rename them however you like (in your file
manager, with `mv`, with `git`, or with a script), and within about ten minutes Zotero points to the new
place again.

## How it works

- zotlink remembers what each linked file is: its inode, size and SHA-256.
- When a file goes missing, zotlink finds it again, first near where it was and then everywhere.
  A rename keeps the inode; a copy keeps the content.
- It updates the attachment's path through the Zotero Web API, and Zotero picks the change up at its
  next sync.
- It never writes Zotero's database, and it never guesses. If two files fit equally well, or the file
  was deleted, zotlink tells you and leaves the link alone.

## Install

```sh
curl -LsSf https://raw.githubusercontent.com/andrewboldi/zotlink/main/install.sh | sh
```

This installs zotlink and asks once for a Zotero API key with write access. It then runs zotlink every
10 minutes, with systemd on Linux or launchd on macOS.

`zotlink status` shows what the last run found, and `zotlink check` shows what zotlink would change
without changing anything.

More: [how it works](docs/how-it-works.md) · [limitations](docs/limitations.md) ·
[uninstall](docs/how-it-works.md#uninstall) · [contributing](CONTRIBUTING.md)
