from __future__ import annotations

import argparse
import html
from pathlib import Path

from .presentation import (
    DEFAULT_RAW_DIR,
    chrome_pdf,
    collection_body,
    document_inner_html,
    html_export_page,
    matching_character_groups,
    quest_metadata_for_row,
)
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


def html_document(rows, raw_dir: Path = DEFAULT_RAW_DIR) -> str:
    """HTML/PDF source for arbitrary documents.

    For the CLI, character rows are better grouped with :func:`character_export`.
    This formatter intentionally uses the same visual language for single and
    generic documents.
    """
    articles = []
    for row in rows:
        if row["category"] == "任务":
            meta = quest_metadata_for_row(row, raw_dir)
            title = meta.get("display_label") or row["title"]
            category = meta.get("type_label") or row["category"]
        else:
            title = row["title"]
            category = row["category"]
        articles.append(
            '<section class="article-card"><p class="category">'
            f'{html.escape(category)}</p><h2>{html.escape(title)}</h2>'
            + document_inner_html(row, raw_dir)
            + f'<p class="source">来源：<a href="{html.escape(row["source_url"], quote=True)}">'
            + html.escape(row["source_url"])
            + "</a></p></section>"
        )
    body = '<p class="category">检索导出</p><h1>原神文本收藏</h1><div class="ornament">◆</div>'
    body += "\n".join(articles)
    return html_export_page("原神文本收藏", body)


def character_export(store: Store, rows, raw_dir: Path = DEFAULT_RAW_DIR, query: str = "") -> str:
    """Group avatar rows into one page per character."""
    body = '<p class="category">检索导出</p><h1>原神文本收藏</h1><div class="ornament">◆</div>'
    body += collection_body(store, rows, raw_dir, query)
    # collection_body repeats its own title; keep the standalone export title only.
    body = body.replace(
        '<p class="category">检索导出</p><h1>原神文本收藏</h1><div class="ornament">◆</div>',
        '<p class="category">角色文本</p><h1>角色资料</h1><div class="ornament">◆</div>',
        1,
    )
    return html_export_page("角色资料", body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the local Genshin text collection.")
    parser.add_argument("--db", type=Path, default=Path("data/genshin.sqlite3"))
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--query", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--format", choices=("markdown", "text", "html", "pdf"), default="html")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    store = Store(args.db)
    try:
        rows = list(store.iter_documents(args.query, args.category))
        if not rows:
            print("No documents matched; no file written.")
            return 2

        if args.category == "角色/故事" or any(row["category"] == "角色/故事" for row in rows):
            rendered = character_export(store, rows, args.raw_dir, args.query)
            character_count = len(matching_character_groups(store, args.raw_dir, args.query))
            if args.format == "markdown":
                rendered = markdown(rows)
            elif args.format == "text":
                rendered = plain(rows)
            elif args.format == "pdf":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                chrome_pdf(rendered, args.output)
                print(f"Exported {character_count} characters to {args.output}")
                return 0
        else:
            rendered = {"markdown": markdown, "text": plain, "html": html_document, "pdf": html_document}[
                args.format
            ](rows, args.raw_dir)
            if args.format == "pdf":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                chrome_pdf(rendered, args.output)
                print(f"Exported {len(rows)} documents to {args.output}")
                return 0

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        if args.category == "角色/故事" or any(row["category"] == "角色/故事" for row in rows):
            print(f"Exported {character_count} characters to {args.output}")
        else:
            print(f"Exported {len(rows)} documents to {args.output}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
