<p align="center">
  <img src="assets/logo.svg" alt="" width="132">
</p>

<h1 align="center">zotero-relink</h1>

<p align="center"><b>Move and rename your PDFs however you like. Zotero keeps up.</b></p>

<p align="center">
  <a href="https://github.com/andrewboldi/zotero-relink/actions/workflows/test.yml"><img alt="tests" src="https://img.shields.io/github/actions/workflow/status/andrewboldi/zotero-relink/test.yml?branch=main&label=tests&style=flat-square"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/andrewboldi/zotero-relink?style=flat-square"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white">
  <img alt="Zotero 7+" src="https://img.shields.io/badge/Zotero-7%2B-cc2936?style=flat-square">
</p>

Have you ever renamed a PDF, tidied a folder, or let a script reorganize your files, and then found
half your Zotero library saying *"The attached file could not be found"*?

zotero-relink keeps Zotero's linked files linked. Move or rename them however you like (in your file
manager, with `mv`, with `git`, or with a script), and within about ten minutes Zotero points to the new
place again.

<p align="center">
  <img src="assets/demo.gif" alt="Zotero's library above, a shell below. A PDF is renamed, then its whole folder, and all three papers show 'The attached file could not be found.' Running zotero-relink finds each file by its inode and fixes all three links; the library shows them at their new paths." width="820">
</p>

## How it works

- zotero-relink remembers what each linked file is: its inode, size and SHA-256.
- When a file goes missing, zotero-relink finds it again, first near where it was and then everywhere.
  A rename keeps the inode; a copy keeps the content.
- It updates the attachment's path through the Zotero Web API, and Zotero picks the change up at its
  next sync.
- It never writes Zotero's database, and it never guesses. If two files fit equally well, or the file
  was deleted, zotero-relink tells you and leaves the link alone.

## Install

```sh
curl -LsSf https://raw.githubusercontent.com/andrewboldi/zotero-relink/main/install.sh | sh
```

This installs zotero-relink and asks once for a Zotero API key with write access. It then runs every
10 minutes, with systemd on Linux or launchd on macOS.

`zotero-relink status` shows what the last run found, and `zotero-relink check` shows what it would
change without changing anything.

More: [how it works](docs/how-it-works.md) · [limitations](docs/limitations.md) ·
[uninstall](docs/how-it-works.md#uninstall) · [contributing](CONTRIBUTING.md)
