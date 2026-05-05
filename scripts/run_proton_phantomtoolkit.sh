#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run PhantomToolkit.exe inside a Steam Proton prefix (Linux).

Usage:
  scripts/run_proton_phantomtoolkit.sh --exe /path/to/PhantomToolkit.exe [--appid <steam_appid>] [--proton /path/to/proton]

Examples:
  # Elden Ring (1245620)
  scripts/run_proton_phantomtoolkit.sh --appid 1245620 --exe "$PWD/dist/windows-0.1.0/PhantomToolkit.exe"

  # Dark Souls III (374320)
  scripts/run_proton_phantomtoolkit.sh --appid 374320 --exe "$PWD/dist/windows-0.1.0/PhantomToolkit.exe"

  # Auto-detect running game (eldenring.exe / DarkSoulsIII.exe)
  scripts/run_proton_phantomtoolkit.sh --exe "$PWD/dist/windows-0.1.0/PhantomToolkit.exe"

Notes:
  - Start the game first via Steam, then run this script.
  - Supports native Steam and Flatpak Steam.
  - Override Steam root via STEAM_ROOT=/path/to/Steam.
EOF
}

appid=""
exe=""
proton=""

# Auto-detect EXE if running inside AppImage
if [[ -n "${APPDIR:-}" && -f "$APPDIR/usr/bin/PhantomToolkit.exe" ]]; then
  exe="$APPDIR/usr/bin/PhantomToolkit.exe"
fi

detect_steam_root() {
  if [[ -n "${STEAM_ROOT:-}" && -d "${STEAM_ROOT:-}" ]]; then
    echo "${STEAM_ROOT}"
    return 0
  fi

  # Native Steam (common locations)
  for p in "$HOME/.steam/steam" "$HOME/.local/share/Steam"; do
    if [[ -d "$p/steamapps" ]]; then
      echo "$p"
      return 0
    fi
  done

  # Flatpak Steam
  fp="$HOME/.var/app/com.valvesoftware.Steam/data/Steam"
  if [[ -d "$fp/steamapps" ]]; then
    echo "$fp"
    return 0
  fi

  return 1
}

detect_running_game_appid() {
  # We intentionally match the Windows exe names in the Proton command line.
  # Elden Ring: 1245620
  # Dark Souls III: 374320
  if ps -eo args 2>/dev/null | grep -Fqi "eldenring.exe"; then
    echo "1245620"
    return 0
  fi
  if ps -eo args 2>/dev/null | grep -Fqi "dark souls iii" || ps -eo args 2>/dev/null | grep -Fqi "darksoulsiii.exe"; then
    echo "374320"
    return 0
  fi
  return 1
}

pick_free_port() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    python - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
    return 0
  fi
  echo "8000"
}

wait_for_server() {
  local url="$1"
  local deadline=$((SECONDS + 20))

  local host=""
  local port=""
  if [[ "$url" =~ ^https?://([^:/]+):([0-9]+) ]]; then
    host="${BASH_REMATCH[1]}"
    port="${BASH_REMATCH[2]}"
  fi

  http_ping() {
    local ping_url="${url%/}/ping"
    if command -v curl >/dev/null 2>&1; then
      curl -fsS --max-time 1 "$ping_url" >/dev/null 2>&1
      return $?
    fi
    if command -v wget >/dev/null 2>&1; then
      wget -q -T 1 -O - "$ping_url" >/dev/null 2>&1
      return $?
    fi
    return 127
  }

  tcp_ping() {
    # Best-effort ping without curl/wget. Prefer Python; fall back to bash /dev/tcp.
    if command -v python3 >/dev/null 2>&1; then
      python3 - <<PY 2>/dev/null
import socket, sys
host = ${host@Q}
port = int(${port:-0})
if not host or port <= 0:
    sys.exit(2)
s = socket.socket()
s.settimeout(1.0)
try:
    s.connect((host, port))
    s.sendall(b"GET /ping HTTP/1.0\\r\\nHost: " + host.encode("utf-8") + b"\\r\\n\\r\\n")
    data = s.recv(128)
    sys.exit(0 if b"200" in data or b"ok" in data.lower() else 1)
except Exception:
    sys.exit(1)
finally:
    try: s.close()
    except Exception: pass
PY
      return $?
    fi
    if [[ -n "$host" && -n "$port" ]]; then
      (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1 || return 1
      printf 'GET /ping HTTP/1.0\r\nHost: %s\r\n\r\n' "$host" >&3 || true
      local line=""
      IFS= read -r -t 1 line <&3 || true
      exec 3<&- 3>&- || true
      [[ "$line" == *"200"* || "$line" == *"ok"* ]]
      return $?
    fi
    return 1
  }

  while (( SECONDS < deadline )); do
    if http_ping; then
      return 0
    fi
    if tcp_ping; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

open_url() {
  local url="$1"
  if [[ -n "${PHANTOM_BROWSER_CMD:-}" ]]; then
    # shellcheck disable=SC2086
    nohup ${PHANTOM_BROWSER_CMD} "$url" >/dev/null 2>&1 &
    return 0
  fi
  if command -v chromium >/dev/null 2>&1; then
    nohup chromium --app="$url" >/dev/null 2>&1 &
    return 0
  fi
  if command -v google-chrome >/dev/null 2>&1; then
    nohup google-chrome --app="$url" >/dev/null 2>&1 &
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    nohup xdg-open "$url" >/dev/null 2>&1 &
    return 0
  fi
  return 1
}

linux_to_wine_z_path() {
  local p="$1"
  p="${p//\//\\}"
  echo "Z:${p}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --appid)
      appid="${2:-}"; shift 2;;
    --exe)
      exe="${2:-}"; shift 2;;
    --proton)
      proton="${2:-}"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2;;
  esac
done

if [[ -z "$exe" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$exe" ]]; then
  echo "EXE not found: $exe" >&2
  exit 2
fi

steam_root="$(detect_steam_root || true)"
if [[ -z "$steam_root" ]]; then
  echo "Could not locate Steam installation." >&2
  echo "Set STEAM_ROOT to your Steam folder (it should contain steamapps/)." >&2
  exit 2
fi

if [[ -z "$appid" ]]; then
  appid="$(detect_running_game_appid || true)"
fi

if [[ -z "$appid" ]]; then
  echo "Could not auto-detect a running supported game." >&2
  echo "Start Elden Ring or Dark Souls III, or pass --appid explicitly." >&2
  exit 2
fi

compatdata="$steam_root/steamapps/compatdata/$appid"

if [[ ! -d "$compatdata" ]]; then
  echo "Compatdata prefix not found: $compatdata" >&2
  echo "Make sure the game has been launched at least once via Steam." >&2
  exit 2
fi

if [[ -z "$proton" ]]; then
  # Prefer Proton - Experimental, then fall back to any Proton* that exists.
  shopt -s nullglob
  candidates=(
    "$steam_root/steamapps/common/Proton - Experimental/proton"
    "$steam_root/steamapps/common/Proton"*"/proton"
    "$steam_root/steamapps/common/GE-Proton"*"/proton"
    "$steam_root/compatibilitytools.d/"*"/proton"
  )
  shopt -u nullglob

  for p in "${candidates[@]}"; do
    if [[ -x "$p" ]]; then
      proton="$p"
      break
    fi
  done
fi

if [[ -z "$proton" || ! -x "$proton" ]]; then
  echo "Could not find a Proton launcher executable." >&2
  echo "Pass it explicitly: --proton /path/to/proton" >&2
  exit 2
fi

export STEAM_COMPAT_APP_ID="$appid"
export STEAM_COMPAT_DATA_PATH="$compatdata"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$steam_root"

game_key=""
if [[ "$appid" == "1245620" ]]; then
  game_key="eldenring"
elif [[ "$appid" == "374320" ]]; then
  game_key="ds3"
fi

# Auto-wire items assets when items/ lives next to the exe on disk.
if [[ -z "${PHANTOM_ITEMS_DIR:-}" ]]; then
  exe_dir="$(cd "$(dirname "$exe")" && pwd)"
  if [[ -n "$game_key" && -d "$exe_dir/items/$game_key" ]]; then
    export PHANTOM_ITEMS_DIR="$(linux_to_wine_z_path "$exe_dir/items/$game_key")"
  elif [[ -d "$exe_dir/items" ]]; then
    export PHANTOM_ITEMS_DIR="$(linux_to_wine_z_path "$exe_dir/items")"
  fi
fi

echo "Steam root: $steam_root"
echo "Compatdata:  $compatdata"
echo "Proton:      $proton"
echo "EXE:         $exe"
echo ""
echo "Launching PhantomToolkit.exe under Proton (server-only)..."

export PHANTOM_HOST="${PHANTOM_HOST:-127.0.0.1}"
export PHANTOM_PORT="${PHANTOM_PORT:-$(pick_free_port)}"
url="http://${PHANTOM_HOST}:${PHANTOM_PORT}"

# Provide real Linux HOME for Steam path discovery in Proton mode.
export PHANTOM_LINUX_HOME="${PHANTOM_LINUX_HOME:-$HOME}"
export PHANTOM_LAUNCHED_BY_APPIMAGE="1"

# Start native Linux host bridge (dialogs + screenshots + sound) when bundled.
bridge_pid=""
if [[ -n "${APPDIR:-}" && -x "$APPDIR/usr/bin/PhantomHostBridge" ]]; then
  bridge_port="${PHANTOM_HOST_BRIDGE_PORT:-$(pick_free_port)}"
  bridge_url="http://127.0.0.1:${bridge_port}"
  "$APPDIR/usr/bin/PhantomHostBridge" --host 127.0.0.1 --port "${bridge_port}" &
  bridge_pid=$!
  if wait_for_server "${bridge_url}"; then
    export PHANTOM_HOST_BRIDGE_PORT="${bridge_port}"
    export PHANTOM_HOST_BRIDGE_URL="${bridge_url}"
  else
    kill "$bridge_pid" >/dev/null 2>&1 || true
    bridge_pid=""
  fi
fi

cleanup() {
  # Stop Proton/Wine backend (and all children) if still running.
  if [[ -n "${tool_pid:-}" ]]; then
    local self_pgid=""
    local target_pgid=""
    if command -v ps >/dev/null 2>&1; then
      self_pgid="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ' || true)"
      target_pgid="$(ps -o pgid= -p "$tool_pid" 2>/dev/null | tr -d ' ' || true)"
    fi
    if [[ -n "${target_pgid:-}" && -n "${self_pgid:-}" && "$target_pgid" != "$self_pgid" ]]; then
      kill -- -"${target_pgid}" >/dev/null 2>&1 || true
    else
      kill -- -"$tool_pid" >/dev/null 2>&1 || true
    fi
    kill "$tool_pid" >/dev/null 2>&1 || true

    # Ensure we don't leave PhantomToolkit.exe or wineserver running.
    if command -v pkill >/dev/null 2>&1; then
      pkill -TERM -f "PhantomToolkit\\.exe" >/dev/null 2>&1 || true
      sleep 0.2
      pkill -KILL -f "PhantomToolkit\\.exe" >/dev/null 2>&1 || true
    fi
    "$proton" run wineserver -k >/dev/null 2>&1 || true
  fi

  if [[ -n "${bridge_pid:-}" ]]; then
    kill "$bridge_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Use 'runinprefix' to bypass Proton's steam.exe stub (prevents DLC errors).
if command -v setsid >/dev/null 2>&1; then
  setsid "$proton" runinprefix "$exe" --no-webview --launched-by-appimage --host "${PHANTOM_HOST}" --port "${PHANTOM_PORT}" &
else
  "$proton" runinprefix "$exe" --no-webview --launched-by-appimage --host "${PHANTOM_HOST}" --port "${PHANTOM_PORT}" &
fi
tool_pid=$!

if ! wait_for_server "$url"; then
  echo "Backend did not become reachable: $url" >&2
  echo "Check phantomtoolkit_startup.log" >&2
fi

# Try to open native GUI window using system Python3 + GTK/WebKit.
# This avoids bundling any GUI framework in the AppImage.
launch_native_gui() {
  local gui_url="$1"
  # Force X11 backend to avoid Wayland protocol errors with WebKit2.
  export GDK_BACKEND=x11
  # Disable WebKit2 hardware acceleration to avoid GBM buffer errors.
  export WEBKIT_DISABLE_COMPOSITING_MODE=1
  export WEBKIT_DISABLE_DMABUF_RENDERER=1
  python3 - "$gui_url" <<'PYEOF'
import sys

url = sys.argv[1]
launched = False

# Try GTK + WebKit2 (pre-installed on most Linux desktops)
if not launched:
    try:
        import gi
        try:
            gi.require_version('WebKit2', '4.1')
        except ValueError:
            gi.require_version('WebKit2', '4.0')
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, WebKit2

        win = Gtk.Window(title="Phantom Toolkit")
        win.set_default_size(1280, 800)
        win.connect("destroy", Gtk.main_quit)

        wv = WebKit2.WebView()
        wv.load_uri(url)
        win.add(wv)
        win.show_all()
        Gtk.main()
        launched = True
    except Exception:
        pass

# Try pywebview (if user has it installed)
if not launched:
    try:
        import webview
        webview.create_window("Phantom Toolkit", url, width=1280, height=800, resizable=True)
        webview.start(debug=False)
        launched = True
    except Exception:
        pass

sys.exit(0 if launched else 1)
PYEOF
}

if launch_native_gui "$url"; then
  # GUI closed normally; cleanup trap will stop the backend.
  exit 0
else
  # No GUI framework available, fall back to browser.
  open_url "$url" || true
  wait "$tool_pid"
fi

