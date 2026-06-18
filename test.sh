#!/bin/bash
# Run the test suite (stdlib unittest — no install required).
# Usage: ./test.sh            (verbose)
#        ./test.sh -q         (quiet)
set -euo pipefail
cd "$(dirname "$0")"

python3 -m unittest discover -s tests "${@:--v}"
