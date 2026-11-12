#!/usr/bin/env bash
# Install / start / stop the AWS Emulator without root (extracts the .deb with dpkg-deb -x).
#
#   scripts/emulator.sh install [--version X.Y.Z] [--from-source [--ref <git-ref>]]
#   scripts/emulator.sh start | stop | restart | status | env | version-json
#
# Default install = latest LTS .deb from downloads.aws.com. --from-source builds the router from
# github.com/aws/aws-emulator with cargo (needs a Rust toolchain and ~100 GB disk) and wraps the
# binary in a local .deb with the same /opt/aws-emulator layout.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EMU_DIR="${EMU_DIR:-$HERE/.emulator}"          # git-ignored
BIN="$EMU_DIR/root/opt/aws-emulator/bin/aws-emulator"
PORT="${EMULATOR_DATA_PORT:-9297}"
STATE="$HOME/.aws/emulator/$PORT"
BASE_URL="https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS"
# Ports for per-resource listeners (RDS clusters, CloudFront distributions).
export EMULATOR_LISTENER_PORT_RANGE="${EMULATOR_LISTENER_PORT_RANGE:-19300-19499}"

die() { echo "emulator.sh: $*" >&2; exit 1; }

install_deb() {
  local deb="$1" source="$2"
  rm -rf "$EMU_DIR/root"
  mkdir -p "$EMU_DIR/root"
  dpkg-deb -x "$deb" "$EMU_DIR/root"
  cp "$deb" "$EMU_DIR/aws-emulator.deb"
  sha256sum "$deb" | cut -d' ' -f1 > "$EMU_DIR/deb.sha256"
  echo "$source" > "$EMU_DIR/source"
  "$BIN" -v
}

cmd_install() {
  local version="" from_source=0 ref="main"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version) version="$2"; shift 2 ;;
      --from-source) from_source=1; shift ;;
      --ref) ref="$2"; shift 2 ;;
      *) die "unknown option $1" ;;
    esac
  done
  mkdir -p "$EMU_DIR"
  if [[ $from_source == 1 ]]; then
    command -v cargo >/dev/null || die "--from-source needs cargo (rustup) on PATH"
    local src="$EMU_DIR/src"
    if [[ ! -d "$src/.git" ]]; then
      git clone --filter=blob:none https://github.com/aws/aws-emulator "$src"
    fi
    git -C "$src" fetch --depth 1 origin "$ref"
    git -C "$src" checkout -q FETCH_HEAD
    local commit; commit="$(git -C "$src" rev-parse HEAD)"
    echo "Building aws-emulator-router at $commit (needs ~100 GB free for target/)..."
    (cd "$src" && cargo build --release -p aws-emulator-router)
    local pkg="$EMU_DIR/pkg"; rm -rf "$pkg"
    mkdir -p "$pkg/DEBIAN" "$pkg/opt/aws-emulator/bin" "$pkg/usr/bin"
    local built; built="$(find "$src/target/release" -maxdepth 1 -type f -perm -u+x -name 'aws-emulator*' | head -1)"
    [[ -n "$built" ]] || die "could not find the built emulator binary in target/release"
    cp "$built" "$pkg/opt/aws-emulator/bin/aws-emulator"
    ln -s /opt/aws-emulator/bin/aws-emulator "$pkg/usr/bin/aws-emulator"
    cat > "$pkg/DEBIAN/control" <<CTL
Package: aws-emulator
Version: 0.0.0+src.${commit:0:12}-1
Architecture: amd64
Maintainer: local source build
Description: AWS Emulator built from source at $commit
CTL
    dpkg-deb --build "$pkg" "$EMU_DIR/aws-emulator-src.deb" >/dev/null
    install_deb "$EMU_DIR/aws-emulator-src.deb" "source-build@$commit"
  else
    local url
    if [[ -n "$version" ]]; then url="$BASE_URL/aws-emulator_${version}-1_amd64.deb"
    else url="$BASE_URL/latest/aws-emulator_amd64.deb"; fi
    echo "Downloading $url"
    curl -fsSL -o "$EMU_DIR/download.deb" "$url"
    install_deb "$EMU_DIR/download.deb" "$([[ -n $version ]] && echo "deb@$version" || echo deb-latest)"
    rm -f "$EMU_DIR/download.deb"
  fi
}

healthy() { curl -fsS --cacert "$STATE/ca.pem" "https://127.0.0.1:$PORT/__admin/health" >/dev/null 2>&1; }

cmd_start() {
  [[ -x "$BIN" ]] || die "not installed; run: $0 install"
  if [[ -f "$EMU_DIR/pid" ]] && kill -0 "$(cat "$EMU_DIR/pid")" 2>/dev/null; then
    echo "already running (pid $(cat "$EMU_DIR/pid"))"; return 0
  fi
  # Telemetry off for reproducible, private runs. --idle-timeout guards against forgotten runs.
  nohup "$BIN" -p "$PORT" -t off --idle-timeout "${EMULATOR_IDLE_TIMEOUT:-21600}" \
    > "$EMU_DIR/emulator.log" 2>&1 &
  echo $! > "$EMU_DIR/pid"
  for _ in $(seq 1 100); do
    [[ -f "$STATE/ca.pem" ]] && healthy && { echo "emulator up on https://127.0.0.1:$PORT (pid $(cat "$EMU_DIR/pid"))"; return 0; }
    sleep 0.2
  done
  tail -20 "$EMU_DIR/emulator.log"; die "emulator did not become healthy"
}

cmd_stop() {
  if [[ -f "$EMU_DIR/pid" ]]; then
    kill "$(cat "$EMU_DIR/pid")" 2>/dev/null || true
    for _ in $(seq 1 50); do kill -0 "$(cat "$EMU_DIR/pid")" 2>/dev/null || break; sleep 0.1; done
    rm -f "$EMU_DIR/pid"
  fi
  echo "emulator stopped"
}

cmd_env() {
  # eval "$(scripts/emulator.sh env)"
  # Env-provided keys would win over the credentials file, so clear them.
  cat <<ENV
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
export AWS_CONFIG_FILE="$STATE/config"
export AWS_SHARED_CREDENTIALS_FILE="$STATE/emulator_credentials"
export AWS_CA_BUNDLE="$STATE/ca.pem"
export AWS_ENDPOINT_URL="https://127.0.0.1:$PORT"
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export AWS_PROFILE=default
export EMULATOR_STATE_DIR="$STATE"
export TF_VAR_emulator_ca_bundle="$STATE/ca.pem"
export TF_VAR_emulator_credentials_file="$STATE/emulator_credentials"
export TF_VAR_emulator_endpoint="https://127.0.0.1:$PORT"
ENV
}

cmd_version_json() {
  # Machine-readable description of the installed emulator (used by update_check.py).
  [[ -x "$BIN" ]] || die "not installed"
  "$BIN" -v | python3 -c '
import json, sys, os
kv = dict(l.split(":", 1) for l in sys.stdin.read().strip().splitlines())
kv = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in kv.items()}
emu = sys.argv[1]
print(json.dumps({
  "version": kv.get("version"),
  "release_date": kv.get("release_date"),
  "commit": kv.get("commit"),
  "deb_sha256": open(os.path.join(emu, "deb.sha256")).read().strip(),
  "source": open(os.path.join(emu, "source")).read().strip(),
}, indent=2))' "$EMU_DIR"
}

case "${1:-}" in
  install) shift; cmd_install "$@" ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status) healthy && echo "healthy on $PORT" || { echo "not running"; exit 1; } ;;
  env) cmd_env ;;
  version-json) cmd_version_json ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
