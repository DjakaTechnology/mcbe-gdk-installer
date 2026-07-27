#!/usr/bin/env bash
set -uo pipefail
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
export BOL_HOME="$ROOT/profile"
export PROTON_USE_WOW64=1
APP="$HOME/.local/opt/bedrock-on-linux/BedrockOnLinux.AppImage"
LOG="$BOL_HOME/logs/desktop-launch.log"
CACHE="$BOL_HOME/graphics-cache"
LOCK="$BOL_HOME/.desktop-launch.lock"
GPU_MARKER="$BOL_HOME/.gpu-launch-in-progress.json"
RECOVER_CMD="mcbe-gdk-linux-recover"

notify() {
  if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name='MCBE GDK Linux' --icon=minecraft \
      "$1" "$2" >/dev/null 2>&1 || true
  fi
}

[[ -x "$APP" ]] || {
  notify 'MCBE GDK Linux' \
    'BedrockOnLinux is missing; rerun install.sh.'
  exit 1
}
command -v flock >/dev/null 2>&1 || {
  notify 'MCBE GDK Linux' 'flock is required.'
  exit 1
}

mkdir -p "$BOL_HOME/logs" "$CACHE/vkd3d" "$CACHE/dxvk" "$CACHE/nvidia"
exec 9>"$LOCK"
if ! flock -n 9; then
  notify 'MCBE GDK Linux is already starting or running' \
    'Wait for the game window instead of clicking the launcher again.'
  exit 0
fi

if [[ -f "$GPU_MARKER" ]]; then
  current_boot="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
  marker_boot="$(
    grep -o '"boot_id":"[^"]*"' "$GPU_MARKER" 2>/dev/null |
      head -1 | cut -d'"' -f4 || true
  )"
  marker_pid="$(
    grep -o '"launcher_pid":[0-9]*' "$GPU_MARKER" 2>/dev/null |
      head -1 | cut -d: -f2 || true
  )"
  if [[ "$marker_pid" =~ ^[0-9]+$ ]] &&
      kill -0 "$marker_pid" 2>/dev/null; then
    notify 'MCBE GDK Linux is already running' \
      'Close the existing game session before launching it again.'
  elif [[ -n "$current_boot" && "$marker_boot" == "$current_boot" ]]; then
    notify 'MCBE GDK Linux needs one reboot' \
      "A previous GPU session was interrupted. Reboot Linux, then run: $RECOVER_CMD"
  else
    notify 'MCBE GDK Linux recovery required' \
      "Run: $RECOVER_CMD"
  fi
  exit 3
fi

# Custom engines are intentionally outside BOL's managed-engine cache path.
# Supply equivalent persistent caches explicitly and keep heavyweight Proton
# diagnostics off during normal play.
export BOL_DIAG="${BOL_DIAG:-0}"
export BOL_XCURL_LOG="${BOL_XCURL_LOG:-0}"
export VKD3D_SHADER_CACHE_PATH="$CACHE/vkd3d"
export DXVK_SHADER_CACHE_PATH="$CACHE/dxvk"
export __GL_SHADER_DISK_CACHE=1
export __GL_SHADER_DISK_CACHE_PATH="$CACHE/nvidia"
export __GL_SHADER_DISK_CACHE_SIZE=1073741824

# Some GDK builds can expose a native assertion dialog during a Wine startup race.
# Suppress the dialog/debug break without disabling addon or script debugging.
while IFS= read -r -d '' options; do
  grep -q '^dev_assertions_debug_break:' "$options" && \
    sed -i 's/^dev_assertions_debug_break:.*/dev_assertions_debug_break:0/' "$options" || \
    printf '\ndev_assertions_debug_break:0\n' >> "$options"
  grep -q '^dev_assertions_show_dialog:' "$options" && \
    sed -i 's/^dev_assertions_show_dialog:.*/dev_assertions_show_dialog:0/' "$options" || \
    printf 'dev_assertions_show_dialog:0\n' >> "$options"
done < <(find "$BOL_HOME/compatdata" -type f -name options.txt -print0 2>/dev/null || true)

notify 'Starting MCBE GDK Linux…' \
  'Xbox pre-authentication can take several seconds. Only click once.'
printf '\n[%(%F %T)T] Launch requested\n' -1 >> "$LOG"
start=$SECONDS
"$APP" play "$@" >> "$LOG" 2>&1
rc=$?
elapsed=$((SECONDS - start))
printf '[%(%F %T)T] Launcher exited rc=%d elapsed=%ds\n' \
  -1 "$rc" "$elapsed" >> "$LOG"

if (( rc != 0 )); then
  notify 'MCBE GDK Linux failed to start' "See $LOG"
elif (( elapsed < 8 )); then
  notify 'MCBE GDK Linux exited before opening' "See $LOG"
fi
exit "$rc"
