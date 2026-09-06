from __future__ import annotations

import argparse
import html
from pathlib import Path

from .store import Store


def markdown(rows) -> str:
    parts = ["# 原神文本收藏", ""]
    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            parts.extend([f"## {current_category}", ""])
        parts.extend([f"### {row['title']}", "", row["content"], "", f"来源：{row['source_url']}", ""])
    return "\n".join(parts)


def plain(rows) -> str:
    parts = ["原神文本收藏", "=" * 20, ""]
    for row in rows:
        parts.extend([f"[{row['category']}] {row['title']}", row["content"], f"来源：{row['source_url']}", ""])
    return "\n".join(parts)


def html_document(rows) -> str:
    articles = []
    for row in rows:
        content = html.escape(row["content"])
        content = content.replace("\n", "<br>\n")
        articles.append(
            f"<article><p class=category>{html.escape(row['category'])}</p>"
            f"<h2>{html.escape(row['title'])}</h2><div class=content>{content}</div>"
            f"<p class=source>来源：<a href={html.escape(row['source_url'], quote=True)}>{html.escape(row['source_url'])}</a></p></article>"
        )
    return """<!doctype html><html lang=zh-CN><meta charset=utf-8><title>原神文本收藏</title>
<style>body{max-width:850px;margin:2rem auto;font-family:"Noto Serif CJK SC","Source Han Serif SC",serif;line-height:1.75;color:#1f2937;padding:0 1rem}h1{border-bottom:2px solid #334155}.category{color:#64748b;font-size:.9rem;margin-bottom:0}h2{margin-top:.15rem}.content{white-space:normal}article{break-inside:avoid;border-bottom:1px solid #d1d5db;padding:1rem 0}.source{font-size:.8rem;color:#64748b}@media print{body{max-width:none;margin:0;font-size:10.5pt}a{color:inherit;text-decoration:none}article{page-break-inside:avoid}}</style>
<h1>原神文本收藏</h1>""" + "\n".join(articles) + "</html>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the local Genshin text collection.")
    parser.add_argument("--db", type=Path, default=Path("data/genshin.sqlite3"))
    parser.add_argument("--query", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--format", choices=("markdown", "text", "html"), default="html")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    store = Store(args.db)
    try:
        rows = list(store.iter_documents(args.query, args.category))
    finally:
        store.close()
    if not rows:
        print("No documents matched; no file written.")
        return 2
    rendered = {"markdown": markdown, "text": plain, "html": html_document}[args.format](rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Exported {len(rows)} documents to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
