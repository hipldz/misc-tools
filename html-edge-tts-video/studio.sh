#!/usr/bin/env bash
# Run the project-local Studio in the background without activating a venv.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="$project_root/.venv/bin/python"
server_script="$project_root/studio/server.py"
runtime_dir="$project_root/.local/studio"
pid_file="$runtime_dir/studio.pid"
log_file="$runtime_dir/studio.log"
action=start
bind_host=0.0.0.0
bind_port=10071
base_path="/html2video"

usage() {
    cat <<'EOF'
Usage: ./studio.sh [start|stop|restart|status|logs] [options]

Options for start/restart:
  --host ADDRESS     Bind address (default: 0.0.0.0)
  --port PORT        Listen port (default: 10071)
  --base-path PATH   Public URL prefix, e.g. /xxx (default: /)
  -h, --help         Show this help

Uses .venv/bin/python. PID and log live under .local/studio/.
Each start replaces the previous log. Restart uses the supplied options/defaults.
This script does not install dependencies or configure boot-time startup.
EOF
}

if [[ ${1:-} =~ ^(start|stop|restart|status|logs)$ ]]; then
    action=$1
    shift
fi
while (($#)); do
    case "$1" in
        --host|--port|--base-path)
            if (($# < 2)); then
                echo "Missing value for $1" >&2
                exit 2
            fi
            case "$1" in
                --host) bind_host=$2 ;;
                --port) bind_port=$2 ;;
                --base-path) base_path=$2 ;;
            esac
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

cd -- "$project_root"
mkdir -p -- "$runtime_dir"
exec 9>"$runtime_dir/control.lock"
flock -n 9 || { echo "Another Studio management command is running." >&2; exit 1; }

studio_pid=""
running() {
    [[ -f "$pid_file" ]] || return 1
    studio_pid=$(<"$pid_file")
    [[ "$studio_pid" =~ ^[0-9]+$ && "$studio_pid" -gt 1 ]] || return 1
    kill -0 "$studio_pid" 2>/dev/null || return 1
    local command_line
    command_line=$(ps -p "$studio_pid" -o args=) || return 1
    [[ "$command_line" == *"$server_script"* ]]
}

prepare_start() {
    [[ -x "$python_bin" ]] || { echo "Missing .venv/bin/python; create the project venv first." >&2; return 1; }
    if [[ ! "$bind_port" =~ ^[0-9]{1,5}$ ]] || ((10#$bind_port < 1 || 10#$bind_port > 65535)); then
        echo "Port must be between 1 and 65535." >&2
        return 1
    fi
    bind_port=$((10#$bind_port))
    base_path=$("$python_bin" -c 'import sys; from studio.web_paths import normalize_base_path; import studio.server; print(normalize_base_path(sys.argv[1]))' "$base_path")
}

start_studio() {
    if running; then
        echo "Studio is already running (PID $studio_pid)."
        return
    fi
    rm -f -- "$pid_file"
    : >"$log_file"
    # A separate process group lets stop terminate Studio and its job children.
    # Close the management lock in the child so subsequent commands can acquire it.
    nohup setsid "$python_bin" -u "$server_script" \
        --host "$bind_host" --port "$bind_port" --base-path "$base_path" \
        </dev/null >"$log_file" 2>&1 9>&- &
    studio_pid=$!
    printf '%s\n' "$studio_pid" >"$pid_file"
    local attempt
    for attempt in {1..50}; do
        if ! running; then
            rm -f -- "$pid_file"
            echo "Studio failed to start. Log: $log_file" >&2
            tail -n 30 -- "$log_file" >&2
            return 1
        fi
        if [[ "$(<"$log_file")" == *"[server] Listening on "* ]]; then
            local display_host=$bind_host
            [[ "$display_host" == 0.0.0.0 ]] && display_host=127.0.0.1
            [[ "$display_host" == *:* ]] && display_host="[$display_host]"
            echo "Studio started (PID $studio_pid): http://$display_host:$bind_port$base_path/"
            echo "Log: $log_file"
            return
        fi
        sleep 0.1
    done
    echo "Startup is still pending. Run ./studio.sh status or ./studio.sh logs." >&2
    return 1
}

stop_studio() {
    if ! running; then
        rm -f -- "$pid_file"
        echo "Studio is stopped."
        return
    fi
    local group_id
    group_id=$(ps -p "$studio_pid" -o pgid=)
    group_id=${group_id//[[:space:]]/}
    if [[ "$group_id" != "$studio_pid" ]]; then
        echo "Refusing to stop a process outside the script-managed process group." >&2
        return 1
    fi
    kill -TERM -- "-$studio_pid"
    local attempt
    for attempt in {1..50}; do
        if ! running; then
            rm -f -- "$pid_file"
            echo "Studio stopped."
            return
        fi
        sleep 0.1
    done
    echo "Studio did not stop within 5 seconds; PID retained. Check ./studio.sh logs." >&2
    return 1
}

case "$action" in
    start) prepare_start; start_studio ;;
    stop) stop_studio ;;
    restart) prepare_start; stop_studio; start_studio ;;
    status)
        if running; then
            echo "Studio is running (PID $studio_pid)."
        else
            echo "Studio is stopped."
        fi
        ;;
    logs)
        if [[ -f "$log_file" ]]; then
            tail -n 50 -- "$log_file"
        else
            echo "No Studio log yet."
        fi
        ;;
esac
