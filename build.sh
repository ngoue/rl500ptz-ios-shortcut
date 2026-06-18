#!/bin/bash
# Build the RL500 shortcut from src/build.py into dist/.
# Usage: ./build.sh
set -euo pipefail
cd "$(dirname "$0")"

NAME="Camera Control"

python3 src/build.py                                          # src/build.py -> dist/rl500.json
plutil -convert binary1 -o "dist/$NAME.plist" dist/rl500.json # json         -> binary plist
plutil -lint "dist/$NAME.plist"                               # sanity check
cp "dist/$NAME.plist" "dist/$NAME (unsigned).shortcut"        # sign requires a .shortcut input
shortcuts sign --mode anyone \
  --input "dist/$NAME (unsigned).shortcut" \
  --output "dist/$NAME.shortcut"                              # -> signed, shareable
echo "Built: dist/$NAME.shortcut"
