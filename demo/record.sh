#!/usr/bin/env bash
# Records assets/demo.gif. Needs tmux, asciinema and agg, and the repo's venv (uv sync).
# Everything happens in a throwaway world: a temporary home folder with three papers, a tiny Zotero
# library that links them, and a stand-in for the Zotero Web API on localhost. A real Zotero library
# is never touched.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
py="$repo/.venv/bin/python"
work=$(mktemp -d /tmp/zotero-relink-demo.XXXXXX)
server=
cleanup() {
  set +e
  tmux -L zr-demo kill-server 2>/dev/null
  tmux -L zr-rec kill-server 2>/dev/null
  [ -n "$server" ] && kill "$server" 2>/dev/null
  rm -rf "$work"
}
trap cleanup EXIT

port=$("$py" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
"$py" "$here/world.py" setup "$work"
"$py" "$here/world.py" serve "$work" "$port" &
server=$!
mkdir -p "$work/bin"
cat > "$work/bin/zotero-relink" <<EOF
#!/bin/sh
ZOTERO_DATA_DIR="$work/home/Zotero" ZOTERO_API_URL="http://127.0.0.1:$port" exec "$py" -m zotero_relink.cli "\$@"
EOF
printf '#!/bin/sh\nexec "%s" "%s/world.py" view "%s"\n' "$py" "$here" "$work" > "$work/bin/library"
chmod +x "$work/bin/zotero-relink" "$work/bin/library"
sleep 0.5
# zotero-relink has seen the files once already, as its timer would have.
HOME="$work/home" "$work/bin/zotero-relink" --quiet

tmux -L zr-rec -f /dev/null new-session -d -x 100 -y 24 \
  "asciinema rec --overwrite --cols 100 --rows 24 -c '$here/driver.sh $work' $work/demo.cast; tmux -L zr-rec wait-for -S recorded"
tmux -L zr-rec wait-for recorded
# End on the scene's last frame, not on tmux leaving the screen when it detaches.
"$py" - "$work/demo.cast" <<'PY'
import json, sys
lines = open(sys.argv[1]).read().splitlines()
keep = [lines[0]]
for line in lines[1:]:
    if "\x1b[?1049l" in json.loads(line)[2]:
        break
    keep.append(line)
open(sys.argv[1], "w").write("\n".join(keep) + "\n")
PY
agg --theme monokai --font-size 15 --idle-time-limit 2 --last-frame-duration 4 "$work/demo.cast" "$repo/assets/demo.gif"
cp "$work/demo.cast" "${DEMO_CAST:-/dev/null}" 2>/dev/null || true
echo "wrote $repo/assets/demo.gif"
