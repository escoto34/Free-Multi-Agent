#!/usr/bin/env bash
# Install `multiagent` / `MultiAgent` into ~/.local/bin (on PATH for most setups).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHER="$ROOT/bin/multiagent"
DEST="${HOME}/.local/bin"

if [ ! -x "$LAUNCHER" ]; then
  echo "Missing executable: $LAUNCHER" >&2
  exit 1
fi

mkdir -p "$DEST"
ln -sfn "$LAUNCHER" "$DEST/multiagent"
ln -sfn "$LAUNCHER" "$DEST/MultiAgent"

echo "Installed:"
echo "  $DEST/multiagent  -> $LAUNCHER"
echo "  $DEST/MultiAgent  -> $LAUNCHER"
echo
if ! command -v multiagent >/dev/null 2>&1; then
  echo "Note: $DEST is not on your PATH yet. Add this to your shell config:"
  echo
  echo "  # fish"
  echo "  fish_add_path $DEST"
  echo
  echo "  # bash/zsh"
  echo "  export PATH=\"$DEST:\$PATH\""
  echo
else
  echo "Try:  multiagent"
  echo "      multiagent --help"
fi
