"""HTML/PDF presentation helpers shared by the local web UI and CLI exporter.

The database rows are intentionally kept as raw text so the crawler stays
simple.  This module turns those rows (and, where available, the cached API
payloads) into structured, print-friendly HTML in a style inspired by the
MiYouShe observatory / in-game story review.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = ROOT / "data" / "raw"


NAV_ITEMS = (
    {"label": "首页", "href": "/", "key": "home"},
    {"label": "角色", "href": "/characters", "key": "characters"},
    {"label": "任务", "href": "/quests", "key": "quest"},
    {"label": "素材", "href": "/materials", "key": "materials"},
    {"label": "武器", "href": "/?category=%E6%AD%A6%E5%99%A8%2F%E6%95%85%E4%BA%8B", "key": "weapon"},
    {"label": "圣遗物", "href": "/?category=%E5%9C%A3%E9%81%97%E7%89%A9", "key": "reliquary"},
    {"label": "书籍", "href": "/?category=%E5%9B%BE%E9%89%B4%2F%E4%B9%A6%E7%B1%8D", "key": "book"},
    {"label": "名片", "href": "/?category=%E5%9B%BE%E9%89%B4%2F%E5%90%8D%E7%89%87", "key": "namecard"},
)


ELEMENT_LABELS = {
    "Water": "水",
    "Fire": "火",
    "Electric": "雷",
    "Ice": "冰",
    "Wind": "风",
    "Rock": "岩",
    "Grass": "草",
    "None": "无",
}
WEAPON_LABELS = {
    "WEAPON_SWORD_ONE_HAND": "单手剑",
    "WEAPON_CLAYMORE": "双手剑",
    "WEAPON_POLE": "长柄武器",
    "WEAPON_CATALYST": "法器",
    "WEAPON_BOW": "弓",
}
REGION_LABELS = {
    "MONDSTADT": "蒙德",
    "LIYUE": "璃月",
    "INAZUMA": "稻妻",
    "SUMERU": "须弥",
    "FONTAINE": "枫丹",
    "NATLAN": "纳塔",
    "SNEZHNAYA": "至冬",
    "KHAENRIAH": "坎瑞亚",
    "MAINACTOR": "旅行者",
    "FATUI": "至冬",
    "NODKRAI": "挪德卡莱",
    "OMNI_SCOURGE": "深渊",
}

QUEST_TYPE_LABELS = {
    "aq": "魔神任务",
    "lq": "传说任务",
    "eq": "活动任务",
    "wq": "世界任务",
    "iq": "其他任务",
    None: "未分类任务",
}
QUEST_TYPE_ORDER = ["aq", "lq", "eq", "wq", "iq", None]
REGION_ORDER = ["蒙德", "璃月", "稻妻", "须弥", "枫丹", "纳塔", "至冬", "坎瑞亚", "间章", "旅人", "挪德卡莱", "深渊", "未分类地区"]
REGION_KEYWORDS = {
    "蒙德": ["蒙德", "西风骑士团", "龙脊雪山", "风花节", "清泉镇", "晨曦酒庄", "奔狼领", "风龙废墟", "蒲公英海", "雪山"],
    "璃月": ["璃月", "千岩军", "往生堂", "不卜庐", "群玉阁", "层岩巨渊", "海灯节", "荻花洲", "绝云间", "归离原", "璃月港"],
    "稻妻": ["稻妻", "雷电将军", "社奉行", "天领奉行", "勘定奉行", "海祇岛", "珊瑚宫", "荒泷派", "八重堂", "鸣神大社", "鹤观", "清籁岛"],
    "须弥": ["须弥", "教令院", "镀金旅团", "兰那罗", "雨林", "沙漠", "喀万驿", "阿如村", "须弥城", "桓那兰那"],
    "枫丹": ["枫丹", "沫芒宫", "欧庇克莱歌剧院", "梅洛彼得堡", "海露港", "蒸汽鸟报", "白淞镇", "枫丹廷", "厄里那斯"],
    "纳塔": ["纳塔", "流泉之众", "花羽会", "回声之子", "悬木人", "烟谜主", "沃陆之邦", "圣火竞技场", "图兰大火山", "夜神之国"],
    "至冬": ["至冬", "愚人众", "执行官", "冰之女皇", "至冬堡", "挪德卡莱"],
    "坎瑞亚": ["坎瑞亚", "深渊教团", "深渊使徒", "黑蛇骑士"],
    "深渊": ["深渊"],
}
QUERY_ALIASES = {
    "炽热": "炽烈",
    "炽热的还魂诗": "炽烈的还魂诗",
}
RELIQUARY_SLOT_ORDER = (
    ("EQUIP_BRACER", "生之花"),
    ("EQUIP_NECKLACE", "死之羽"),
    ("EQUIP_SHOES", "时之沙"),
    ("EQUIP_RING", "空之杯"),
    ("EQUIP_DRESS", "理之冠"),
)
MATERIAL_GROUP_ORDER = {"weekly": 0, "talent": 1, "weapon": 2, "normal-boss": 3, "other": 4}


BASE_CSS = r"""
:root{
  --paper:#f7f3ea;
  --paper-deep:#efe7d8;
  --card:#fffdf8;
  --ink:#38342e;
  --muted:#7b7267;
  --line:#ddd2bf;
  --gold:#a8874b;
  --gold-soft:#c9ac72;
  --nav:#272831;
  --nav-ink:#f3ead6;
  --water:#3e6f86;
  --accent:#8b5e3c;
}
*{box-sizing:border-box}
html{background:var(--paper)}
body{
  margin:0;
  color:var(--ink);
  background:
    radial-gradient(circle at 15% 0%,rgba(201,172,114,.12),transparent 32rem),
    radial-gradient(circle at 90% 4%,rgba(62,111,134,.08),transparent 28rem),
    var(--paper);
  font:15.5px/1.62 "Latin Modern Roman","Noto Serif CJK SC","Source Han Serif SC","Songti SC",serif;
  letter-spacing:.005em;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.topnav{
  position:sticky;top:0;z-index:20;
  display:flex;align-items:center;gap:4px;overflow-x:auto;
  padding:0 14px;background:linear-gradient(90deg,#20222b,#2b2832);
  border-bottom:1px solid rgba(201,172,114,.35);
  box-shadow:0 4px 18px rgba(40,32,24,.14);
}
.topnav .brand{
  color:var(--nav-ink);font-weight:700;font-size:15px;white-space:nowrap;
  padding:9px 10px 9px 0;letter-spacing:.06em;
}
.topnav a{
  color:#d8ceb8;white-space:nowrap;padding:9px 9px;font-size:13.5px;
  border-bottom:2px solid transparent;
}
.topnav a:hover{color:#fff;text-decoration:none;background:rgba(255,255,255,.04)}
.topnav a.active{color:#fff;border-bottom-color:var(--gold-soft)}
.shell{max-width:1180px;margin:0 auto;padding:22px 18px 46px}
.hero{
  position:relative;padding:24px 22px 20px;margin:10px 0 16px;
  background:linear-gradient(180deg,rgba(255,253,248,.98),rgba(255,253,248,.88));
  border:1px solid var(--line);border-radius:4px;
  box-shadow:0 10px 30px rgba(61,47,29,.08);
}
.hero:before,.hero:after,.card:before,.card:after{
  content:"";position:absolute;width:18px;height:18px;pointer-events:none;
  border-color:var(--gold);opacity:.75;
}
.hero:before,.card:before{left:7px;top:7px;border-left:1px solid;border-top:1px solid}
.hero:after,.card:after{right:7px;bottom:7px;border-right:1px solid;border-bottom:1px solid}
h1,h2,h3,h4{font-family:"Noto Serif CJK SC","Source Han Serif SC","Songti SC",serif;color:#2f2b26}
h1{
  margin:0 0 5px;font-size:clamp(25px,4.4vw,36px);font-weight:700;line-height:1.16;
  letter-spacing:.04em;text-align:center;
}
.subtitle{margin:0;text-align:center;color:var(--muted);font-size:13px}
.ornament{
  display:flex;align-items:center;justify-content:center;gap:7px;margin:8px auto 0;
  color:var(--gold);font-size:16px;
}
.ornament:before,.ornament:after{content:"";height:1px;width:46px;background:linear-gradient(90deg,transparent,var(--gold))}
.ornament:after{background:linear-gradient(90deg,var(--gold),transparent)}
.searchbar{display:grid;grid-template-columns:minmax(0,1fr) 180px auto;gap:8px;margin-top:12px}
input,select,button{font:inherit;border:1px solid #c8bcab;border-radius:3px;padding:8px 10px;background:#fff;color:var(--ink)}
input:focus,select:focus{outline:2px solid rgba(168,135,75,.28);border-color:var(--gold)}
button,.button{
  display:inline-flex;align-items:center;justify-content:center;cursor:pointer;
  background:linear-gradient(180deg,#b28d51,#8f6c3b);color:#fff;border-color:#8f6c3b;
  padding:8px 15px;font-weight:700;letter-spacing:.04em;
}
button:hover,.button:hover{background:linear-gradient(180deg,#c3a15f,#9a7643);text-decoration:none}
.button.ghost{background:#fff;color:var(--accent);border-color:var(--gold-soft)}
.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:10px}
.card{
  position:relative;display:block;padding:13px 14px 11px;background:var(--card);
  border:1px solid var(--line);border-radius:4px;color:inherit;
  box-shadow:0 5px 18px rgba(61,47,29,.07);transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
}
a.card:hover{transform:translateY(-2px);border-color:var(--gold-soft);text-decoration:none;box-shadow:0 10px 26px rgba(61,47,29,.12)}
.card .category{font-size:11.5px;color:var(--gold);letter-spacing:.06em;margin:0 0 3px}
.card h2,.card h3{margin:.1rem 0 .3rem;font-size:18px;line-height:1.28}
.card .preview{color:#5b5348;font-size:13px;line-height:1.55;margin:0}
.empty{padding:28px 16px;text-align:center;color:var(--muted);border:1px dashed var(--line);background:rgba(255,253,248,.6)}
.article-card{
  position:relative;margin:0 0 14px;padding:20px 22px 18px;background:var(--card);
  border:1px solid var(--line);border-radius:4px;box-shadow:0 6px 22px rgba(61,47,29,.07);
  page-break-inside:avoid;break-inside:avoid;
}
.article-card>.category{font-size:11.5px;color:var(--gold);letter-spacing:.1em;text-transform:uppercase;margin:0 0 3px}
.article-card h1,.article-card h2{margin:.1rem 0 .4rem;font-size:26px;line-height:1.28}
.source{margin-top:12px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;word-break:break-all}
.source a{color:var(--water)}
.content{white-space:normal;font-size:15.5px}
.content p{margin:0 0 .7em;text-align:justify}
.content h3,.content h4{margin:1.05em 0 .38em;color:var(--accent);font-size:18.5px}
.content h4{font-size:16.5px}
.story-step{margin:0 0 12px;padding-left:11px;border-left:2px solid var(--paper-deep)}
.story-step h4{margin-top:0}
.dialogue{margin:0 0 7px;padding:7px 11px 7px 12px;background:#fbf7ef;border-left:3px solid var(--gold-soft);border-radius:0 3px 3px 0}
.dialogue .role{display:block;font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--gold);margin-bottom:1px}
.dialogue .text{margin:0;color:#3d3932}
.dialogue.blank{border-left-color:#b9c8cf;background:#f5f8f9}
.dialogue.blank .role{color:var(--water)}
.quote-list{display:grid;gap:0;margin-top:8px}
.quote-item{padding:9px 0;border-bottom:1px solid var(--line)}
.quote-item:last-child{border-bottom:0}
.quote-item .role{font-weight:700;color:var(--accent)}
.quote-item .tips{display:block;margin-top:3px;color:var(--muted);font-size:11.5px}
.info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px 14px;margin-top:10px}
.info-grid div{border-bottom:1px dashed var(--line);padding-bottom:5px}
.info-grid .label{display:block;font-size:11.5px;color:var(--gold);letter-spacing:.06em}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px}
.tabs a{padding:6px 10px;border:1px solid var(--line);background:#fffdf8;color:var(--accent)}
.tabs a.active{background:var(--nav);color:var(--nav-ink);border-color:var(--nav)}
.quest-group{margin:18px 0 6px}
.quest-group h2{margin:0;font-size:20px;letter-spacing:.03em}
.quest-group .count{color:var(--muted);font-size:12px;margin-left:6px;font-weight:400}
.quest-group .rule{height:1px;margin:5px 0 8px;background:linear-gradient(90deg,var(--gold),transparent)}
@media (max-width:760px){
  .searchbar{grid-template-columns:1fr}
  .hero{padding:24px 16px}
  .article-card{padding:20px 16px}
}
@media print{
  @page{size:A4;margin:9mm 11mm}
  :root{--paper:#fff;--paper-deep:#f2ede4;--card:#fff}
  body{background:#fff;font-size:9.4pt;line-height:1.34}
  .topnav,.toolbar,.tabs,.no-print{display:none!important}
  .shell{max-width:none;padding:0}
  .hero,.card,.article-card{box-shadow:none;border-color:#d8cfbe;background:#fff}
  .hero{padding:12px 12px 10px;margin:0 0 8px}
  .article-card{margin:0 0 6px;padding:9px 10px 8px}
  .card{padding:8px 9px 7px;box-shadow:none}
  .result-grid{gap:6px}
  .card h2,.card h3,.article-card h1,.article-card h2{font-size:14pt;line-height:1.22;margin:.08rem 0 .22rem}
  .card .category,.article-card>.category{font-size:8.5pt}
  .card .preview{font-size:8.6pt;line-height:1.32}
  .content{font-size:9.4pt}
  .content p{margin:0 0 .38em}
  .content h3,.content h4{margin:.65em 0 .22em;font-size:12pt}
  .content h4{font-size:11pt}
  .story-step{margin:0 0 6px;padding-left:8px}
  .dialogue{margin:0 0 3px;padding:4px 7px 4px 8px}
  .dialogue .role{font-size:8.5pt}
  .quote-item{padding:4px 0}
  .quote-item .tips{font-size:8.5pt;margin-top:1px}
  .info-grid{gap:3px 8px;margin-top:5px}
  .info-grid div{padding-bottom:2px}
  .info-grid .label{font-size:8.5pt}
  .source{margin-top:5px;padding-top:4px;font-size:8.5pt}
  .quest-group{margin:8px 0 3px}
  .quest-group h2{font-size:12.5pt}
  .quest-group .rule{margin:3px 0 5px}
  .ornament{margin-top:4px;gap:5px}
  .ornament:before,.ornament:after{width:30px}
  a{color:inherit;text-decoration:none}
  .source a{word-break:break-all}
  .dialogue,.quote-item,.article-card,.story-step{page-break-inside:avoid;break-inside:avoid}
}
"""


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\\n", "\n").replace("{NL}", "\n")
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


@lru_cache(maxsize=8)
def _character_region_map(raw_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    directory = Path(raw_dir) / "avatar"
    if not directory.is_dir():
        return mapping
    for path in directory.glob("*.json"):
        payload = load_json(path)
        item = _unwrap(payload) if payload is not None else None
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"))
        region = _label(item.get("region"), REGION_LABELS)
        if name and region:
            mapping[name] = region
    return mapping


def _infer_region_from_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    for region, keywords in REGION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in compact:
                return region
    return "未分类地区"


def _quest_region(
    info: dict[str, Any],
    raw_dir: Path | None = None,
    title_hint: str = "",
    description_hint: str = "",
) -> str:
    image_title = _clean_text(info.get("chapterImageTitle"))
    icon = _clean_text(info.get("chapterIcon"))
    chapter_num = _clean_text(info.get("chapterNum"))

    icon_upper = icon.upper()
    for key, label in REGION_LABELS.items():
        if key in icon_upper:
            return label

    if image_title in REGION_LABELS.values():
        return image_title
    special_regions = {
        "FATUI": "至冬",
        "NODKRAI": "挪德卡莱",
        "OMNI_SCOURGE": "深渊",
    }
    if image_title.upper() in special_regions:
        return special_regions[image_title.upper()]
    if raw_dir is not None and image_title:
        character_region = _character_region_map(raw_dir).get(image_title)
        if character_region:
            return character_region
    if image_title:
        return image_title

    if chapter_num.startswith("序章"):
        return "蒙德"
    if chapter_num.startswith("第一章"):
        return "璃月"
    if chapter_num.startswith("第二章"):
        return "稻妻"
    if chapter_num.startswith("第三章"):
        return "须弥"
    if chapter_num.startswith("第四章"):
        return "枫丹"
    if chapter_num.startswith("第五章"):
        return "纳塔"
    if chapter_num.startswith("第六章") or chapter_num.startswith("第七章"):
        return "至冬"
    if chapter_num.startswith("间章"):
        return "间章"
    text_region = _infer_region_from_text(" ".join([title_hint, description_hint]))
    if text_region != "未分类地区":
        return text_region
    return "未分类地区"


def _quest_chapter_order(chapter_num: str) -> tuple[int, int]:
    match = re.match(r"^第?([一二三四五六七八九十百\d]+)章\s*第?([一二三四五六七八九十百\d]+)幕", chapter_num)
    if match:
        return (_chinese_number(match.group(1)), _chinese_number(match.group(2)))
    match = re.match(r"^第?([一二三四五六七八九十百\d]+)章", chapter_num)
    if match:
        return (_chinese_number(match.group(1)), 0)
    return (999, 0)


def _chinese_number(value: str) -> int:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if value.isdigit():
        return int(value)
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if value.startswith("十") and len(value) == 2:
        return 10 + digits.get(value[1], 0)
    if len(value) == 2 and value.endswith("十"):
        return digits.get(value[0], 0) * 10
    return 999


def _quest_sort_key(entry: dict[str, Any]) -> tuple[int, int, int, int, str]:
    type_order = QUEST_TYPE_ORDER.index(entry["quest_type"]) if entry["quest_type"] in QUEST_TYPE_ORDER else len(QUEST_TYPE_ORDER)
    region_order = REGION_ORDER.index(entry["region"]) if entry["region"] in REGION_ORDER else len(REGION_ORDER)
    chapter_order = _quest_chapter_order(entry.get("chapter_num", ""))
    return (type_order, region_order, chapter_order[0], chapter_order[1], str(entry.get("id", "")))


@lru_cache(maxsize=8)
def load_quest_catalog(raw_dir: Path) -> tuple[dict[str, dict[str, Any]], ...]:
    """Read the cached quest payloads once and derive display metadata."""
    directory = Path(raw_dir) / "quest"
    entries: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return tuple()

    for path in sorted(directory.glob("*.json"), key=lambda p: _int_key(p.stem)):
        payload = load_json(path)
        item = _unwrap(payload) if payload is not None else None
        if not isinstance(item, dict):
            continue
        info = item.get("info") or {}
        if not isinstance(info, dict):
            info = {}
        item_id = str(info.get("id") or path.stem)
        story_list = item.get("storyList") or {}
        first_story_title = ""
        first_story_description = ""
        if isinstance(story_list, dict):
            for key, story in story_list.items():
                if not isinstance(story, dict):
                    continue
                story_info = story.get("info") or {}
                if isinstance(story_info, dict):
                    first_story_title = _clean_text(story_info.get("title"))
                    first_story_description = _clean_text(story_info.get("description"))
                if first_story_title or first_story_description:
                    break

        chapter_num = _clean_text(info.get("chapterNum"))
        chapter_title = _clean_text(info.get("chapterTitle"))
        quest_type = info.get("type")
        if quest_type not in QUEST_TYPE_LABELS:
            quest_type = None
        display_title = chapter_title or first_story_title or f"任务 {item_id}"
        act_label = chapter_num
        display_label = f"{act_label} · {display_title}" if act_label else display_title
        region = _quest_region(
            info,
            raw_dir,
            title_hint=chapter_title,
            description_hint=first_story_description,
        )
        entries[f"quest:{item_id}"] = {
            "source_key": f"quest:{item_id}",
            "id": item_id,
            "quest_type": quest_type,
            "type_label": QUEST_TYPE_LABELS[quest_type],
            "chapter_num": chapter_num,
            "chapter_title": chapter_title,
            "display_title": display_title,
            "act_label": act_label,
            "display_label": display_label,
            "region": region,
            "description": first_story_description,
            "image_title": _clean_text(info.get("chapterImageTitle")),
        }

    ordered = sorted(entries.values(), key=_quest_sort_key)
    return tuple(ordered)


@lru_cache(maxsize=8)
def quest_catalog_map(raw_dir: Path) -> dict[str, dict[str, Any]]:
    return {entry["source_key"]: entry for entry in load_quest_catalog(raw_dir)}


def quest_display_label(source_key: str, raw_dir: Path = DEFAULT_RAW_DIR) -> str | None:
    entry = quest_catalog_map(raw_dir).get(source_key)
    return entry["display_label"] if entry else None


def quest_metadata_for_row(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, Any]:
    """Merge a database quest row with its display metadata."""
    source_key = row["source_key"] if hasattr(row, "__getitem__") else getattr(row, "source_key")
    entry = quest_catalog_map(raw_dir).get(source_key)
    if entry is None:
        return {
            "source_key": source_key,
            "display_title": row["title"],
            "display_label": row["title"],
            "act_label": "",
            "region": "未分类地区",
            "type_label": "任务",
            "quest_type": "iq",
            "description": "",
        }
    return entry


def expand_query_aliases(query: str) -> list[str]:
    query = query.strip()
    if not query:
        return []
    expanded = {query}
    for source, target in QUERY_ALIASES.items():
        if source in query:
            expanded.add(query.replace(source, target))
    return list(expanded)


def matching_quest_entries(
    store: Any,
    raw_dir: Path,
    query: str = "",
    quest_type: str = "",
) -> list[dict[str, Any]]:
    """Return task metadata filtered by full-text search and task type."""
    catalog = load_quest_catalog(raw_dir)
    if quest_type:
        catalog = tuple(entry for entry in catalog if entry["quest_type"] == quest_type)

    query = query.strip()
    if not query:
        return list(catalog)

    source_keys: set[str] = set()
    for variant in expand_query_aliases(query):
        rows = store.search(variant, "任务", 10_000)
        source_keys.update(row["source_key"] for row in rows)

    # Also match the derived chapter/act labels, because the database content
    # does not currently include info.chapterNum/chapterTitle.
    matched = []
    query_variants = expand_query_aliases(query)
    compact_variants = [re.sub(r"\s+", "", variant) for variant in query_variants]
    for entry in catalog:
        haystack = " ".join(
            [
                entry["display_label"],
                entry["chapter_title"],
                entry["region"],
                entry["type_label"],
                entry["description"],
            ]
        )
        compact_haystack = re.sub(r"\s+", "", haystack)
        if entry["source_key"] in source_keys or any(
            variant in haystack or compact_variant in compact_haystack
            for variant, compact_variant in zip(query_variants, compact_variants)
        ):
            matched.append(entry)
    return matched


def _unwrap(payload: Any) -> Any:
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_payload_path(payload_path: str | None) -> Path | None:
    if not payload_path:
        return None
    path = Path(payload_path)
    if not path.is_absolute():
        path = ROOT / path
    return path


def raw_payload(row: Any, raw_dir: Path) -> dict[str, Any] | None:
    """Return the unwrapped item object for a database row."""
    payload_path = resolve_payload_path(row.get("payload_path") if hasattr(row, "get") else getattr(row, "payload_path", None))
    payload = load_json(payload_path) if payload_path else None
    if payload is not None:
        return _unwrap(payload)

    source_key = row["source_key"] if hasattr(row, "__getitem__") else getattr(row, "source_key")
    category, item_id = source_key.split(":", 1)
    payload = load_json(raw_dir / category / f"{item_id}.json")
    return _unwrap(payload) if payload is not None else None


def _linked_payload(category: str, item_id: str, raw_dir: Path) -> dict[str, Any] | None:
    payload = load_json(raw_dir / "_linked" / category / f"{item_id}.json")
    if not isinstance(payload, dict):
        return None
    sections = payload.get("sections") or []
    for section in sections:
        if isinstance(section, dict) and "数据" not in str(section.get("heading", "")):
            pass
    # The crawler stores one or more sections with `data`; the avatar feed
    # only has one section named "角色故事与语音".
    for section in sections:
        if isinstance(section, dict) and isinstance(section.get("data"), dict):
            return section["data"]
    return None


def _linked_sections(category: str, item_id: str, raw_dir: Path) -> list[dict[str, Any]]:
    payload = load_json(raw_dir / "_linked" / category / f"{item_id}.json")
    if not isinstance(payload, dict):
        return []
    return [section for section in payload.get("sections") or [] if isinstance(section, dict)]


def _material_series_name(name: str, type_label: str) -> str:
    if type_label == "角色天赋素材":
        return name.split("的", 1)[0] if "的" in name else name
    if type_label == "武器突破素材":
        return name.rsplit("的", 1)[0] if "的" in name else name
    return name


def _material_group_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    type_label = entry["type_label"]
    rank = entry.get("rank")
    dropped_by = entry.get("dropped_by")
    if type_label == "角色培养素材" and rank == 5:
        return ("weekly", f"周本素材 · {dropped_by or '未命名首领'}", dropped_by or "")
    if type_label == "武器突破素材":
        return ("weapon", f"武器突破素材 · {entry['series']}", entry["series"])
    if type_label == "角色天赋素材":
        return ("talent", f"角色天赋素材 · {entry['series']}", entry["series"])
    if type_label in {"角色培养素材", "角色突破素材"} and dropped_by:
        return ("normal-boss", f"{type_label} · {dropped_by}", dropped_by)
    return ("other", type_label, "")


@lru_cache(maxsize=8)
def load_material_catalog(raw_dir: Path) -> tuple[dict[str, Any], ...]:
    directory = Path(raw_dir) / "material"
    if not directory.is_dir():
        return tuple()

    entries: dict[int, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json"), key=lambda p: _int_key(p.stem)):
        payload = load_json(path)
        item = _unwrap(payload) if payload is not None else None
        if not isinstance(item, dict):
            continue
        item_id = item.get("id") or path.stem
        name = _clean_text(item.get("name"))
        type_label = _clean_text(item.get("type")) or "未分类素材"
        rank = item.get("rank")
        description = _clean_text(item.get("description") or item.get("descriptionCodex"))
        additions = item.get("additions") or {}
        dropped_by = ""
        if isinstance(additions, dict):
            dropped = additions.get("droppedBy") or []
            if isinstance(dropped, list) and dropped and isinstance(dropped[0], dict):
                dropped_by = _clean_text(dropped[0].get("name"))
        required_by: list[str] = []
        if isinstance(additions, dict):
            required = additions.get("requiredBy") or {}
            if isinstance(required, dict):
                for kind in ("avatar", "weapon"):
                    for target in _as_list(required.get(kind)):
                        if isinstance(target, dict):
                            target_name = _clean_text(target.get("name"))
                            if target_name:
                                required_by.append(target_name)

        source_names = []
        for source in _as_list(item.get("source")):
            if isinstance(source, dict):
                source_name = _clean_text(source.get("name"))
                if source_name:
                    source_names.append(source_name)

        series = _material_series_name(name, type_label)
        group_kind, group_title, group_subtitle = _material_group_key({
            "type_label": type_label,
            "rank": rank,
            "dropped_by": dropped_by,
            "series": series,
        })
        entries[int(item_id)] = {
            "source_key": f"material:{item_id}",
            "id": str(item_id),
            "name": name,
            "type_label": type_label,
            "rank": rank,
            "description": description,
            "series": series,
            "dropped_by": dropped_by,
            "source_names": source_names,
            "required_by": list(dict.fromkeys(required_by)),
            "group_kind": group_kind,
            "group_title": group_title,
            "group_subtitle": group_subtitle,
        }
    return tuple(sorted(
        entries.values(),
        key=lambda e: (MATERIAL_GROUP_ORDER.get(e["group_kind"], 5), e["group_title"], e["name"]),
    ))


def material_groups(catalog: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for entry in catalog:
        key = entry["group_title"]
        if key not in groups:
            groups[key] = {
                "key": key,
                "title": key,
                "kind": entry["group_kind"],
                "entries": [],
            }
        groups[key]["entries"].append(entry)
    return list(groups.values())


def _paragraphs(text: str) -> list[str]:
    text = _clean_text(text)
    return [line.strip() for line in text.split("\n") if line.strip()]


def _dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        signature = (item.get("title", ""), item.get("text", ""))
        if signature not in seen:
            seen.add(signature)
            result.append(item)
    return result


def _cv_text(cv: Any) -> str:
    if not isinstance(cv, dict):
        return ""
    labels = (("CHS", "中"), ("JP", "日"), ("EN", "英"), ("KR", "韩"))
    return "　".join(f"{label}：{cv[key]}" for key, label in labels if isinstance(cv.get(key), str) and cv[key])


def _label(value: str, mapping: dict[str, str]) -> str:
    value = _clean_text(value)
    return mapping.get(value, value)


def _birthday_text(value: Any) -> str:
    if isinstance(value, list) and len(value) >= 2:
        try:
            month, day = int(value[0]), int(value[1])
            return f"{month}月{day}日" if month > 0 and day > 0 else ""
        except (TypeError, ValueError):
            pass
    return _clean_text(value)


def character_groups(store: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT source_key, title, payload_path FROM documents WHERE category='角色/故事' ORDER BY source_key"
    ).fetchall()
    groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for row in rows:
        title = row["title"].strip()
        group = groups.get(title)
        if group is None:
            group = {
                "key": title,
                "title": title,
                "variants": [],
                "base_id": None,
                "first_source_key": row["source_key"],
                "element": "",
            }
            groups[title] = group
        source_key = row["source_key"]
        item_id = source_key.split(":", 1)[1]
        base_id = item_id.split("-", 1)[0]
        if group["base_id"] is None:
            group["base_id"] = base_id
        variant = {
            "source_key": source_key,
            "item_id": item_id,
            "base_id": base_id,
            "payload_path": row["payload_path"],
        }
        group["variants"].append(variant)
        payload = raw_payload(row, raw_dir) if row["payload_path"] else None
        if isinstance(payload, dict):
            element = _label(payload.get("element"), ELEMENT_LABELS)
            if element and not group["element"]:
                group["element"] = element
    for group in groups.values():
        group["variant_count"] = len(group["variants"])
    return list(groups.values())


def matching_character_groups(
    store: Any,
    raw_dir: Path = DEFAULT_RAW_DIR,
    query: str = "",
) -> list[dict[str, Any]]:
    """Prefer exact character-name matches; fall back to full-text matches."""
    groups = character_groups(store, raw_dir)
    query = query.strip()
    if not query:
        return groups

    title_matches = [item for item in groups if query in item["title"]]
    if title_matches:
        return title_matches

    found = store.search(query, "角色/故事", 500)
    titles = {row["title"] for row in found if row["category"] == "角色/故事"}
    return [item for item in groups if item["title"] in titles]


def character_profile(store: Any, key: str, raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, Any] | None:
    """Build the combined profile for one character (grouped by display title)."""
    groups = character_groups(store, raw_dir)
    group = next((item for item in groups if item["key"] == key or item["title"] == key), None)
    if group is None:
        return None

    basic: dict[str, str] = {
        "name": group["title"],
        "title": "",
        "detail": "",
        "constellation": "",
        "native": "",
        "birthday": "",
        "element": group.get("element", ""),
        "weaponType": "",
        "region": "",
        "cv": "",
    }
    stories: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []

    for variant in group["variants"]:
        payload = None
        payload_path = resolve_payload_path(variant.get("payload_path"))
        if payload_path:
            payload = load_json(payload_path)
            if payload is not None:
                payload = _unwrap(payload)
        if payload is None:
            payload = load_json(raw_dir / "avatar" / f"{variant['item_id']}.json")
            if payload is not None:
                payload = _unwrap(payload)

        if isinstance(payload, dict):
            fetter = payload.get("fetter") or {}
            if isinstance(fetter, dict):
                if not basic["title"]:
                    basic["title"] = _clean_text(fetter.get("title"))
                if not basic["detail"]:
                    basic["detail"] = _clean_text(fetter.get("detail"))
                if not basic["constellation"]:
                    basic["constellation"] = _clean_text(fetter.get("constellation"))
                if not basic["native"]:
                    native = _clean_text(fetter.get("native"))
                    if native not in {"——", "-", "--"}:
                        basic["native"] = native
                if not basic["cv"]:
                    basic["cv"] = _cv_text(fetter.get("cv"))
            if not basic["element"]:
                basic["element"] = _label(payload.get("element"), ELEMENT_LABELS)
            if not basic["weaponType"]:
                basic["weaponType"] = _label(payload.get("weaponType"), WEAPON_LABELS)
            if not basic["region"]:
                basic["region"] = _label(payload.get("region"), REGION_LABELS)
            if not basic["birthday"]:
                basic["birthday"] = _birthday_text(payload.get("birthday"))

        linked = _linked_payload("avatar", variant["item_id"], raw_dir)
        if isinstance(linked, dict):
            story_data = linked.get("story")
            quote_data = linked.get("quotes")
            if isinstance(story_data, dict):
                for _, item in sorted(story_data.items(), key=lambda kv: _int_key(kv[0])):
                    if not isinstance(item, dict):
                        continue
                    text = _clean_text(item.get("text"))
                    text2 = _clean_text(item.get("text2"))
                    if text2:
                        text = f"{text}\n\n{text2}" if text else text2
                    if text:
                        stories.append({
                            "title": _clean_text(item.get("title")) or "角色故事",
                            "text": text,
                            "tips": _clean_text(item.get("tips")),
                        })
            if isinstance(quote_data, dict):
                for _, item in sorted(quote_data.items(), key=lambda kv: _int_key(kv[0])):
                    if not isinstance(item, dict):
                        continue
                    text = _clean_text(item.get("text"))
                    if text:
                        quotes.append({
                            "title": _clean_text(item.get("title")) or "语音",
                            "text": text,
                            "tips": _clean_text(item.get("tips")),
                        })

    # For older caches the linked file may be absent; fall back to the already
    # collected content instead of silently showing an empty page.
    if not stories and not quotes:
        rows = store.conn.execute(
            "SELECT content FROM documents WHERE category='角色/故事' AND title=?",
            (group["title"],),
        ).fetchall()
        fallback_blocks = _generic_blocks(rows[0]["content"]) if rows else []
        if fallback_blocks:
            stories.append({"title": "角色故事与语音", "text": "\n\n".join(block[1] for block in fallback_blocks), "tips": ""})

    return {
        "key": group["key"],
        "basic": basic,
        "stories": _dedup(stories),
        "quotes": _dedup(quotes),
        "variants": group["variants"],
        "source_url": f"https://gi.yatta.moe/api/v2/chs/avatar/{group['variants'][0]['item_id']}",
    }


def _int_key(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dialogue_parts(item: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for part in _as_list(item.get("text")):
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict):
            value = part.get("text")
            if isinstance(value, str):
                texts.append(value)
    return texts


def quest_sections(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> list[dict[str, Any]]:
    """Turn a quest payload into game-review-like story sections."""
    payload = raw_payload(row, raw_dir)
    if not isinstance(payload, dict):
        return []

    info = payload.get("info") or {}
    chapter_num = _clean_text(info.get("chapterNum"))
    chapter_title = _clean_text(info.get("chapterTitle"))
    image_title = _clean_text(info.get("chapterImageTitle"))
    if chapter_num or chapter_title:
        top_title = "　".join(part for part in (chapter_num, chapter_title) if part)
    else:
        top_title = _clean_text(row["title"])

    sections: list[dict[str, Any]] = [
        {
            "title": top_title,
            "subtitle": image_title,
            "kind": "quest-intro",
            "stories": [],
        }
    ]

    story_list = payload.get("storyList") or {}
    if isinstance(story_list, dict):
        story_items = list(story_list.items())
    else:
        story_items = [(str(i), item) for i, item in enumerate(_as_list(story_list))]

    for story_key, story in story_items:
        if not isinstance(story, dict):
            continue
        story_info = story.get("info") or {}
        story_title = _clean_text(story_info.get("title")) or f"剧情 {story_key}"
        description = _clean_text(story_info.get("description"))
        steps: list[dict[str, Any]] = []
        step_data = story.get("story") or {}
        if isinstance(step_data, dict):
            step_items = list(step_data.items())
        else:
            step_items = [(str(i), step) for i, step in enumerate(_as_list(step_data))]

        for step_key, step in step_items:
            if not isinstance(step, dict):
                continue
            step_title = _clean_text(step.get("title")) or f"步骤 {step_key}"
            dialogues: list[dict[str, str]] = []
            for task in _as_list(step.get("taskData")):
                if not isinstance(task, dict):
                    continue
                items = task.get("items") or {}
                if isinstance(items, dict):
                    ordered = list(items.items())
                else:
                    ordered = [(str(i), item) for i, item in enumerate(_as_list(items))]
                for _, item in ordered:
                    if not isinstance(item, dict):
                        continue
                    role = _clean_text(item.get("role"))
                    for text in _dialogue_parts(item):
                        if text.strip():
                            dialogues.append({"role": role, "text": _clean_text(text)})
            if dialogues:
                steps.append({"title": step_title, "dialogues": dialogues})
        sections.append({
            "title": story_title,
            "subtitle": description,
            "kind": "quest-story",
            "steps": steps,
        })
    return sections


def _generic_blocks(content: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal heading, body
        text = "\n\n".join(part.strip() for part in ("\n".join(body)).split("\n\n") if part.strip())
        if heading or text:
            blocks.append((heading or "", text))
        heading = None
        body = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if line.startswith("##"):
            flush()
            heading = _clean_heading(line)
        elif line.strip():
            body.append(line.strip())
    flush()
    return blocks


def _clean_heading(line: str) -> str:
    value = re.sub(r"^#+\s*", "", line).strip()
    parts = [part.strip() for part in value.split("/") if part.strip()]
    generic = {
        "name", "description", "text", "title", "detail", "content", "info",
        "list", "items", "item", "volume", "suit", "story", "task data",
        "data", "0", "1", "2", "3", "4", "5",
    }
    kept = [part for part in parts if part.lower() not in generic]
    if not kept:
        kept = parts[-1:]
    # Turn technical snake-case labels into readable Chinese-like labels.
    readable = []
    for part in kept:
        part = part.replace("_", " ")
        part = re.sub(r"(?<!^)(?=[A-Z])", " ", part)
        readable.append(" ".join(part.split()).strip())
    return " · ".join(readable) if readable else "正文"


def generic_content_html(content: str) -> str:
    parts: list[str] = []
    for heading, body in _generic_blocks(content):
        if heading:
            parts.append(f'<h3 class="section-title">{html.escape(heading)}</h3>')
        if body:
            for paragraph in body.split("\n\n"):
                parts.append(f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>")
    return "\n".join(parts)


def _story_section_by_name(sections: list[dict[str, Any]], piece_name: str) -> dict[str, Any] | None:
    if not piece_name:
        return None
    for section in sections:
        heading = _clean_text(section.get("heading"))
        if piece_name in heading or heading.endswith(piece_name):
            return section
    return None


def weapon_inner_html(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> str:
    source_key = row["source_key"]
    item_id = source_key.split(":", 1)[1]
    item = raw_payload(row, raw_dir)
    parts: list[str] = []

    if isinstance(item, dict):
        description = _clean_text(item.get("description"))
        if description:
            parts.append(f'<p class="detail">{html.escape(description).replace(chr(10), "<br>")}</p>')

        affix = item.get("affix") or {}
        if isinstance(affix, dict):
            for _, affix_item in affix.items():
                if not isinstance(affix_item, dict):
                    continue
                affix_name = _clean_text(affix_item.get("name"))
                upgrades = affix_item.get("upgrade") or {}
                if affix_name:
                    parts.append(f'<h3 class="section-title">武器技能 · {html.escape(affix_name)}</h3>')
                if isinstance(upgrades, dict):
                    for level_key in sorted(upgrades, key=_int_key):
                        level = _int_key(level_key) + 1
                        text = _clean_text(upgrades[level_key])
                        if text:
                            parts.append(f'<section class="quote-item"><h4 class="role">精炼 {level}</h4><p>{html.escape(text).replace(chr(10), "<br>")}</p></section>')

    linked_sections = _linked_sections("weapon", item_id, raw_dir)
    if linked_sections:
        parts.append('<h3 class="section-title">武器故事</h3>')
        for section in linked_sections:
            story = section.get("data")
            if isinstance(story, str):
                story = _clean_text(story)
            else:
                story = _clean_text(json.dumps(story, ensure_ascii=False)) if story else ""
            if story:
                paragraphs = [p for p in story.split("\n\n") if p.strip()]
                if paragraphs:
                    parts.append('<section class="quote-item">')
                    for paragraph in paragraphs:
                        parts.append(f'<p>{html.escape(paragraph).replace(chr(10), "<br>")}</p>')
                    parts.append("</section>")
    return "\n".join(parts) if parts else generic_content_html(row["content"])


def reliquary_inner_html(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> str:
    source_key = row["source_key"]
    item_id = source_key.split(":", 1)[1]
    item = raw_payload(row, raw_dir)
    parts: list[str] = []

    if isinstance(item, dict):
        affix_list = item.get("affixList") or {}
        if isinstance(affix_list, dict) and affix_list:
            parts.append('<h3 class="section-title">套装效果</h3>')
            for affix_key in affix_list:
                affix_text = _clean_text(affix_list[affix_key])
                if affix_text:
                    parts.append(f'<section class="quote-item"><p>{html.escape(affix_text).replace(chr(10), "<br>")}</p></section>')

        suit = item.get("suit") or {}
        linked_sections = _linked_sections("reliquary", item_id, raw_dir)
        if isinstance(suit, dict):
            parts.append('<h3 class="section-title">部件与故事</h3>')
            for slot_key, slot_label in RELIQUARY_SLOT_ORDER:
                piece = suit.get(slot_key)
                if not isinstance(piece, dict):
                    continue
                piece_name = _clean_text(piece.get("name"))
                description = _clean_text(piece.get("description"))
                story_section = _story_section_by_name(linked_sections, piece_name)
                story = story_section.get("data") if story_section else ""
                if isinstance(story, str):
                    story = _clean_text(story)
                else:
                    story = _clean_text(json.dumps(story, ensure_ascii=False)) if story else ""
                if not piece_name and not story:
                    continue
                parts.append('<section class="quote-item">')
                heading = f"{slot_label} · {piece_name}" if piece_name else slot_label
                parts.append(f'<h4 class="role">{html.escape(heading)}</h4>')
                if description:
                    parts.append(f'<p class="muted">{html.escape(description)}</p>')
                if story:
                    for paragraph in story.split("\n\n"):
                        if paragraph.strip():
                            parts.append(f'<p>{html.escape(paragraph.strip()).replace(chr(10), "<br>")}</p>')
                parts.append("</section>")
    return "\n".join(parts) if parts else generic_content_html(row["content"])


def material_inner_html(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> str:
    source_key = row["source_key"]
    item_id = source_key.split(":", 1)[1]
    item = raw_payload(row, raw_dir)
    if not isinstance(item, dict):
        return generic_content_html(row["content"])

    parts: list[str] = []
    description = _clean_text(item.get("description") or item.get("descriptionCodex"))
    if description:
        parts.append(f'<p class="detail">{html.escape(description).replace(chr(10), "<br>")}</p>')

    info_fields = [
        ("类型", _clean_text(item.get("type"))),
        ("稀有度", f"{item.get('rank')}★" if item.get("rank") else ""),
    ]
    source_names = []
    for source in _as_list(item.get("source")):
        if isinstance(source, dict):
            source_name = _clean_text(source.get("name"))
            if source_name:
                source_names.append(source_name)
    if source_names:
        info_fields.append(("获取途径", "、".join(source_names)))
    fields = [(label, value) for label, value in info_fields if value]
    if fields:
        parts.append('<div class="info-grid">')
        for label, value in fields:
            parts.append(f'<div><span class="label">{html.escape(label)}</span>{html.escape(value)}</div>')
        parts.append("</div>")

    additions = item.get("additions") or {}
    if isinstance(additions, dict):
        required = additions.get("requiredBy") or {}
        if isinstance(required, dict):
            for kind, label in (("avatar", "关联角色"), ("weapon", "关联武器")):
                targets = _as_list(required.get(kind))
                names = []
                for target in targets:
                    if isinstance(target, dict):
                        name = _clean_text(target.get("name"))
                        if name:
                            names.append(name)
                if names:
                    parts.append(f'<h3 class="section-title">{html.escape(label)}</h3>')
                    parts.append(f'<p class="muted">{html.escape("、".join(names))}</p>')
    return "\n".join(parts)


def document_inner_html(row: Any, raw_dir: Path = DEFAULT_RAW_DIR) -> str:
    source_key = row["source_key"]
    category = row["category"]
    if source_key.startswith("quest:"):
        sections = quest_sections(row, raw_dir)
        if sections:
            parts: list[str] = []
            for section in sections:
                parts.append(f'<h3>{html.escape(section["title"])}</h3>')
                if section.get("subtitle"):
                    parts.append(f'<p class="muted">{html.escape(section["subtitle"])}</p>')
                for step in section.get("steps", []):
                    parts.append(f'<div class="story-step"><h4>{html.escape(step["title"])}</h4>')
                    for dialogue in step["dialogues"]:
                        role = dialogue["role"]
                        cls = "dialogue" if role else "dialogue blank"
                        role_html = f'<span class="role">{html.escape(role) if role else "旁白"}</span>'
                        parts.append(f'<div class="{cls}">{role_html}<p class="text">{html.escape(dialogue["text"]).replace(chr(10), "<br>")}</p></div>')
                    parts.append("</div>")
            return "\n".join(parts)
    if source_key.startswith("weapon:"):
        return weapon_inner_html(row, raw_dir)
    if source_key.startswith("reliquary:"):
        return reliquary_inner_html(row, raw_dir)
    if source_key.startswith("material:"):
        return material_inner_html(row, raw_dir)
    return generic_content_html(row["content"])


def character_inner_html(profile: dict[str, Any]) -> str:
    basic = profile["basic"]
    parts: list[str] = []
    info_fields = [
        ("称号", basic.get("title")),
        ("命之座", basic.get("constellation")),
        ("所属", basic.get("native")),
        ("元素", basic.get("element")),
        ("武器", basic.get("weaponType")),
        ("地区", basic.get("region")),
        ("生日", basic.get("birthday")),
    ]
    fields = [(label, value) for label, value in info_fields if value]
    if fields:
        parts.append('<div class="info-grid">')
        for label, value in fields:
            parts.append(f'<div><span class="label">{label}</span>{html.escape(value)}</div>')
        parts.append("</div>")
    if basic.get("detail"):
        parts.append(f'<p class="detail">{html.escape(basic["detail"])}</p>')
    if basic.get("cv"):
        parts.append(f'<p class="muted">配音　{html.escape(basic["cv"])}</p>')

    parts.append('<h3 class="section-title">角色故事</h3>')
    if profile["stories"]:
        for story in profile["stories"]:
            parts.append('<section class="quote-item">')
            parts.append(f'<h4 class="role">{html.escape(story["title"])}</h4>')
            parts.append(f'<p>{html.escape(story["text"]).replace(chr(10), "<br>")}</p>')
            if story.get("tips"):
                parts.append(f'<span class="tips">{html.escape(story["tips"])}</span>')
            parts.append("</section>")
    else:
        parts.append('<p class="muted">暂无已采集的角色故事。</p>')

    parts.append('<h3 class="section-title">角色语音</h3>')
    if profile["quotes"]:
        for quote in profile["quotes"]:
            parts.append('<section class="quote-item">')
            parts.append(f'<h4 class="role">{html.escape(quote["title"])}</h4>')
            parts.append(f'<p>{html.escape(quote["text"]).replace(chr(10), "<br>")}</p>')
            if quote.get("tips"):
                parts.append(f'<span class="tips">{html.escape(quote["tips"])}</span>')
            parts.append("</section>")
    else:
        parts.append('<p class="muted">暂无已采集的角色语音。</p>')
    return "\n".join(parts)


def row_dict(row: Any) -> dict[str, Any]:
    return {
        "source_key": row["source_key"],
        "category": row["category"],
        "title": row["title"],
        "content": row["content"],
        "source_url": row["source_url"],
        "payload_path": row["payload_path"],
    }


def chrome_pdf(html_text: str, output: Path, chrome: str = "google-chrome") -> None:
    """Render local HTML to PDF with the same CSS as the web page."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as handle:
        handle.write(html_text)
        html_path = Path(handle.name)
    try:
        cmd = [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output}",
            html_path.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "Chrome exited with an error").strip())
    finally:
        html_path.unlink(missing_ok=True)


def html_to_pdf_bytes(html_text: str, chrome: str = "google-chrome") -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        output = Path(handle.name)
    try:
        chrome_pdf(html_text, output, chrome=chrome)
        return output.read_bytes()
    finally:
        output.unlink(missing_ok=True)


def html_export_page(title: str, body_html: str, active: str = "") -> str:
    nav = "".join(
        f'<a href="{html.escape(item["href"])}" class="{"active" if item["key"] == active else ""}">{html.escape(item["label"])}</a>'
        for item in NAV_ITEMS
    )
    return f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · 原神文本收藏</title><style>{BASE_CSS}</style>
<body><nav class="topnav no-print"><span class="brand">原神文本收藏</span>{nav}</nav>
<main class="shell">
<div class="article-card">{body_html}</div>
</main></body></html>"""


def html_character_page(profile: dict[str, Any], title: str | None = None) -> str:
    body = f'<p class="category">角色资料</p><h1>{html.escape(profile["basic"]["name"])}</h1>'
    body += '<div class="ornament">◆</div>'
    body += character_inner_html(profile)
    body += f'<p class="source">数据来源：<a href="{html.escape(profile["source_url"], quote=True)}">{html.escape(profile["source_url"])}</a></p>'
    return html_export_page(title or profile["basic"]["name"], body, "characters")


def collection_body(
    store: Any,
    rows: Iterable[Any],
    raw_dir: Path = DEFAULT_RAW_DIR,
    query: str = "",
) -> str:
    """Render a mixed collection while merging character rows into profiles."""
    rows = list(rows)
    avatar_rows = [row for row in rows if row["category"] == "角色/故事"]
    other_rows = [row for row in rows if row["category"] != "角色/故事"]

    parts: list[str] = [
        '<p class="category">检索导出</p><h1>原神文本收藏</h1><div class="ornament">◆</div>'
    ]

    if avatar_rows:
        groups = matching_character_groups(store, raw_dir, query)
        for item in groups:
            profile = character_profile(store, item["key"], raw_dir)
            if profile is None:
                continue
            parts.append(
                f'<section class="article-card"><p class="category">角色资料</p>'
                f'<h2>{html.escape(profile["basic"]["name"])}</h2>'
            )
            parts.append(character_inner_html(profile))
            parts.append(
                f'<p class="source">数据来源：<a href="{html.escape(profile["source_url"], quote=True)}">'
                f'{html.escape(profile["source_url"])}</a></p></section>'
            )

    for row in other_rows:
        if row["category"] == "任务":
            meta = quest_metadata_for_row(row, raw_dir)
            title = meta.get("display_label") or row["title"]
            category = meta.get("type_label") or row["category"]
        else:
            title = row["title"]
            category = row["category"]
        parts.append(
            f'<section class="article-card"><p class="category">{html.escape(category)}</p>'
            f'<h2>{html.escape(title)}</h2>'
            + document_inner_html(row, raw_dir)
            + f'<p class="source">来源：<a href="{html.escape(row["source_url"], quote=True)}">'
            + html.escape(row["source_url"])
            + "</a></p></section>"
        )
    return "\n".join(parts)
