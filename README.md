# DiscernBrief

持续监控国内外公开信息，从海量数据中筛出"值得行动的商业信号"的信息雷达系统。

> Spec: [`SPEC.md`](./SPEC.md) · Skill: `DiscernBrief` (skill_workshop) · 
> Repo: https://github.com/free-revalution/DiscernBrief
> Status (2026-09-11): Pipeline 健康（24h 实测 9/11 cycle 成功）。**`sync-bitable` 已移除**（commit ff3ae94，飞书 5000 行上限 + cron 卡死）；改用 `export-xlsx --daily` 按日归档到 `cache/excel/<日期>/`。Phase 8 (bot) deferred.

## 设计哲学

- **数据采集常驻** — 30min fast cycle + 30min slow cycle 持续入 DB（不漏数据）
- **推送每天一次** — 30min cycle 不再 spam 飞书卡片（安静入 DB 即可）
- **08:00 daily brief** — Excel 全量 + 行业分析卡 + 深度价值挖掘卡，固定每天一次
- **不阻塞对话控制** — 所有 4 个 automation 都在 `current` session，可正常 `/discernbrief` 调

## Recent Updates

- **`cache/` 目录**：`export-xlsx --daily` 按 `cache/excel/YYYY-MM-DD/DiscernBrief-YYYY-MM-DD.xlsx` 自动归档（不再需要手填 `--out`）
- **`sync-bitable` 已移除**（commit ff3ae94，飞书存储上限 + cron 卡死）：调它现在返回 deprecation 提示 + exit 0
- **`unsynced` 字段退出 `status` 默认视图**：仍可通过 `discernbrief query --preset summary` 看
- **`cmd_export_xlsx --daily --tz <iana>`**：支持自定义时区（默认 `Asia/Shanghai`）
- **`daily-content` 子命令**：从前 24h Excel 提取 top 3 信号 → 知识星球 3 篇（不同角度）+ 小红书 + 即刻，全部带合规标识（AI 显式+隐式+风险提示+付费声明）。可选 `--feishu-target` 输出投递 manifest 给 OpenClaw cron 投递到飞书。

## 架构

```
   ┌── 数据采集（每 30min，无 spam）──┐
   │                                    │
   │  fast cycle  ──┐                 │
   │  (15 src)      │  ingest →        │
   │  (~30s)        │  SQLite +         │
   │                │  cache/excel/     │
   │  slow cycle ──┘                  │
   │  (3 src, 30s-2min)              │
   │  + STALE GUARD 2h               │
   │                                    │
   └────────────────────────────────────┘

                  │ 
                  ▼ 每天 08:00 Asia/Shanghai

   ┌── 每日晨报 (daily brief) ─────────┐
   │                                  │
   │  1. export-xlsx 24h  → 飞书文件   │
   │  2. per-industry  → 飞书分析卡  │
   │  3. deep value  → 飞书深度卡     │
   │  4. summary  → 飞书一行          │
   │                                  │
   └──────────────────────────────────┘
```

## 4 个 OpenClaw Automation

| ID 简写 | cron | 行为 | 飞书输出 |
|---|---|---|---|
| fast | `*/30 * * * *` | 15 个 fast 源 (RSS, ~30s) | 静默（只入 DB + 写 cache/excel/）|
| slow | `15,45 * * * *` | 3 个 slow 源 (HN+Reddit+GH, ~2min) + STALE GUARD 2h | 静默（只入 DB + 写 cache/excel/）|
| backup | `0 2 * * *` | SQLite dump + 5 个 .csv + git push | 静默（除非失败）|
| brief | `0 8 * * *` | export-xlsx 24h + 行业分析 + 深度价值挖掘 | **飞书** Excel + 多张卡 |
| **daily-content** | `30 7 * * *` | 昨日 top 3 信号 → 知识星球/小红书/即刻 发布模板 + 飞书投递 | **飞书** 多卡 + 附件 |

## 每日内容生成（知识星球 / 小红书 / 即刻）

每天 07:30 cron 跑 `daily-content`，从前 24 小时 Excel 提取 top 3 信号，为每个信号生成：
- 3 篇知识星球深度文（不同角度：产业链拆解 / 商业模式重估 / 个体影响）
- 1 篇小红书引流帖
- 1 篇即刻引流帖

每个 .md 自动带中国法规合规标识（AI 显式 + 隐式 + 风险提示 + 付费声明）。

```bash
discernbrief daily-content --date $(date -v-1d +%F) --top 3 --feishu-target <chat_id>
```

详见 SKILL.md STEP 7。

## Pipeline 详细

### 数据采集（fast + slow）

```bash
cd $PROJ
python3 -m discernbrief.cli run-cycle --tier fast   # ~30s
# 或 --tier slow
# 或 --staged（先 fast 再 slow）

# agentTurn 触发（fast 30min / slow 30min）
# 读 /tmp/radar_pending-{fast,slow}.json
# 判每条 → 写 /tmp/radar_judged.json
# ingest-signals → DB
# → cache/excel/<YYYY-MM-DD>/ (auto-dated by --daily mode)
# ⚠️ 不发飞书 card（避免 spam）
```

### 每日 08:00 晨报

```bash
# 1. 生成 Excel
python3 -m discernbrief.cli export-xlsx --days 1 --out /tmp/DiscernBrief-2026-09-09.xlsx

# 2. agentTurn（brief 唯一会发飞书）
# - 上传 .xlsx 附件到飞书
# - 查询按类别分组，发"行业分析卡" (3-4 张)
# - 查询全 DB 找高价值信号，发"深度价值卡" (5-8 张)
# - 一行总结收尾
```

## 安装

```bash
git clone https://github.com/free-revalution/DiscernBrief.git
cd DiscernBrief

# 必需：Python 3.9+（stdlib sqlite3 + urllib，零 pip 依赖）
# 推荐：xlsxwriter（export-xlsx 用）
pip3 install xlsxwriter

# 可选：curl（CN CDN 时 FallbackFetcher 自动切 curl）

# 初始化 Bitable 凭据（飞书 Bitable 同步用）
mkdir -p ~/.openclaw
cat > ~/.openclaw/feishu_creds.json <<EOF
{
  "app_id": "cli_xxx",
  "app_secret": "YOUR_SECRET"
}
EOF
chmod 600 ~/.openclaw/feishu_creds.json
```

数据库 schema-on-open，首次 `python3 -m discernbrief.cli status` 自动建表。

## 命令速查

```bash
# 配置与状态
python3 -m discernbrief.cli sources
python3 -m discernbrief.cli status

# 采集
python3 -m discernbrief.cli ingest                    # 全 enabled
python3 -m discernbrief.cli ingest --source hackernews,arxiv
python3 -m discernbrief.cli ingest-fast
python3 -m discernbrief.cli ingest-slow

# 端到端
python3 -m discernbrief.cli run-cycle
python3 -m discernbrief.cli run-cycle --tier fast
python3 -m discernbrief.cli run-cycle --tier slow
python3 -m discernbrief.cli run-cycle --staged

# Filter / judge
python3 -m discernbrief.cli filter-prompt --limit 10 --out /tmp/p.json
# 读 /tmp/p.json，判，写 /tmp/radar_judged.json
python3 -m discernbrief.cli ingest-signals /tmp/radar_judged.json

# 报告 / 分析（给 agentTurn / 08:00 brief 用）
python3 -m discernbrief.cli signals
python3 -m discernbrief.cli report --days 2 --json

# 每日晨报导出
python3 -m discernbrief.cli export-xlsx --days 1 --out /tmp/brief.xlsx
python3 -m discernbrief.cli query --preset summary|categories|cycles|trends|topurls|recent
python3 -m discernbrief.cli query --sql "SELECT ..."

# 备份 + 飞书 Bitable 同步
python3 -m discernbrief.cli backup --out ./backups --push
# sync-bitable 已移除（commit ff3ae94），用 export-xlsx --daily 代替
```

## 数据模型

| 表 | 字段 |
|---|---|
| `sources` | source_id, name, country, category, type, enabled, priority, **tier (fast/slow)**, consecutive_failures, disabled_reason, disabled_at |
| `raw_items` | source_id, external_id, url, title, content, **published_at (源发布时间)**, content_hash, **collected_at (本地抓取时间)**, metadata |
| `signals` | id, title, summary, why_it_matters, business_angle, category, importance, confidence, source_urls, raw_item_ids, **published_at, created_at**, ingested_at |
| `signal_raw_items` | signal_id ↔ raw_id（多对多 join）|
| `runs` | started_at, finished_at, source_count, raw_item_count, status, error |

时间戳是分析的核心：published_at（源）→ collected_at（抓取）→ created_at（判后入库）— 24h 窗口、周期分析、跨源去重都靠它。

## Sources 现状（2026-09-09）

**32 源登记，18 enabled**（多了 V2EXCollector 独立子）：

| Tier | Source | Status |
|---|---|---|
| fast | hackernews_best, lobsters, lwn | ✅ |
| fast | arxiv, openai_blog, google_ai_blog, anthropic_sdk | ✅ |
| fast | techcrunch, theverge, google_news | ✅ |
| fast | geekpark (FeedBurner), v2ex (/index.xml), qbitai | ✅ |
| fast | sspai, synced | ✅ |
| slow | hackernews (30 stories), reddit_rss (7 subs), github_releases (11 repos) | ✅ |
| disabled | kr36, jiqizhixin, gdelt | ❌ auto/manual |
| deferred | huxiu, anthropic_news, github_trending, producthunt, youtube_trending, weibo, zhihu, huggingface_papers, microsoft_ai_blog, nvidia_blog, indiehackers, cnbc, reuters, google_trends | ⏸ |

## Auto-disable

每个 source 有 `consecutive_failures` 计数。`run-cycle` 每次 collect 完调：
- 成功 → `record_source_success(source_id)` 清零
- 失败 → `record_source_failure(source_id, reason)` 累加

阈值默认 **2**（连续失败 ≥2 → 自动 `enabled=0` + 写 `disabled_reason`）。

## 飞书同步（已废弃）

项目不再支持飞书 Bitable 同步 — 之前因为 5000 行上限 + cron 触发 → 反复 ModuleNotFoundError 卡死飞书。
数据现在只存本地 SQLite + `cache/excel/<日期>/`，按日归档：

```bash
discernbrief export-xlsx --days 1 --daily
# → cache/excel/2026-09-11/DiscernBrief-2026-09-11.xlsx
```

调用 `sync-bitable` 现在会返回 deprecation 提示（exit 0）而不是 `invalid choice` 错误。

## 已知限制

| 项 | 状态 | 备注 |
|---|---|---|
| Feishu 真 doc | ❌ | 需 `docx:document` scope；用 interactive card 代替 |
| Anthropic 官方 blog | ❌ | 用 GitHub releases 镜像 |
| 微博 / 知乎 / 抖音 | ❌ | anti-bot / 脆弱 API |
| YouTube / Product Hunt | ❌ | 需 OAuth/API key |
| NewsAPI / Event Registry | ⏸ | 需 API key，能补英文新闻正文 snippet |
| Bilibili / GitHub Trending | ⏸ | 待加 |
| 36氪 / 虎嗅 / 极客公园真 RSS | ❌ | 服务端返 anti-bot / 404 / 405，已禁用 |
| slow tier 反复挂起 | ⚠️ | HN/Reddit 偶发 socket hang，60s 后 SIGTERM，回退 stale 文件 |

## 目录结构

```
DiscernBrief/
├── SPEC.md                         # 用户提交的原始 spec
├── README.md                       # 本文件
├── sources.yaml                    # Source Registry（32 源）
├── discernbrief/
│   ├── __init__.py
│   ├── cli.py                      # argparse 入口（cmd_ingest/run-cycle/filter/report/export-xlsx/backup/query）
│   ├── config.py                   # Registry + SourceConfig dataclass
│   ├── db.py                       # SQLite schema + 轻量 migration
│   ├── models.py                   # RawItem / RunResult
│   ├── normalize.py                # URL/title 清理
│   ├── dedup.py                    # title 相似度去重
│   ├── collectors/
│   │   ├── base.py                 # HttpFetcher / CurlFetcher / FallbackFetcher
│   │   ├── hackernews.py
│   │   ├── gdelt.py                # disabled
│   │   ├── arxiv.py
│   │   ├── rss.py                  # 多个 RSS 子类（含 V2EXCollector）
│   │   ├── github_releases.py
│   │   └── anthropic_sdk.py
│   └── analyze/
│       ├── schema.py               # Signal dataclass + category/importance enum
│       ├── filter.py               # FilterPipeline（fetch + prompt + parse）
│       └── llm.py                  # ManualLlm（= 我）
└── data/
    └── discernbrief.db             # SQLite（运行时自动生成）
```

## License & Contact

Internal OpenClaw project. Use per SPEC.md §31 compliance rules.
