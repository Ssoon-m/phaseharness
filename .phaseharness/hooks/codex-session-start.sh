#!/usr/bin/env sh
set -eu

hook_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root="$(dirname "$(dirname "$hook_dir")")"
log_dir="$root/.phaseharness/state/logs"
mkdir -p "$log_dir"
if [ "${PHASEHARNESS_UPDATE:-}" != "0" ]; then
  update_log="$log_dir/session-start-update.log"
  python3 "$root/.phaseharness/bin/phaseharness-update.py" apply --quiet >"$update_log" 2>&1 || true
  if [ -s "$update_log" ]; then
    cat "$update_log"
  fi
fi
python3 "$root/.phaseharness/bin/phaseharness-sync-bridges.py" --quiet >"$log_dir/session-start-sync.log" 2>&1 || true
