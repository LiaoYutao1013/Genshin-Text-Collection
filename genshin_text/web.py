"""Local Flask interface for browsing, searching, and printing the collection."""

from __future__ import annotations

import html
import io
import os
from pathlib import Path

from flask import Flask, Response, abort, render_template, request, send_file, url_for

from .presentation import (
    BASE_CSS,
    DEFAULT_RAW_DIR,
    NAV_ITEMS,
    character_groups,
    character_inner_html,
    character_profile,
    collection_body,
    document_inner_html,
    html_export_page,
    html_to_pdf_bytes,
    matching_character_groups,
)
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/genshin.sqlite3"


def create_app(db_path: str | Path | None = None, raw_dir: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(ROOT / "templates"))
    app.config["DB_PATH"] = Path(db_path or os.environ.get("GENSHIN_TEXT_DB", DEFAULT_DB))
    app.config["RAW_DIR"] = Path(raw_dir or os.environ.get("GENSHIN_TEXT_RAW", DEFAULT_RAW_DIR))

    def database() -> Store:
        return Store(app.config["DB_PATH"])

    def raw_directory() -> Path:
        return app.config["RAW_DIR"]

    def common(**kwargs) -> dict:
        values = {
            "base_css": BASE_CSS,
            "nav_items": NAV_ITEMS,
            "active_nav": "",
        }
        values.update(kwargs)
        return values

    def character_matches(groups: list[dict], query: str) -> list[dict]:
        if not query:
            return groups
        query = query.strip()
        title_first = [item for item in groups if query in item["title"]]
        other = [item for item in groups if query not in item["title"]]
        return title_first + other

    def pdf_response(html_text: str, filename: str) -> Response:
        try:
            data = html_to_pdf_bytes(html_text)
        except RuntimeError as exc:
            abort(500, description=f"无法调用 Chrome 生成 PDF：{exc}")
        return send_file(
            io.BytesIO(data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )

    def preview_rows(rows) -> list[dict]:
        result = []
        for row in rows:
            text = " ".join(row["content"].split())
            result.append({
                "source_key": row["source_key"],
                "category": row["category"],
                "title": row["title"],
                "source_url": row["source_url"],
                "payload_path": row["payload_path"],
                "preview": text[:180] + ("…" if len(text) > 180 else ""),
            })
        return result

    @app.get("/")
    def index() -> str:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        store = database()
        try:
            categories = store.categories()
            character_results: list[dict] = []
            rows: list = []

            if category == "角色/故事":
                character_results = matching_character_groups(store, raw_directory(), query)
            elif query or category:
                found = store.search(query, category, 200)
                avatar_rows = [row for row in found if row["category"] == "角色/故事"]
                rows = preview_rows([row for row in found if row["category"] != "角色/故事"])
                if avatar_rows:
                    character_results = matching_character_groups(store, raw_directory(), query)
        finally:
            store.close()

        character_pdf_href = "/characters.pdf"
        if query:
            character_pdf_href += f"?q={query}"
        return render_template(
            "index.html",
            **common(),
            query=query,
            category=category,
            categories=categories,
            rows=rows,
            character_groups=character_results,
            character_pdf_href=character_pdf_href,
        )

    @app.get("/characters")
    def characters() -> str:
        query = request.args.get("q", "").strip()
        store = database()
        try:
            groups = character_matches(character_groups(store, raw_directory()), query)
        finally:
            store.close()
        return render_template(
            "characters.html",
            **common(active_nav="characters"),
            query=query,
            groups=groups,
        )

    @app.get("/characters.pdf")
    def characters_pdf() -> Response:
        query = request.args.get("q", "").strip()
        store = database()
        try:
            groups = character_matches(character_groups(store, raw_directory()), query)
            cards = []
            for item in groups:
                subtitle = f"元素：{item['element']}" if item.get("element") else ""
                if item.get("variant_count", 1) > 1:
                    subtitle = f"{subtitle}；{item['variant_count']} 个旅行者属性档案" if subtitle else f"{item['variant_count']} 个旅行者属性档案"
                cards.append(
                    f'<a class="card" href="/characters/{html.escape(item["key"], quote=True)}">'
                    f'<p class="category">角色</p><h2>{html.escape(item["title"])}</h2>'
                    f'<p class="preview">{html.escape(subtitle)}</p></a>'
                )
        finally:
            store.close()
        body = f'<p class="category">角色文本</p><h1>角色列表</h1><div class="ornament">◆</div>'
        body += '<section class="result-grid">' + "".join(cards) + "</section>"
        return pdf_response(html_export_page("角色列表", body, "characters"), "genshin-characters.pdf")

    @app.get("/characters/<path:key>")
    def character(key: str) -> str:
        store = database()
        try:
            profile = character_profile(store, key, raw_directory())
        finally:
            store.close()
        if profile is None:
            abort(404)
        body_html = character_inner_html(profile)
        return render_template(
            "character.html",
            **common(active_nav="characters"),
            profile=profile,
            body_html=body_html,
            pdf_href=url_for("character_pdf", key=profile["key"]),
        )

    @app.get("/characters/<path:key>/pdf")
    def character_pdf(key: str) -> Response:
        store = database()
        try:
            profile = character_profile(store, key, raw_directory())
        finally:
            store.close()
        if profile is None:
            abort(404)
        body = (
            f'<p class="category">角色资料</p><h1>{html.escape(profile["basic"]["name"])}</h1>'
            '<div class="ornament">◆</div>'
            + character_inner_html(profile)
            + f'<p class="source">数据来源：<a href="{html.escape(profile["source_url"], quote=True)}">'
            + html.escape(profile["source_url"])
            + "</a></p>"
        )
        filename = f"genshin-{profile['basic']['name']}.pdf"
        return pdf_response(html_export_page(profile["basic"]["name"], body, "characters"), filename)

    @app.get("/document/<path:source_key>")
    def document(source_key: str) -> str:
        store = database()
        try:
            row = store.get(source_key)
            body_html = document_inner_html(row, raw_directory()) if row is not None else ""
        finally:
            store.close()
        if row is None:
            abort(404)
        return render_template(
            "document.html",
            **common(),
            row=row,
            body_html=body_html,
            back_href=request.referrer or "/",
            pdf_href=url_for("document_pdf", source_key=row["source_key"]),
        )

    @app.get("/document/<path:source_key>/pdf")
    def document_pdf(source_key: str) -> Response:
        store = database()
        try:
            row = store.get(source_key)
            body_html = document_inner_html(row, raw_directory()) if row is not None else ""
        finally:
            store.close()
        if row is None:
            abort(404)
        body = (
            f'<p class="category">{html.escape(row["category"])}</p><h1>{html.escape(row["title"])}</h1>'
            '<div class="ornament">◆</div>'
            + body_html
            + f'<p class="source">来源：<a href="{html.escape(row["source_url"], quote=True)}">'
            + html.escape(row["source_url"])
            + "</a></p>"
        )
        return pdf_response(html_export_page(row["title"], body), f"genshin-{row['title']}.pdf")

    @app.get("/export.html")
    def export_html() -> Response:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        store = database()
        try:
            body = collection_body(store, store.iter_documents(query, category), raw_directory(), query)
        finally:
            store.close()
        return Response(html_export_page("检索导出", body), content_type="text/html; charset=utf-8")

    @app.get("/export.pdf")
    def export_pdf() -> Response:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        store = database()
        try:
            body = collection_body(store, store.iter_documents(query, category), raw_directory(), query)
        finally:
            store.close()
        return pdf_response(html_export_page("检索导出", body), "genshin-export.pdf")

    return app


def serve(db_path: str | Path = DEFAULT_DB, raw_dir: str | Path | None = None, port: int = 8765) -> None:
    create_app(db_path, raw_dir).run(host="127.0.0.1", port=port, debug=False)
