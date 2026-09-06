from __future__ import annotations

import argparse
from pathlib import Path

from .store import Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the local Genshin text collection.")
    parser.add_argument("query")
    parser.add_argument("--db", type=Path, default=Path("data/genshin.sqlite3"))
    parser.add_argument("--category", default="")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    store = Store(args.db)
    try:
        rows = store.search(args.query, args.category, args.limit)
    finally:
        store.close()
    for row in rows:
        preview = " ".join(row["content"].split())[:160]
        print(f"[{row['category']}] {row['title']}\n  {preview}\n  {row['source_key']}\n")
    print(f"{len(rows)} result(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
