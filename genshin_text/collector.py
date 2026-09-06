"""Polite, resumable collector for Project Amber simplified-Chinese API data."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from .store import Store

BASE_URL = "https://gi.yatta.moe"
API_ROOT = f"{BASE_URL}/api/v2/chs"
DEFAULT_CATEGORIES = ("quest", "avatar", "weapon", "reliquary", "book", "achievement", "namecard", "archive")
USER_AGENT = "GenshinTextCollection/2.0 (personal offline research; respectful crawler)"
TEXT_KEYS = {
    "name", "title", "description", "story", "content", "text", "detail", "introduction",
    "dialog", "dialogue", "narration", "talk", "flavorText", "desc", "tip",
}
SKIP_KEYS = {"icon", "image", "hash", "id", "guid", "order", "rarity", "type", "version", "count"}


class AccessStopped(RuntimeError):
    """The server or its robots policy has explicitly asked this run to stop."""


@dataclass(frozen=True)
class CollectionConfig:
    db_path: Path = Path("data/genshin.sqlite3")
    raw_dir: Path = Path("data/raw")
    delay_seconds: float = 2.5
    timeout_seconds: float = 30.0
    retries: int = 3


class PoliteClient:
    """Single-request client that stops, rather than bypassing, access controls."""

    def __init__(self, delay_seconds: float, timeout_seconds: float = 30.0):
        self.delay_seconds = delay_seconds
        self.last_request = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds),
        )

    def close(self) -> None:
        self.client.close()

    def get(self, url: str) -> httpx.Response:
        remaining = self.delay_seconds - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        try:
            response = self.client.get(url)
        finally:
            self.last_request = time.monotonic()

        preview = response.text[:5000].lower()
        if response.status_code in (403, 429) or "captcha" in preview or "attention required" in preview:
            raise AccessStopped(f"server returned {response.status_code} or an access challenge: {url}")
        return response


def verify_robots(client: PoliteClient) -> bool:
    response = client.get(urljoin(BASE_URL, "/robots.txt"))
    if response.is_error:
        raise AccessStopped(f"cannot verify robots.txt: HTTP {response.status_code}")
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, f"{API_ROOT}/quest")


def get_json(client: PoliteClient, url: str, retries: int) -> Any | None:
    """Request JSON with restrained exponential retry for transient failures only."""
    for attempt in range(retries):
        try:
            response = client.get(url)
            if response.status_code == 404:
                return None
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("server failure", request=response.request, response=response)
            response.raise_for_status()
            return response.json()
        except AccessStopped:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            if attempt + 1 == retries:
                raise RuntimeError(f"request failed after {retries} attempts: {url}: {exc}") from exc
            time.sleep(3 * (2 ** attempt))
    raise AssertionError("unreachable")


def unwrap(value: Any) -> Any:
    return value["data"] if isinstance(value, dict) and "data" in value else value


def item_ids(payload: Any) -> list[str]:
    payload = unwrap(payload)
    if isinstance(payload, dict):
        for key in ("items", "list", "entries", "data"):
            child = payload.get(key)
            if isinstance(child, (list, dict)):
                return item_ids(child)
        return [str(key) for key, value in payload.items() if isinstance(value, dict) or str(key).isdigit()]
    if isinstance(payload, list):
        ids: list[str] = []
        for value in payload:
            if isinstance(value, dict):
                identifier = value.get("id", value.get("_id", value.get("guid")))
                if identifier is not None:
                    ids.append(str(identifier))
            elif isinstance(value, (str, int)):
                ids.append(str(value))
        return ids
    return []


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\\n", "\n").replace("{NL}", "\n")
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def human_key(key: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r" \1", key).replace("_", " ").strip()


def extract_sections(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SKIP_KEYS or key.lower() in SKIP_KEYS:
                continue
            if isinstance(child, str) and key in TEXT_KEYS:
                text = clean_text(child)
                if text:
                    sections.append((" / ".join(map(human_key, path + (key,))), text))
            elif isinstance(child, (dict, list)):
                sections.extend(extract_sections(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value, 1):
            sections.extend(extract_sections(child, path + (str(index),)))
    return sections


def title_from(payload: Any, fallback: str) -> str:
    item = unwrap(payload)
    if isinstance(item, dict):
        for key in ("name", "title"):
            if isinstance(item.get(key), str) and item[key].strip():
                return clean_text(item[key])
    return fallback


def classify(category: str, payload: Any) -> str:
    labels = {
        "avatar": "角色/故事", "weapon": "武器/故事", "reliquary": "圣遗物",
        "book": "图鉴/书籍", "achievement": "图鉴/成就", "namecard": "图鉴/名片", "archive": "图鉴",
    }
    item = unwrap(payload)
    if category != "quest" or not isinstance(item, dict):
        return labels.get(category, category)
    for key in ("chapter", "questType", "type", "category"):
        value = item.get(key)
        if isinstance(value, str):
            for marker, label in {
                "archon": "任务/魔神任务", "story": "任务/传说任务",
                "event": "任务/活动任务", "world": "任务/世界任务",
            }.items():
                if marker in value.lower():
                    return label
    return "任务"


def render_content(payload: Any) -> str:
    seen: set[tuple[str, str]] = set()
    blocks: list[str] = []
    for heading, body in extract_sections(unwrap(payload)):
        if (heading, body) not in seen:
            seen.add((heading, body))
            blocks.append(f"## {heading}\n\n{body}")
    return "\n\n".join(blocks)


def write_raw(raw_dir: Path, category: str, item_id: str, payload: Any) -> Path:
    target = raw_dir / category / f"{item_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def crawl(
    categories: Iterable[str] = DEFAULT_CATEGORIES,
    *, config: CollectionConfig = CollectionConfig(),
    limit: int | None = None,
    check_only: bool = False,
    console: Console | None = None,
) -> None:
    """Collect categories into SQLite; safe to rerun after interruption."""
    if config.delay_seconds < 2:
        raise ValueError("delay_seconds must be at least 2")
    console = console or Console()
    client = PoliteClient(config.delay_seconds, config.timeout_seconds)
    try:
        if not verify_robots(client):
            raise AccessStopped("robots.txt does not allow the configured API path")
        console.print("[green]robots.txt allows the configured API path.[/green]")
        if check_only:
            return

        store = Store(config.db_path)
        try:
            for category in categories:
                list_url = f"{API_ROOT}/{category}"
                console.print(f"[bold]Loading {category} index[/bold]")
                listing = get_json(client, list_url, config.retries)
                if listing is None:
                    console.print(f"[yellow]Skipping unavailable category: {category}[/yellow]")
                    continue
                ids = item_ids(listing)
                if limit is not None:
                    ids = ids[:limit]
                if not ids:
                    console.print(f"[yellow]No item IDs in {category} index.[/yellow]")
                    continue

                with Progress(
                    TextColumn("{task.description}"), BarColumn(), "{task.completed}/{task.total}", TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(category, total=len(ids))
                    for item_id in ids:
                        source_key = f"{category}:{item_id}"
                        if store.state(source_key) == "done":
                            progress.advance(task)
                            continue
                        item_url = f"{list_url}/{item_id}"
                        try:
                            payload = get_json(client, item_url, config.retries)
                            if payload is None:
                                store.mark_failure(source_key, "404")
                            else:
                                content = render_content(payload)
                                if not content:
                                    store.mark_failure(source_key, "No textual fields found")
                                else:
                                    raw_path = write_raw(config.raw_dir, category, item_id, payload)
                                    store.upsert(source_key, classify(category, payload), title_from(payload, f"{category} {item_id}"), content, item_url, str(raw_path))
                        except AccessStopped:
                            raise
                        except Exception as exc:  # Item failures remain resumable.
                            store.mark_failure(source_key, str(exc))
                            console.print(f"[yellow]Failed {source_key}: {exc}[/yellow]")
                        finally:
                            progress.advance(task)
        finally:
            store.close()
    finally:
        client.close()
