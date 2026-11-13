#!/bin/sh
# Installs zotero-relink and runs it every 10 minutes. Run it again to update.
set -eu

REPO="${ZOTERO_RELINK_SOURCE:-git+https://github.com/andrewboldi/zotero-relink}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
ENV_FILE="$CONFIG/zotero-relink/env"

# 1. uv, which installs Python tools in their own environment
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi

# 2. zotero-relink (copies, not links, so clearing uv's cache can't break it)
uv tool install --force --link-mode=copy "$REPO"
BIN="$(uv tool dir --bin)/zotero-relink"

# 3. a Zotero API key with write access, asked for once
if [ ! -s "$ENV_FILE" ]; then
  echo
  echo "zotero-relink fixes links through the Zotero Web API, so it needs an API key."
  echo "Create one at https://www.zotero.org/settings/keys/new with 'Allow library access'"
  echo "and 'Allow write access'. Your user ID is on https://www.zotero.org/settings/keys"
  printf "API key: "; read -r key </dev/tty
  printf "User ID: "; read -r uid </dev/tty
  mkdir -p "$CONFIG/zotero-relink"
  (umask 077; printf 'ZOTERO_API_KEY=%s\nZOTERO_USER_ID=%s\n' "$key" "$uid" >"$ENV_FILE")
fi

# 4. every 10 minutes, and soon after you log in
case "$(uname -s)" in
  Linux)
    units="$CONFIG/systemd/user"
    mkdir -p "$units"
    cat >"$units/zotero-relink.service" <<EOF
[Unit]
Description=Keep Zotero's linked files linked (zotero-relink)

[Service]
Type=oneshot
ExecStart=$BIN --quiet
Nice=10
IOSchedulingClass=idle
EOF
    cat >"$units/zotero-relink.timer" <<EOF
[Unit]
Description=Run zotero-relink every 10 minutes

[Timer]
OnStartupSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now zotero-relink.timer
    ;;
  Darwin)
    plist="$HOME/Library/LaunchAgents/io.github.zotero-relink.plist"
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat >"$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>io.github.zotero-relink</string>
  <key>ProgramArguments</key><array><string>$BIN</string><string>--quiet</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/zotero-relink.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/zotero-relink.log</string>
</dict></plist>
EOF
    launchctl unload "$plist" 2>/dev/null || true
    launchctl load "$plist"
    ;;
  *)
    echo "Run '$BIN' on a schedule yourself (see docs/how-it-works.md)."
    ;;
esac

# 5. remember every linked file now (the first run reads each file once)
echo
"$BIN"
echo "zotero-relink is installed. 'zotero-relink status' shows what the last run found."
