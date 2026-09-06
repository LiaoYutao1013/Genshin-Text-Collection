#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
conda run -n yolo python -m pip install -e .
conda run -n yolo python -m py_compile genshin_text/*.py
mkdir -p data/raw exports
echo "Ready in the yolo Conda environment. Run ./scripts/crawl.sh --check-only first."
