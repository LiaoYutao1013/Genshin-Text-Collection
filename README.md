# Genshin Text Collection

从 Project Amber（安柏网）公开的简体中文数据接口建立本地、可全文检索的原神文本库。

> 内容的著作权归米哈游及各原始权利人所有。本项目仅供个人离线查阅、研究和打印；请遵守来源站点的服务条款、robots 规则和当地法律，不要将导出的完整数据重新发布。

## 快速开始

```bash
conda activate yolo
./scripts/setup.sh
./scripts/crawl.sh --check-only
./scripts/crawl.sh
./scripts/serve.sh
```

浏览器打开 `http://127.0.0.1:8765`。工程使用 `yolo` Conda 环境中的 `httpx`、Rich、Typer、Flask 和 nbformat；依赖版本记录于 `requirements-yolo.txt`。数据写入 `data/genshin.sqlite3`，原始 API 响应缓存于 `data/raw/`，可随时中断后重新执行抓取命令。

页面现在提供：

- 仿米游社观测枢的本地浏览样式，任务文本按剧情回顾方式展示带说话人的对白；
- 角色页按角色聚合基本信息、角色故事与语音，旅行者不同属性会合并为一个入口；
- 顶部导航按任务、角色、武器、圣遗物、书籍、名片分类浏览；
- 每个页面和检索结果都提供 PDF 导出，导出的 PDF 与网页使用同一套排版样式。

任务页 `http://127.0.0.1:8765/quests` 会按魔神任务、传说任务、活动任务、世界任务和国家/地区分组，并显示章节/幕数与任务标题。例如“第五章 第五幕 · 炽烈的还魂诗”可以直接通过标题、章节或幕数检索，不再只显示数字编号。

素材页 `http://127.0.0.1:8765/materials` 展示武器突破素材、角色天赋书、角色培养素材和周本五星素材；同一系列或同一首领掉落会聚合到一个子页面。首次采集素材运行：

```bash
./scripts/crawl.sh --categories material
```

`./scripts/setup.sh` 会将工程以可编辑模式安装到 `yolo` 环境。因此 `notebooks/` 下的 Notebook 可从任意工作目录直接打开；首格会从已安装包的位置定位工程目录，无需切换 Jupyter 的启动目录。

## 抓取策略

默认来源是 `https://gi.yatta.moe/api/v2/chs/`，语言固定为简体中文。采集器按分类索引逐条取得条目详情，涵盖任务（魔神、传说、活动、世界任务等由条目标签/字段分组）、角色资料、武器、圣遗物、书籍/图鉴等。它会：

- 每个请求至少间隔 2.5 秒，且只有一个并发请求；
- 请求前检查 `robots.txt`；
- 使用本地缓存和 SQLite 进度，避免重复下载；
- 网络错误指数退避；收到 `403`、`429`、Cloudflare 验证页或 robots 禁止时立即停止；
- 不使用代理、验证码绕过或规避访问控制。

接口字段或分类发生变化时，可通过 `--categories` 指定实际分类，例如：

```bash
./scripts/crawl.sh --categories quest,avatar,weapon,reliquary,book
```

先用 `--limit 3` 验证当前接口，再开始完整抓取：

```bash
./scripts/crawl.sh --limit 3
./scripts/crawl.sh
```

如果早期版本已经下载了主条目但遗漏角色故事、武器故事或圣遗物五件套故事，请运行以下补全命令。它不会重新下载主条目，只会读取 `data/raw/` 中已有 JSON 并补抓关联故事：

```bash
./scripts/crawl.sh --categories avatar,weapon,reliquary --refresh-linked
```

## 命令行检索与导出

```bash
./scripts/search.sh "璃月 港口"
./scripts/export.sh --format html --query "安柏" --output exports/amber.html
./scripts/export.sh --format markdown --category "任务/世界任务" --output exports/world-quests.md
./scripts/export.sh --format pdf --query "芙宁娜" --category "角色/故事" --output exports/furina.pdf
./scripts/export.sh --format pdf --query "第五章 第五幕" --category "任务" --output exports/natlan-act5.pdf
```

HTML/PDF 导出使用与网页相同的排版样式；`pdf` 格式会调用本机的无头 Chrome 生成文件。导出范围默认为全库，建议用关键词或分类缩小打印内容。角色分类会自动合并为角色档案页，而不是逐条输出原始数据库记录。

## 目录

- `genshin_text/collector.py`: 礼貌、可恢复的 API 采集核心。
- `genshin_text/store.py`: SQLite + FTS5 本地索引。
- `genshin_text/web.py`: Flask 本地检索和打印页面。
- `genshin_text/cli.py`: `collect`、`search`、`export`、`serve` 统一命令。
- `notebooks/`: 可逐格记录 robots 检查、试抓、全量采集、检索与导出过程。
- `data/`: 运行时数据库与原始缓存（不纳入版本控制）。
