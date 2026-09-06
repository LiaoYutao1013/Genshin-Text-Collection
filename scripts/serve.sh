#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
exec conda run --no-capture-output -n yolo python -m genshin_text.cli serve "$@"
