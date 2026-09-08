"""One command-line entry point for collection, search, export, and local UI."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .collector import AccessStopped, CollectionConfig, DEFAULT_CATEGORIES, crawl
from .exporter import character_export, html_document, markdown, plain
from .presentation import DEFAULT_RAW_DIR, chrome_pdf, matching_character_groups
from .store import Store

app = typer.Typer(no_args_is_help=True, help="原神文本收藏：本地采集、检索、导出与浏览。")
console = Console()


@app.command()
def collect(
    categories: str = typer.Option(",".join(DEFAULT_CATEGORIES), help="逗号分隔的 API 分类"),
    db: Path = typer.Option(Path("data/genshin.sqlite3"), help="SQLite 数据库路径"),
    raw_dir: Path = typer.Option(Path("data/raw"), help="原始 JSON 缓存目录"),
    delay: float = typer.Option(2.5, min=2.0, help="最小请求间隔（秒）"),
    limit: int | None = typer.Option(None, min=1, help="每个分类的最大条数，用于试抓"),
    check_only: bool = typer.Option(False, help="仅验证 robots.txt"),
    refresh_linked: bool = typer.Option(False, help="使用已有主 JSON 补抓角色、武器和圣遗物关联故事"),
) -> None:
    """采集简体中文数据；403/429/验证码会立即停止。"""
    try:
        crawl(
            [value.strip() for value in categories.split(",") if value.strip()],
            config=CollectionConfig(db_path=db, raw_dir=raw_dir, delay_seconds=delay),
            limit=limit,
            check_only=check_only,
            refresh_linked=refresh_linked,
            console=console,
        )
    except AccessStopped as exc:
        console.print(f"[red]已停止，未重试或绕过访问限制：{exc}[/red]")
        raise typer.Exit(3)


@app.command()
def search(
    query: str = typer.Argument(..., help="标题或正文中的中文子串"),
    category: str = typer.Option("", help="精确分类筛选"),
    db: Path = typer.Option(Path("data/genshin.sqlite3")),
    limit: int = typer.Option(30, min=1, max=500),
) -> None:
    """检索本地 SQLite 文本库。"""
    store = Store(db)
    try:
        rows = store.search(query, category, limit)
    finally:
        store.close()
    table = Table(title=f"{len(rows)} 条结果")
    table.add_column("分类", style="cyan")
    table.add_column("标题", style="bold")
    table.add_column("摘要")
    for row in rows:
        table.add_row(row["category"], row["title"], " ".join(row["content"].split())[:140])
    console.print(table)


@app.command("export")
def export_collection(
    output: Path = typer.Option(..., "--output", "-o", help="输出文件"),
    format: str = typer.Option("html", help="html、pdf、markdown 或 text"),
    query: str = typer.Option("", help="可选关键词筛选"),
    category: str = typer.Option("", help="可选分类筛选"),
    db: Path = typer.Option(Path("data/genshin.sqlite3")),
    raw_dir: Path = typer.Option(DEFAULT_RAW_DIR, help="原始 JSON 缓存目录"),
) -> None:
    """将全部或筛选后的本地文本导出为适合打印或分享的文件。"""
    if format not in {"html", "pdf", "markdown", "text"}:
        raise typer.BadParameter("format 必须为 html、pdf、markdown 或 text")
    store = Store(db)
    try:
        rows = list(store.iter_documents(query, category))
        if not rows:
            raise typer.Exit("没有匹配的本地文本，未创建文件。")
        output.parent.mkdir(parents=True, exist_ok=True)
        character_mode = category == "角色/故事" or any(row["category"] == "角色/故事" for row in rows)
        exported_count: int | None = None
        if character_mode:
            if format == "markdown":
                rendered = markdown(rows)
            elif format == "text":
                rendered = plain(rows)
            else:
                rendered = character_export(store, rows, raw_dir, query)
                exported_count = len(matching_character_groups(store, raw_dir, query))
        else:
            formatters = {"html": html_document, "pdf": html_document, "markdown": markdown, "text": plain}
            rendered = formatters[format](rows, raw_dir)
        if format == "pdf":
            chrome_pdf(rendered, output)
        else:
            output.write_text(rendered, encoding="utf-8")
    finally:
        store.close()
    if exported_count is not None:
        console.print(f"[green]已导出 {exported_count} 位角色至 {output}[/green]")
    else:
        console.print(f"[green]已导出 {len(rows)} 条文本至 {output}[/green]")


@app.command()
def serve(
    db: Path = typer.Option(Path("data/genshin.sqlite3")),
    port: int = typer.Option(8765, min=1024, max=65535),
    raw_dir: Path = typer.Option(DEFAULT_RAW_DIR, help="原始 JSON 缓存目录"),
) -> None:
    """在 127.0.0.1 启动本地检索页面。"""
    console.print(f"[green]打开 http://127.0.0.1:{port}[/green]")
    from .web import serve as run_server

    run_server(db, raw_dir, port)


if __name__ == "__main__":
    app()
