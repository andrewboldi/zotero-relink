#!/usr/bin/env bash
# Plays the demo inside tmux: the Zotero library above, a shell below. Run by record.sh.
work=$1
T() { tmux -L zr-demo -f "$work/tmux.conf" "$@"; }

cat > "$work/tmux.conf" <<'CONF'
set -g status off
set -g default-terminal tmux-256color
set -g pane-border-style fg=colour239
set -g pane-active-border-style fg=colour239
CONF
cat > "$work/bashrc" <<'RC'
PS1='\[\e[34m\]\w\[\e[0m\] \[\e[32m\]❯\[\e[0m\] '
RC

export HOME="$work/home" PATH="$work/bin:$PATH"
unset TMUX TMUX_PANE
T new-session -d -s demo -x 100 -y 24 -c "$HOME" "bash --noprofile --rcfile $work/bashrc -i"
T split-window -v -b -l 6 -t demo "$work/bin/library"
T select-pane -t demo:0.1

say() {  # type like a person, then press Enter
  local s=$1 i
  for ((i = 0; i < ${#s}; i++)); do T send-keys -t demo:0.1 -l -- "${s:i:1}"; sleep 0.035; done
  sleep 0.6
  T send-keys -t demo:0.1 Enter
}

director() {
  sleep 2.5
  say "ls Papers"
  sleep 2
  say "mv Papers/attention.pdf 'Papers/Vaswani 2017.pdf'"
  sleep 3
  say "mv Papers Reading"
  sleep 3.5
  say "zotero-relink"
  sleep 6
  T detach-client
}

director &
T attach -t demo
