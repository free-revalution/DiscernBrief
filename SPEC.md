# AI Opportunity Radar — OpenClaw 数据源接入清单与实施规范

> 目标：给 OpenClaw / AI Agent 使用的国内外公开数据源池。
>
> 核心原则：**不是把所有平台全部接入，而是建立统一 Source Registry，再按优先级逐步启用。**
>
> 产品定位：**公共合法信息 → 清洗去重 → AI 分析 → 商业信号 → 飞书交付**。

---

## 1. 产品目标

AI Opportunity Radar 不应该做成单纯的新闻聚合器。

目标是：

```text
国内外公开信息
      ↓
Source Registry
      ↓
定时采集
      ↓
清洗 / 去重 / 聚类
      ↓
AI 判断：
  - 是否值得关注
  - 属于什么领域
  - 为什么重要
  - 对什么人有商业价值
      ↓
Commercial Signal
      ↓
飞书日报 / 飞书 Bot
```

最终输出的不是“今天发生了什么”，而是：

> **哪些变化可能影响赚钱、创业、销售、产品、内容、电商、采购、技术选型等实际决策。**

---

# 2. 数据源分级

建议所有 Source 都有等级：

| 等级 | 定义 | 示例 |
|---|---|---|
| S | 官方、一手、原始数据 | 政府、公司官方公告、官方 API |
| A | 高质量媒体 / 专业数据库 | Reuters、TechCrunch、36氪 |
| B | 行业媒体 / 专业社区 | 机器之心、InfoQ、V2EX |
| C | 社交趋势 | Reddit、微博、知乎、YouTube |
| D | 未验证个人内容 | 个人博客、匿名账号 |

AI 在最终排序时应优先信任 S/A，其次 B/C。

D 类信息默认只能作为“趋势线索”，不能直接作为事实依据。

---

# 3. 第一阶段建议启用的 30 个核心数据源

OpenClaw 第一阶段不要接入全部平台。

建议优先：

1. Google News
2. GDELT
3. Hacker News
4. Reddit
5. GitHub
6. Product Hunt
7. TechCrunch
8. The Verge
9. CNBC
10. Reuters
11. arXiv
12. Hugging Face
13. OpenAI 官方
14. Anthropic 官方
15. Google AI / DeepMind
16. Microsoft AI
17. NVIDIA
18. Indie Hackers
19. YouTube
20. Google Trends
21. 36氪
22. 虎嗅
23. 极客公园
24. 机器之心
25. 量子位
26. 新智元
27. V2EX
28. 少数派
29. 微博
30. 知乎

---

# 4. 全球新闻与信息

## 4.1 综合新闻

- Google News
- GDELT
- Reuters
- AP
- BBC
- CNN
- CNBC
- Bloomberg
- Financial Times
- Wall Street Journal
- The Guardian
- New York Times
- The Economist
- Politico
- NPR

### OpenClaw 用途

重点寻找：

- 政策变化
- 公司重大事件
- 行业变化
- 新产品
- 市场变化
- 消费趋势
- 企业融资
- 新商业模式
- 国际贸易变化

---

# 5. AI / 科技

## 5.1 官方一手来源

优先级最高：

- OpenAI
- Anthropic
- Google AI
- Google DeepMind
- Microsoft AI
- Meta AI
- NVIDIA
- Apple
- Amazon
- ByteDance
- Alibaba
- Tencent
- Baidu
- Huawei

重点监控：

- 产品发布
- API 更新
- 模型发布
- 定价变化
- SDK
- 开源项目
- 开发者政策
- 合作伙伴
- 企业应用
- 招聘变化
- 官方博客

---

## 5.2 科技媒体

- TechCrunch
- The Verge
- Ars Technica
- MIT Technology Review
- VentureBeat
- Wired
- 36氪
- 虎嗅
- 极客公园
- 钛媒体
- 机器之心
- 量子位
- 新智元
- AI科技评论
- 雷锋网
- InfoQ
- 开源中国
- CSDN
- 少数派
- 爱范儿

---

# 6. AI / 开源 / 开发者生态

重点来源：

- GitHub
- GitHub Trending
- GitHub Releases
- GitHub Issues
- GitHub Pull Requests
- GitLab
- Gitee
- Hugging Face
- Hugging Face Papers
- Docker Hub
- npm
- PyPI
- Maven Central
- Homebrew
- Hacker News
- V2EX
- 掘金
- SegmentFault
- InfoQ
- OSCHINA

重点检测信号：

```text
GitHub Stars 快速增长
        ↓
Fork 快速增长
        ↓
Issue / PR 活跃
        ↓
Hugging Face 热度增长
        ↓
Hacker News 讨论
        ↓
媒体报道
        ↓
商业化可能性
```

不要只统计 Star。

应综合：

- stars 增速
- forks 增速
- commits
- release
- issue
- PR
- contributors
- HN 讨论
- Reddit 讨论
- Product Hunt
- 媒体报道

---

# 7. 创业 / VC / 新产品

数据源：

- Product Hunt
- Y Combinator
- Crunchbase
- Dealroom
- PitchBook
- CB Insights
- Tracxn
- TechCrunch
- Sifted
- Tech.eu
- VentureBeat
- Hacker News
- Indie Hackers
- BetaList
- Uneed
- AlternativeTo

重点寻找：

- 新产品
- 新商业模式
- 新 SaaS
- AI Agent
- 开源商业化
- 创业融资
- 产品增长
- 收购
- 新市场
- 用户痛点

---

# 8. 社区 / 社交趋势

## 8.1 Reddit

重点 Subreddit：

- r/artificial
- r/ChatGPT
- r/OpenAI
- r/ClaudeAI
- r/LocalLLaMA
- r/MachineLearning
- r/technology
- r/startups
- r/Entrepreneur
- r/SaaS
- r/SideProject
- r/indiehackers
- r/ecommerce
- r/FulfillmentByAmazon
- r/dropshipping
- r/marketing
- r/smallbusiness
- r/investing
- r/stocks
- r/quant

注意：

Reddit 内容主要用于发现：

- 用户需求
- 痛点
- 产品评价
- 新趋势
- 真实使用体验

不能把 Reddit 用户发言直接当作事实来源。

---

## 8.2 中国社交平台

- 微博
- 知乎
- 小红书
- Bilibili
- 抖音
- 快手
- 即刻

注意：

只使用合法公开访问方式。

禁止为了抓取而：

- 绕过登录
- 绕过 CAPTCHA
- 绕过反爬
- 使用盗取 Cookie
- 使用未经授权接口
- 绕过付费墙

---

# 9. 电商

## 中国

- 淘宝
- 天猫
- 京东
- 拼多多
- 1688
- 阿里巴巴国际站

## 海外

- Amazon
- eBay
- Etsy
- Walmart
- Shopify

## 电商专业数据

- Jungle Scout
- Helium 10
- Keepa
- Similarweb
- Semrush
- Google Trends
- Exploding Topics
- Trend Hunter
- Pinterest Trends
- TikTok Creative Center
- Meta Ad Library
- Google Ads Transparency Center

---

# 10. 电商机会分析

未来可以形成：

```text
Amazon 热门商品
        +
Google Trends 增长
        +
TikTok 热度
        +
1688 供应链价格
        +
广告投放数据
        ↓
商品机会信号
```

例如：

```text
海外需求快速增长
+
中国供应链成本较低
+
竞争尚未严重
+
社交媒体热度上升
=
跨境电商机会
```

第一阶段不要直接做完整选品系统。

先做“机会信号”。

---

# 11. 搜索趋势 / SEO

- Google Trends
- Google News
- Similarweb
- Semrush
- Ahrefs
- Exploding Topics
- AnswerThePublic
- AlsoAsked

重点：

- 搜索量增长
- 新关键词
- 新兴需求
- 季节性
- 地区差异
- 用户问题变化

---

# 12. 广告趋势

- Meta Ad Library
- TikTok Creative Center
- Google Ads Transparency Center

可以分析：

- 什么产品正在投广告
- 哪些广告持续存在
- 创意变化
- 品牌增长
- 新产品进入市场

注意：

广告库数据只用于趋势分析，不要复制受版权保护的完整广告素材。

---

# 13. App / 软件市场

- Apple App Store
- Google Play
- Product Hunt
- AlternativeTo
- Similarweb

重点：

- 新 App
- 排名变化
- 评论增长
- 用户痛点
- 替代产品
- 新功能

---

# 14. 科研 / 技术突破

- arXiv
- Semantic Scholar
- Google Scholar
- Hugging Face Papers
- Papers With Code
- PubMed
- Crossref
- OpenAlex

重点：

- 新论文
- 新模型
- 新算法
- 新 benchmark
- 新数据集
- 新开源项目

不要直接把论文热度等同于商业价值。

需要 AI 判断：

```text
技术突破
↓
是否可落地？
↓
成本是否下降？
↓
是否出现产品化？
↓
是否产生新的用户需求？
↓
是否产生商业机会？
```

---

# 15. 政府 / 政策

## 中国

重点：

- 中国政府网
- 工业和信息化部
- 国家发展改革委
- 商务部
- 市场监管总局
- 国家数据局
- 科技部
- 国家金融监督管理总局
- 中国人民银行
- 中国证监会
- 海关总署
- 国家知识产权局

## 海外

- White House
- U.S. Congress
- SEC
- FTC
- FDA
- Federal Reserve
- EU Commission
- ECB
- UK Government
- FCA
- World Bank
- IMF
- OECD

政策源优先级应非常高。

因为：

```text
政策变化
→ 行业规则变化
→ 成本变化
→ 供需变化
→ 商业机会 / 风险
```

---

# 16. 金融数据

可以监控：

## 海外

- SEC EDGAR
- Yahoo Finance
- Google Finance
- Nasdaq
- NYSE
- TradingView
- Alpha Vantage
- FRED
- Federal Reserve
- ECB
- World Bank
- IMF
- OECD

## 中国

- 中国证监会
- 上海证券交易所
- 深圳证券交易所
- 北京证券交易所
- 巨潮资讯
- 东方财富
- 同花顺
- 雪球

### 重要合规限制

第一阶段禁止把系统做成：

- 股票买卖推荐
- 个股预测
- 明确“买入/卖出”
- 收费荐股
- 收益承诺
- 自动生成投资建议

金融数据只能用于：

- 市场信息整理
- 公司公告摘要
- 宏观数据
- 行业变化
- 风险事件
- 新闻监控

如果未来做投资咨询相关业务，必须单独进行资质和合规评估。

---

# 17. 招聘 / 人才市场

海外：

- LinkedIn Jobs
- Indeed
- Glassdoor
- Wellfound
- Levels.fyi
- Remote OK
- We Work Remotely
- Hacker News Jobs

中国：

- BOSS直聘
- 拉勾
- 猎聘
- 智联招聘
- 前程无忧

招聘数据可以作为行业需求信号：

```text
某技能招聘数量快速增加
+
工资提高
+
大量公司同时招聘
=
产业需求增长信号
```

---

# 18. 网络 / 域名 / 基础设施

- Cloudflare Radar
- SecurityTrails
- Whois
- DomainTools

只使用合法授权的数据。

用途：

- 网站增长
- 新域名
- 网络趋势
- 技术生态变化

---

# 19. 网络安全

- CVE
- NVD
- CISA
- GitHub Security Advisories
- OWASP
- Exploit Database
- 各厂商官方 Security Blog

重点：

- 新漏洞
- 高危漏洞
- 软件供应链风险
- 云安全事件
- 新攻击趋势

只做防御性情报分析。

---

# 20. 播客 / Newsletter / Blog

海外：

- Spotify
- Apple Podcasts
- YouTube
- Substack
- Beehiiv
- Ghost
- Medium
- Buttondown

中国：

- 小宇宙
- 喜马拉雅
- 得到
- 蜻蜓 FM

优先使用：

- RSS
- 官方 API
- 官方公开页面

不要依赖未经授权的爬虫。

---

# 21. 聚合层

可以使用：

- RSSHub
- Feedly
- Inoreader
- Google News RSS
- Hacker News RSS
- Reddit RSS

注意：

**RSSHub 是技术聚合层，不是原始信息源。**

Source Registry 应同时记录：

```text
original_source
aggregation_source
```

方便追溯。

---

# 22. Source Registry

不要把数据源硬编码到 Collector。

应该建立统一配置：

```yaml
source_id:
name:
country:
category:
type:
url:
access_method:
api_endpoint:
rss_url:
legal_level:
update_frequency:
enabled:
priority:
```

示例：

```yaml
- source_id: hackernews
  name: Hacker News
  country: US
  category: developer
  type: community
  access_method: api
  url: https://news.ycombinator.com/
  legal_level: public
  update_frequency: realtime
  enabled: true
  priority: S

- source_id: gdelt
  name: GDELT
  country: global
  category: news
  type: dataset
  access_method: api
  url: https://www.gdeltproject.org/
  legal_level: public
  update_frequency: realtime
  enabled: true
  priority: S
```

---

# 23. 推荐数据模型

第一阶段只需要：

## sources

```text
id
source_id
name
category
country
type
url
access_method
api_endpoint
rss_url
legal_level
update_frequency
enabled
priority
created_at
updated_at
```

## raw_items

```text
id
source_id
external_id
url
title
content
published_at
collected_at
content_hash
metadata
```

## signals

```text
id
raw_item_ids
title
summary
why_it_matters
business_angle
category
importance
source_urls
published_at
created_at
```

## runs

```text
id
started_at
finished_at
source_count
raw_item_count
signal_count
status
error
```

---

# 24. AI 处理流程

不要让 AI 直接阅读所有数据并输出长报告。

采用：

```text
10000 raw items
      ↓
规则过滤
      ↓
URL / hash 去重
      ↓
相似内容聚类
      ↓
约 1000 items
      ↓
AI 判断是否有价值
      ↓
约 300 items
      ↓
趋势 / 影响分析
      ↓
约 50 items
      ↓
商业价值判断
      ↓
约 10~30 signals
      ↓
Feishu Daily Report
```

---

# 25. AI 判断字段

每条候选信息至少判断：

```json
{
  "keep": true,
  "category": "AI",
  "importance": "HIGH",
  "summary": "...",
  "why_it_matters": "...",
  "business_angle": "...",
  "confidence": 0.85
}
```

---

# 26. 商业价值分类

建议统一分类：

```text
AI
科技
创业
软件
开发者
电商
跨境电商
消费
内容
营销
广告
招聘
B2B
供应链
政策
金融市场
网络安全
科研
产品
基础设施
其他
```

---

# 27. Signal 的最终结构

示例：

```text
标题：
某 AI 公司推出新的低价 API

发生了什么：
公司宣布新的 API 定价，价格下降约 XX%。

为什么重要：
AI 推理成本进一步下降，可能改变 SaaS 产品成本结构。

商业角度：
对于个人开发者和 AI SaaS 创业者，这意味着原本无法盈利的 AI 功能可能开始具备商业可行性。

来源：
官方公告
TechCrunch
Hacker News
```

核心是：

> **事实 + 意义 + 行动方向**

而不是单纯摘要。

---

# 28. 飞书交付

MVP 不需要开发复杂前端。

直接：

```text
AI Opportunity Radar
├── 首页
├── 今日
├── 每日报告
└── 信息源
```

每日：

```text
AI Opportunity Radar
2026-XX-XX

🔥 今日重要信号

1. xxx
   - 发生了什么
   - 为什么重要
   - 商业角度
   - 来源

2. xxx
   ...

📊 今日趋势

AI：
★★★★★

跨境电商：
★★★★☆

创业：
★★★★
```

---

# 29. OpenClaw Bot 第一阶段

Bot 只保留：

```text
/today
/run
/status
/sources
/help
```

## /today

返回今日信号。

## /run

立即执行一次采集任务。

## /status

返回：

- 最近一次运行时间
- 数据源数量
- 成功数量
- 失败数量
- Raw Item 数
- Signal 数

## /sources

返回启用的数据源。

## /help

显示命令。

---

# 30. 第一阶段禁止做的事情

OpenClaw 不要自主扩张项目范围。

暂时禁止：

- 自建复杂前端
- SaaS 用户系统
- 用户权限系统
- 支付系统
- 订阅系统
- 激活码
- Paywall
- 订单系统
- 自动续费
- 内容创作平台
- 自动发布系统
- 多 Agent 复杂架构
- DeepResearch 大规模调用
- 向量数据库
- 复杂推荐系统
- 个性化推荐
- BI Dashboard
- 复杂评分模型
- 股票买卖推荐
- 收益预测
- 自动荐股
- 绕过网站反爬
- 绕过登录 / CAPTCHA
- 使用盗取 Cookie
- 未授权 API
- 抓取付费墙内容

---

# 31. 合规原则

所有采集必须满足：

```text
公开
+
合法
+
授权
+
可追溯
```

优先级：

```text
官方 API
>
官方 RSS
>
公开网页
>
授权数据服务
>
其他合法公开接口
```

每条 Signal 必须保存来源 URL。

不要直接复制整篇文章。

应该：

```text
原文
↓
AI 摘要
↓
自己的分析
↓
来源链接
```

---

# 32. 中国市场特别注意

尤其避免：

- 非法金融投资建议
- 荐股
- 收益承诺
- 个人敏感信息
- 未授权商业数据
- 侵权转载
- 绕过平台安全措施

金融方向第一阶段仅做：

> 市场信息 / 公司公告 / 宏观数据 / 行业趋势 / 风险事件

不做：

> 买什么 / 卖什么 / 什么时候买 / 什么时候卖。

---

# 33. OpenClaw 实施顺序

## Phase 1：Source Registry

建立统一数据源配置。

先录入 30 个核心 Source。

---

## Phase 2：Collector

实现统一 Collector 接口：

```python
class Collector:
    def collect(self) -> list[RawItem]:
        ...
```

不同数据源只负责：

```text
Source → RawItem
```

不要在 Collector 中写 AI 逻辑。

---

## Phase 3：Normalize

统一：

- title
- url
- published_at
- source
- content
- external_id

---

## Phase 4：Dedup

至少实现：

```text
URL 去重
Hash 去重
Title 相似度去重
```

---

## Phase 5：AI Filter

AI 判断：

```text
是否值得关注？
属于什么领域？
重要程度？
```

---

## Phase 6：Business Analysis

只对高价值内容执行：

```text
为什么重要？
影响谁？
有什么商业意义？
```

---

## Phase 7：Feishu

生成：

```text
每日机会雷达
```

---

## Phase 8：Bot

实现：

```text
/today
/run
/status
/sources
/help
```

---

## Phase 9：Scheduler

例如：

```text
每 30 分钟采集
每 2~4 小时分析
每天固定时间生成日报
```

频率不要一开始设置过高。

---

# 34. 第一阶段验收标准

OpenClaw 完成后必须可以做到：

### 数据

- [ ] 至少 30 个 Source 已登记
- [ ] 至少 10 个 Source 可以稳定采集
- [ ] 采集失败不会导致整个任务崩溃
- [ ] 每条数据可追溯来源

### AI

- [ ] 自动去重
- [ ] 自动分类
- [ ] 自动摘要
- [ ] 自动判断重要性
- [ ] 自动生成商业意义

### 输出

- [ ] 自动生成每日机会报告
- [ ] 写入飞书
- [ ] Bot 可以查询今日内容
- [ ] Bot 可以手动触发采集
- [ ] 可以查看运行状态

### 合规

- [ ] 不绕过登录
- [ ] 不绕过 CAPTCHA
- [ ] 不使用盗取 Cookie
- [ ] 不抓付费墙
- [ ] 不复制完整文章
- [ ] 每条 Signal 有来源
- [ ] 不提供非法投资建议

---

# 35. 最重要的产品原则

OpenClaw 以后开发任何功能，都先回答：

> **这个功能是否能够帮助用户更早发现一个值得行动的商业信号？**

如果不能：

```text
暂缓
```

如果只是：

```text
让系统看起来更复杂
```

也：

```text
暂缓
```

---

# 36. 最终 MVP

最终 MVP 应该非常简单：

```text
        国内外公开数据
               ↓
        Source Registry
               ↓
          Collector
               ↓
          Normalize
               ↓
            Dedup
               ↓
          AI Filter
               ↓
      Business Analysis
               ↓
       Commercial Signal
               ↓
         Feishu Docs
               ↓
          Feishu Bot
```

一句话定义：

> **AI Opportunity Radar 是一个持续监控国内外公开信息，并利用 AI 从海量信息中发现“值得行动的商业信号”的信息雷达系统。**

第一阶段的目标不是“接入全世界所有数据源”。

而是：

> **用最少的数据源，稳定地产生真正有价值的信号。**
