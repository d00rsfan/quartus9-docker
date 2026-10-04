#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
    set -- quartus_sh --version
fi
command_name=${1%.exe}
shift
case "$command_name" in
    quartus_*) ;;
    *) printf 'Expected a Quartus command, e.g. quartus_sh --flow compile project.qpf\n' >&2; exit 64 ;;
esac
if [[ ! "$command_name" =~ ^quartus_[a-zA-Z0-9_]+$ ]]; then
    printf 'Invalid Quartus command: %s\n' "$command_name" >&2
    exit 64
fi

install_dir=${QUARTUS_INSTALL_DIR:-/opt/altera/90sp2}
if [[ ! -f "$install_dir/quartus/bin/$command_name.exe" ]]; then
    printf 'Missing compiler: %s/quartus/bin/%s.exe\n' "$install_dir" "$command_name" >&2
    exit 127
fi
install_dir=$(realpath "$install_dir")
for dependency in wine wineboot wineserver xvfb-run xauth; do
    if ! command -v "$dependency" >/dev/null; then
        printf 'Required tool is missing: %s\n' "$dependency" >&2
        exit 127
    fi
done

# A private prefix per invocation supports concurrent builds and arbitrary UIDs.
# Always own the prefix; never modify ~/.wine or another application's prefix.
runtime_dir=$(mktemp -d "${TMPDIR:-/tmp}/quartus9.XXXXXXXX")
export WINEPREFIX="$runtime_dir/wine"
export WINEARCH=${WINEARCH:-win32}
export WINEDEBUG=${WINEDEBUG:--all}
export WINEDLLOVERRIDES=${WINEDLLOVERRIDES:-mscoree,mshtml,winemenubuilder.exe=}
export QUARTUS_ROOTDIR='C:\altera\90sp2\quartus'
export WINEPATH='C:\altera\90sp2\quartus\bin'
child_pid=
cleanup() {
    wineserver -k >/dev/null 2>&1 || true
    if [[ -n "$child_pid" ]]; then
        kill "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    rm -rf -- "$runtime_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Xvfb also covers Wine initialization and any hidden Windows dialogs.
xvfb-run -a -s '-screen 0 1024x768x24 -nolisten tcp' \
    bash -euo pipefail -c '
        install_dir=$1
        command_name=$2
        shift 2
        wineboot --init
        mkdir -p "$WINEPREFIX/drive_c/altera"
        ln -s "$install_dir" "$WINEPREFIX/drive_c/altera/90sp2"
        wine reg add "HKCU\Software\Wine" /v Version /d winxp /f >/dev/null
        wine "C:/altera/90sp2/quartus/bin/$command_name.exe" "$@"
    ' -- "$install_dir" "$command_name" "$@" &
child_pid=$!
status=0
wait "$child_pid" || status=$?
child_pid=
exit "$status"
