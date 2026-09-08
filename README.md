# DiscernBrief

持续监控国内外公开信息，从海量数据中筛出"值得行动的商业信号"的信息雷达系统。

> Spec: [`SPEC.md`](./SPEC.md) · Skill: `DiscernBrief` (skill_workshop)
> Status (2026-09-08): Phase 1–6 + Phase 7 (interactive card) + Phase 9 (scheduling). Phase 8 (bot) deferred.

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ OpenClaw automation (*/30 * * * *) — schedules run-cycle      │
└──────────────┬──────────────────────────────────────────────┘
               │ agentTurn wakes the assistant
               ▼
┌─────────────────────────────────────────────────────────────┐
│ python3 -m discernbrief.cli run-cycle --staged               │
│   ├── phase:fast   → write /tmp/radar_pending-fast.json      │
│   └── phase:slow   → write /tmp/radar_pending-slow.json      │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Assistant (you, in the next turn)                             │
│   1. Read pending.json                                       │
│   2. Judge each item per SPEC §25 schema                    │
│   3. Write /tmp/radar_judgments.json                         │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│ python3 -m discernbrief.cli ingest-signals                   │
│   → writes to signals table (SQLite)                         │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│ python3 -m discernbrief.cli report --days 2 --json          │
│   + Feishu interactive card via message tool                 │
└─────────────────────────────────────────────────────────────┘
```

**关键设计**：AI filter 是 OpenClaw assistant 本身 — 无外部 LLM server。Pipeline 写 `pending.json` 给 assistant 看，assistant 写 `judgments.json`，CLI ingest。（Per SPEC.md.）

## 安装

```bash
cd /Users/jiang/.openclaw/workspace/projects/DiscernBrief
# 必需：Python 3.9+（已用 stdlib sqlite3 + urllib，无 pip 依赖）
# 可选：curl（CN CDN 时 FallbackFetcher 自动切 curl）
python3 --version
```

数据库 schema-on-open，首次 `python3 -m discernbrief.cli` 命令自动建表。

## 命令速查

```bash
# 配置与状态
python3 -m discernbrief.cli sources                # 所有源 + enabled 状态
python3 -m discernbrief.cli status                 # DB 统计 + 最近 run

# 采集
python3 -m discernbrief.cli ingest                   # 全 enabled 源
python3 -m discernbrief.cli ingest --source hackernews,arxiv
python3 -m discernbrief.cli ingest-fast             # 只 fast tier（~30s）
python3 -m discernbrief.cli ingest-slow             # 只 slow tier（~2min）

# 端到端
python3 -m discernbrief.cli run-cycle                # 全 enabled + 写 pending.json
python3 -m discernbrief.cli run-cycle --tier fast    # 只 fast
python3 -m discernbrief.cli run-cycle --staged       # 分阶段：fast → slow
python3 -m discernbrief.cli run-cycle --staged --pending-file /tmp/x.json

# Filter / judge
python3 -m discernbrief.cli filter-prompt --limit 10 --out /tmp/p.json
python3 -m discernbrief.cli ingest-signals /tmp/judgments.json

# 报告
python3 -m discernbrief.cli signals
python3 -m discernbrief.cli report --days 2 --json
```

## 数据模型

| 表 | 字段 |
|---|---|
| `sources` | source_id, name, country, category, type, enabled, priority, tier (fast/slow), consecutive_failures, disabled_reason |
| `raw_items` | source_id, external_id, url, title, content, published_at, content_hash, metadata |
| `signals` | title, summary, why_it_matters, business_angle, category, importance, confidence, source_urls, raw_item_ids (JSON) |
| `signal_raw_items` | signal_id ↔ raw_id（多对多 join） |
| `runs` | started_at, finished_at, source_count, raw_item_count, status, error |

## Sources 现状（2026-09-08）

**32 源登记，18 enabled**：

| Tier | Source | Status |
|---|---|---|
| fast | hackernews_best, lobsters, lwn | ✅ |
| fast | arxiv, openai_blog, google_ai_blog, anthropic_sdk | ✅ |
| fast | techcrunch, theverge, google_news | ✅ |
| fast | geekpark (FeedBurner), v2ex (/index.xml), qbitai | ✅ |
| fast | sspai, synced | ✅ |
| slow | hackernews (30 stories), reddit_rss (7 subs), github_releases (11 repos) | ✅ |
| disabled | kr36, jiqizhixin, gdelt | ❌ auto/manual |
| deferred | huxiu, geekpark (legacy), anthropic_news, github_trending, producthunt, youtube_trending, weibo, zhihu, huggingface_papers, microsoft_ai_blog, nvidia_blog, indiehackers, cnbc, reuters, google_trends | ⏸ |

## Auto-disable

每个 source 有 `consecutive_failures` 计数。`run-cycle` 每次 collect 完调：
- 成功 → `record_source_success(source_id)` 清零
- 失败 → `record_source_failure(source_id, reason)` 累加

阈值默认 **2**（连续失败 ≥2 → 自动 `enabled=0` + 写 `disabled_reason`）。

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

## 目录结构

```
DiscernBrief/
├── SPEC.md                         # 用户提交的原始 spec
├── README.md                       # 本文件
├── sources.yaml                    # Source Registry（30+ 源）
├── discernbrief/
│   ├── __init__.py
│   ├── cli.py                      # argparse 入口
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
│   │   ├── rss.py                  # 多个 RSS 子类
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
