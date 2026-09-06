"""Local-only Flask interface for the offline collection."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, Response, abort, render_template, request

from .exporter import html_document
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/genshin.sqlite3"


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(ROOT / "templates"))
    app.config["DB_PATH"] = Path(db_path or os.environ.get("GENSHIN_TEXT_DB", DEFAULT_DB))

    def database() -> Store:
        return Store(app.config["DB_PATH"])

    @app.get("/")
    def index() -> str:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "")
        store = database()
        try:
            categories = store.categories()
            rows = store.search(query, category, 100) if query or category else []
        finally:
            store.close()
        return render_template("index.html", query=query, category=category, categories=categories, rows=rows)

    @app.get("/document/<path:source_key>")
    def document(source_key: str) -> str:
        store = database()
        try:
            row = store.get(source_key)
        finally:
            store.close()
        if row is None:
            abort(404)
        return render_template("document.html", row=row)

    @app.get("/export.html")
    def export_html() -> Response:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "")
        store = database()
        try:
            body = html_document(list(store.iter_documents(query, category)))
        finally:
            store.close()
        return Response(body, content_type="text/html; charset=utf-8")

    return app


def serve(db_path: str | Path = DEFAULT_DB, port: int = 8765) -> None:
    create_app(db_path).run(host="127.0.0.1", port=port, debug=False)
