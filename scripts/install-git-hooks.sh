#!/usr/bin/env bash
# Install repo git hooks into .git/hooks (no git config changes).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$ROOT/.git/hooks"
SRC="$ROOT/.githooks"

if [[ ! -d "$HOOKS_DIR" ]]; then
  echo "install-git-hooks: not a git checkout (.git/hooks missing)" >&2
  exit 1
fi

mkdir -p "$SRC"
for hook in pre-push; do
  if [[ ! -f "$SRC/$hook" ]]; then
    echo "install-git-hooks: missing $SRC/$hook" >&2
    exit 1
  fi
  chmod +x "$SRC/$hook"
  ln -sfn "../../.githooks/$hook" "$HOOKS_DIR/$hook"
  echo "installed $hook -> .githooks/$hook"
done
