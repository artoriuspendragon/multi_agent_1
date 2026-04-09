# 私人消息流推送助手 - 产品需求说明（PRD）

| 项目 | 内容 |
|------|------|
| 文档标题 | 私人消息流推送助手 - 产品需求说明 |
| 版本 | v1.1 |
| 日期 | 2025-02-15 |
| 状态 | 待评审 |
| 角色 | 产品负责人（Product Owner） |
| 目标读者 | 下游开发 Agent、技术负责人、实现工程师 |

---

## 1. 背景与目标

### 1.1 业务/产品背景

用户需要一款部署在服务器上的**纯后端**应用，用于从多行业、多来源聚合信息，按个人偏好过滤后，整理成**早报**并推送到个人终端。该产品不提供 Web 前端，所有配置与运行均通过配置文件、环境变量或 CLI/API 完成。

### 1.2 要解决的问题

- **信息分散**：各行业信息分布在 RSS、官网、开放 API、第三方聚合等不同渠道，缺乏统一入口。
- **噪音过多**：原始信息流中大量内容与个人兴趣无关，需要可配置的过滤与排序。
- **触达方式单一或不便**：希望将「过滤后的早报」以稳定、可选的方式推送到本人（如邮件、手机推送、IM 等），并支持主流推送渠道。

### 1.3 目标与成功指标

| 目标 | 说明 | 可衡量标准 |
|------|------|-------------|
| 多源接入 | 支持 RSS/Atom、开放 API、爬虫等主流信息获取方式 | 至少支持 3 类来源，每类至少 1 种可配置实现 |
| 可配置过滤 | 根据用户口味过滤出有价值的内容，口味可配置、可演进 | 支持规则（关键词、标签、来源等）与 Agent 两种方式，可组合；配置变更无需改代码 |
| 早报生成与推送 | 将过滤结果整理成一份早报并推送 | 每日（或按配置周期）生成 1 份早报，并成功送达至少 1 个已配置的推送渠道 |
| 纯后端、可部署 | 无前端，适合服务器部署 | 无 Web UI 依赖，可通过配置 + 定时任务/API 独立运行 |

---

## 2. 用户与场景

### 2.1 目标用户

- **唯一用户**：产品拥有者本人（私人助手定位）。
- **使用方式**：通过修改配置文件或环境变量、执行 CLI/脚本或调用内部 API 来管理订阅源、过滤规则和推送设置。

### 2.2 典型使用场景

| 场景 | 描述 | 系统行为 |
|------|------|----------|
| 每日早报 | 每天早晨固定时间（如 7:00）拉取各源、过滤、生成早报并推送 | 定时任务触发拉取 → 过滤 → 聚合 → 生成早报 → 调用推送渠道 |
| 新增信息源 | 用户想增加某个博客的 RSS 或某新闻 API | 在配置中新增一条源（类型 + 地址/参数），下次拉取时自动包含 |
| 调整口味 | 用户对某类关键词不感兴趣或只想看某领域 | 修改过滤配置（关键词、标签、来源白名单等），下次早报即生效 |
| 更换推送方式 | 从邮件改为 Telegram 或 Bark | 修改推送配置（渠道类型 + 凭证/Webhook），早报改发至新渠道 |

### 2.3 用户故事（可选）

- 作为**个人用户**，我希望系统从 RSS、API 和指定网站拉取信息，以便在一个管道里看到多行业动态。
- 作为**个人用户**，我希望通过配置文件设置「包含/排除关键词、来源、标签」，或通过 Agent 按我的偏好描述做语义过滤，以便早报只包含我关心的内容。
- 作为**个人用户**，我希望早报既可以用固定模板生成，也可以用 Agent 做摘要重写、智能分组或润色，以便在保证结构稳定的同时提升可读性。
- 作为**个人用户**，我希望每天收到一份整理好的早报，并通过我选择的渠道（如邮件或 Telegram）送达，以便不打开多个 App 也能快速浏览。

---

## 3. 功能需求

### 3.1 功能总览与优先级

| 功能编号 | 功能名称 | 优先级 | 简述 |
|----------|----------|--------|------|
| F1 | 多源信息获取 | P0 | 支持 RSS/Atom、开放 API、爬虫等获取方式，可配置多源、定时拉取 |
| F2 | 可配置过滤与排序 | P0 | 支持规则过滤（关键词、标签、来源等）与 Agent 过滤两种方式，可组合；可配置排序 |
| F3 | 早报生成 | P0 | 支持模板聚合与 Agent 生成两种方式，将过滤结果整理成早报（标题、摘要、分类、链接等） |
| F4 | 多通道推送 | P0 | 支持邮件、Bark、Telegram、企业微信/钉钉等至少一种，可配置多通道 |
| F5 | 配置与运行模型 | P0 | 纯配置驱动（YAML/JSON + 环境变量），支持定时任务与可选 CLI/API |
| F6 | 去重与增量 | P1 | 同一篇文章在多源出现时去重；支持按时间/ID 增量拉取，避免重复推送 |
| F7 | 日志与可观测性 | P1 | 拉取/过滤/推送各阶段可日志记录，便于排查与监控 |

以下对 F1～F5 做详细说明；F6、F7 在 3.2 中给出要点，验收标准见第 7 节。

### 3.2 功能详细说明

#### F1：多源信息获取

**功能描述**  
系统从多种类型的「信息源」拉取原始条目（标题、链接、摘要、发布时间、来源等）。支持的来源类型至少包括：**RSS/Atom**、**开放 API**、**网页爬虫**（或类似抓取）。每种类型可配置多个源，拉取任务可按 cron 或固定间隔执行。

**信息获取方式调研结论（供实现参考）**

| 方式 | 说明 | 典型实现要点 | 适用场景 |
|------|------|--------------|----------|
| **RSS / Atom** | 标准化的 XML 订阅流，行业通用 | 使用 feedparser 等解析 URL；支持 RSS 0.9x/2.0、Atom 1.0 | 博客、多数科技/财经媒体、部分新闻站 |
| **开放 API** | 第三方提供的 HTTP API（如新闻聚合、天气、GitHub 动态） | 按文档调用 REST API，解析 JSON/XML；需支持 API Key 等鉴权配置 | 今日头条热点、百度热点、GitHub 动态、天气/日历等 |
| **爬虫/抓取** | 对无 RSS/API 的页面做定向抓取与解析 | 使用 requests + BeautifulSoup/parsel 或 Scrapy 等；需遵守 robots.txt 与站点条款 | 特定官网、论坛、无开放接口的新闻页 |

**输入**

- **配置**：信息源列表。每条记录建议包含：
  - `id`：唯一标识。
  - `type`：`rss` | `api` | `crawler`。
  - `url` 或 `endpoint`：RSS 地址 / API 地址 / 爬虫目标 URL。
  - 可选：`name`、`params`（如 API 的 query）、`headers`（如 API Key）、爬虫选择器或规则引用等。

**输出**

- 统一结构的**原始条目列表**（见 6.1 数据实体）。每条需包含：`title`、`link`、`summary`（或 `description`）、`published_at`（时间，可选）、`source_id`、`raw_id`（如 RSS 的 guid）等，便于去重与过滤。

**规则与边界**

- 单次拉取超时、并发数、单源条数上限建议可配置，避免阻塞或过载。
- 拉取失败（网络错误、4xx/5xx）时记录日志并可配置重试；单源失败不应导致整次早报任务失败。

**异常与错误处理**

- 某源超时或返回错误：记录该源错误日志，跳过该源，继续其他源。
- 解析失败（如非标准 RSS）：记录解析错误，跳过该条或该源，不崩溃。

---

#### F2：可配置过滤与排序

**功能描述**  
根据用户「口味」对原始条目进行过滤与排序，仅保留对用户有价值的内容。系统支持两种过滤方式，可单独或组合使用：

1. **规则过滤**：基于关键词、标签、来源、时间等可配置规则进行过滤与排序。
2. **Agent 过滤**：调用外部 LLM/Agent，根据用户偏好描述对条目进行语义筛选、打分或排序。

过滤策略与规则**全部可配置**，不写死在代码中。

**过滤策略（strategy）**

| 策略值 | 说明 | 适用场景 |
|--------|------|----------|
| `rule` | 仅使用规则（关键词、来源、时间等）过滤与排序 | 口味稳定、规则明确 |
| `agent` | 仅使用 Agent：将条目与用户偏好交给 LLM，由 Agent 返回保留的条目或打分排序 | 口味复杂、需语义理解 |
| `rule_then_agent` | 先执行规则过滤，再对剩余条目执行 Agent 过滤（推荐，可控制调用成本） | 规则粗筛 + 语义精筛 |

**规则过滤：建议支持的配置项（可分批实现）**

| 配置类 | 说明 | 示例 |
|--------|------|------|
| 关键词包含（白名单） | 标题或摘要包含某关键词则保留 | `include_keywords: ["AI", "大模型"]` |
| 关键词排除（黑名单） | 标题或摘要包含某词则丢弃 | `exclude_keywords: ["八卦", "广告"]` |
| 来源白名单 | 只保留来自某几个 source_id 的条目 | `allowed_sources: ["rss-tech", "api-news"]` |
| 来源黑名单 | 排除某几个来源 | `blocked_sources: ["spam-feed"]` |
| 时间范围 | 只保留过去 N 小时/天内的条目 | `max_age_hours: 24` |
| 排序 | 按时间、相关性（关键词匹配度）等 | `sort_by: published_at`，`order: desc` |

**Agent 过滤：接口契约与配置**

- **输入（传给 Agent）**：  
  - 原始或经规则过滤后的 **RawItem 列表**（每条约目的 id、title、link、summary、source_id、published_at 等）。  
  - **用户偏好描述**（由配置提供，如「我关注 AI、创业、产品；不关心娱乐八卦、营销软文」）。  
  - 可选：本次条目的数量上限或截断说明（便于控制 prompt 长度）。
- **输出（Agent 必须返回）**：  
  - **方案 A**：保留的条目的 `id` 列表（推荐，简单可靠）。  
  - **方案 B**：每条目的 `id` +  relevance_score，由系统按分数排序后截断。  
  - 返回格式须约定为结构化 JSON（如 `{"keep_ids": ["id1", "id2"]}` 或 `{"scored": [{"id":"id1","score":0.9}]}`），便于解析与 fallback。
- **配置建议**：  
  - `filter.strategy`：`rule` | `agent` | `rule_then_agent`。  
  - `filter.agent`（当 strategy 含 agent 时必填）：  
    - `provider` / `endpoint`：兼容 OpenAI API 的 chat 接口或自建模型端点。  
    - `api_key`：通过环境变量注入，如 `"${FILTER_AGENT_API_KEY}"`。  
    - `model`：模型名称。  
    - `user_preference`：用户口味的一段话，会注入到 system 或 user prompt。  
    - `prompt_template`：可选，用于构造 system/user 消息的模板（占位符如 `{{items_json}}`、`{{user_preference}}`）。  
    - `timeout_seconds`、`max_items_per_call`：单次调用条数上限与超时，防止 token 超限或长时间阻塞。
- **失败与回退**：Agent 调用超时、返回非 JSON 或格式错误时，记录日志并执行 **fallback**：若为 `rule_then_agent` 则使用规则过滤结果作为最终结果；若为 `agent` 则回退为「全部保留」或可配置的默认行为（如仅保留前 N 条）。

**输入**

- 原始条目列表（F1 输出）。
- 过滤与排序配置（strategy、规则项、Agent 配置等，来自配置文件或环境变量）。

**输出**

- 过滤并排序后的**条目列表**（结构同 6.1，仅条数减少、顺序改变）。

**规则与边界**

- 规则过滤建议支持「与/或」组合（如：必须来自白名单来源 **且** 不在黑名单关键词中）。具体组合方式可在实现时用表达式或简单 DSL 定义。
- 若所有条目均被过滤掉，早报为空，仍可生成「今日无匹配内容」的早报并推送（行为可配置）。
- Agent 过滤时，单次传入的条目数建议可配置上限，超出时可分批调用再合并结果。

**异常与错误处理**

- 配置缺失或格式错误：启动或拉取时校验并报错，给出明确提示，不静默忽略。
- Agent 不可用或返回异常：按上文「失败与回退」执行，并记录详细日志。

---

#### F3：早报生成

**功能描述**  
将过滤后的条目聚合成**一份早报**，包含固定结构：标题、生成时间、按分类或来源分组的条目列表（每条含标题、摘要、链接等），并渲染为适合推送的格式（纯文本、Markdown、HTML）。系统支持两种生成方式，可单独或组合使用：

1. **模板生成**：按配置的标题模板、分组方式、条数上限等，将条目填入选定模板生成早报。
2. **Agent 生成**：调用外部 LLM/Agent，根据条目列表与可选约束生成早报标题、分组与正文（可含摘要重写、重点提炼等）。

**生成策略（strategy）**

| 策略值 | 说明 | 适用场景 |
|--------|------|----------|
| `template` | 仅使用模板：固定结构 + 占位符填充 | 格式固定、无需语义润色 |
| `agent` | 仅使用 Agent：将条目列表交给 LLM，由 Agent 直接输出早报结构或已渲染文本 | 需要摘要重写、个性化表述、智能分组 |
| `template_then_agent` | 先用模板生成草稿，再交给 Agent 润色（如精简、改语气、加导读） | 保证结构稳定同时提升可读性 |

**模板生成：配置项**

- 标题模板、是否按来源/标签分组、单条最大长度、总条数上限等（与现有 6.2 中 digest 配置一致）。

**Agent 生成：接口契约与配置**

- **输入（传给 Agent）**：  
  - 过滤并排序后的 **条目列表**（每条约目的 title、link、summary、source_id、published_at 等，可截断 summary 长度以控制 token）。  
  - 可选：**早报约束**（如「标题格式：每日早报 YYYY-MM-DD」「分组按来源」「总字数不超过 2000」）。  
  - 可选：期望输出格式说明（如「请输出 JSON：{ title, sections: [{ name, items: [{ title, summary, link }] }] }」或「请直接输出 Markdown 正文」）。
- **输出（Agent 必须返回）**：  
  - **方案 A（结构化）**：符合 Digest 语义的 JSON（含 `title`、`generated_at`、`sections`，以及可选的 `rendered.markdown` / `rendered.html`）。系统可据此再渲染为各渠道格式。  
  - **方案 B（直接渲染）**：Agent 直接返回已渲染的早报文本（如 Markdown 或 HTML），系统将其填入 `Digest.rendered`，title 可由系统补全。  
  - 返回格式须约定明确（JSON schema 或示例），便于解析与 fallback。
- **配置建议**：  
  - `digest.strategy`：`template` | `agent` | `template_then_agent`。  
  - `digest.agent`（当 strategy 含 agent 时必填）：  
    - `provider` / `endpoint`、`api_key`、`model`：与过滤 Agent 类似，通过环境变量注入密钥。  
    - `constraints`：一段文字描述早报格式与长度要求，注入到 prompt。  
    - `prompt_template`：可选，用于构造 system/user 消息（占位符如 `{{items_json}}`、`{{constraints}}`、`{{date}}`）。  
    - `output_format`：`structured`（返回 JSON）或 `rendered`（返回 Markdown/HTML 字符串）。  
    - `timeout_seconds`、`max_input_items`：单次传入条目数上限与超时。
- **失败与回退**：Agent 调用超时、返回无法解析或格式错误时，记录日志并执行 **fallback**：若为 `template_then_agent` 则使用模板生成的草稿作为最终早报；若为 `agent` 则回退为**模板生成**（需提供默认模板或从配置读取）。

**输入**

- 过滤并排序后的条目列表（F2 输出）。
- 早报配置：strategy、模板项、Agent 配置等（来自配置文件或环境变量）。

**输出**

- **早报实体**（见 6.2）：至少包含：
  - `title`：早报标题（如「每日早报 YYYY-MM-DD」）。
  - `generated_at`：生成时间（ISO8601）。
  - `sections`：分组列表，每组有分组名 + 条目列表。
  - `rendered`：按渠道需要的格式渲染后的字符串（如 `text`、`markdown`、`html`）。

**规则与边界**

- 早报总长度需适配各推送渠道（如邮件无硬限制，Bark/Telegram 有单条长度限制），可配置截断或分条推送策略。
- 若无条目，可生成「今日无新内容」的占位早报（是否推送可配置）；Agent 生成时也可在 prompt 中约定「无条目时返回简短占位文案」。
- Agent 生成时，传入条目数建议有上限，避免单次 token 过多；可要求 Agent 只输出前 N 条或摘要版。

**异常与错误处理**

- 配置缺失或格式错误：启动或生成时校验并报错。
- Agent 不可用或返回异常：按上文「失败与回退」执行，并记录详细日志。

---

#### F4：多通道推送

**功能描述**  
将生成的早报通过用户配置的**推送渠道**发送给用户。系统应支持多种渠道类型，每种渠道通过配置启用并填写必要凭证。

**推送方式调研结论（供实现参考）**

| 渠道 | 说明 | 典型实现方式 | 适用场景 |
|------|------|--------------|----------|
| **邮件 (SMTP)** | 发送 HTML/纯文本邮件到指定邮箱 | SMTP 发信，支持 TLS、用户名密码或 App 密码 | 早报篇幅大、需在邮箱中留存 |
| **Bark** | iOS 设备推送，支持自建服务 | HTTP GET/POST 到 `/:key/:title/:body` 等形式 | 手机端即时提醒、内容不宜过长 |
| **Telegram** | 私聊/群组/频道推送 | Bot API `sendMessage`（支持 Markdown/HTML） | 跨平台、支持较长内容与分组 |
| **企业微信 / 钉钉** | 群机器人或应用消息 | Webhook URL，POST JSON（Markdown 或文本） | 国内办公场景、群内推送 |
| **Server 酱 / 类似服务** | 第三方「微信/邮件」推送聚合 | 调用其 HTTP API，传入 title + content | 快速接入，依赖第三方 |

**输入**

- 早报实体（F3 输出），以及各渠道所需的格式（如 Bark 用短文本，邮件用 HTML）。
- 推送配置：启用的渠道列表，每个渠道的 type + 凭证（如 SMTP 账号、Bark key、Telegram bot token + chat_id、Webhook URL）。

**输出**

- 各渠道发送结果：成功/失败 + 若有错误则记录原因（如 4xx/5xx、网络超时）。

**规则与边界**

- 某渠道发送失败不应影响其他渠道（例如邮件失败仍尝试 Bark）。
- 敏感凭证（API Key、密码、Token）必须通过环境变量或独立密钥配置注入，**不得**写死在代码或提交到仓库的配置文件中。

**异常与错误处理**

- 网络超时、认证失败、限流：记录日志并标记该渠道失败，可选重试（次数可配置）。

---

#### F5：配置与运行模型

**功能描述**  
项目为**纯后端**，无前端页面。所有行为由**配置文件**（如 YAML 或 JSON）与**环境变量**驱动。运行方式包括：**定时任务**（cron 或内置调度）每日生成并推送早报；可选 **CLI** 或 **HTTP API** 用于手动触发一次拉取/生成/推送或查看状态。

**输入**

- 配置文件路径（或默认路径）；环境变量（如 `CONFIG_PATH`、各渠道的密钥等）。

**输出**

- 定时任务：无直接用户可见输出，仅日志与推送结果。
- CLI/API：执行结果（成功/失败、早报条数、推送结果摘要等）。

**规则与边界**

- 配置需有清晰 schema 或注释，便于人类与 AI 理解和修改。
- 建议配置分层：信息源列表、过滤规则、早报模板、推送渠道，便于下游 Agent 按模块实现与测试。

---

#### F6：去重与增量（P1）

- **去重**：同一篇文章（通过 `link` 或 `raw_id` 归一化）在多源出现时只保留一条。
- **增量**：拉取时可根据 `published_at` 或 `raw_id` 只处理新条目，避免重复推送；持久化存储（如 SQLite/文件）可选，由实现决定。

#### F7：日志与可观测性（P1）

- 拉取开始/结束、每源条数、过滤前后条数、推送各渠道结果，均建议打日志（级别可配置）。
- 可选：简单 metrics（如拉取耗时、早报条数）便于监控。

---

## 4. 非功能需求

| 类型 | 要求 |
|------|------|
| **性能** | 单次全量拉取 + 过滤 + 生成 + 推送，在源数量与条数合理范围内（如 20 源、单源 50 条）应在数分钟内完成；单源超时建议可配置（如 30s）。 |
| **安全** | 密钥、Token、密码仅通过环境变量或安全配置注入；不记录敏感信息到日志。 |
| **可用性** | 单源或单渠道失败不导致整体任务失败；支持重试与降级（如只推邮件不推 Bark）。 |
| **兼容性** | 运行环境建议明确（如 Python 3.10+），依赖版本在 requirements.txt 或 pyproject.toml 中固定。 |
| **合规与礼貌** | 爬虫需遵守目标站 robots.txt 与使用条款；拉取频率不宜过高，避免对第三方造成压力。 |
| **Agent 调用** | 过滤/生成 Agent 的调用需设置超时与条数上限，避免长时间阻塞；API Key 等凭证仅通过环境变量注入；实现方可根据需要做限流或成本控制（如选用更小模型、减少单次 token）。 |

---

## 5. 界面与交互

- **无前端**：不提供 Web UI。配置通过编辑配置文件与设置环境变量完成；若提供 CLI，可支持「校验配置」「试跑一次」等子命令，便于人类与 AI 验证。
- **可选 API**：若提供 HTTP API，建议仅用于内部或本地（如 `POST /v1/digest/run` 触发一次早报），无需对外鉴权文档化即可；若需鉴权，由实现方在技术方案中说明。

---

## 6. 数据与接口

### 6.1 核心数据实体（供实现参考）

**RawItem（原始条目）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 内部唯一 ID（可由 source_id + raw_id 生成） |
| source_id | string | 对应配置中的信息源 id |
| raw_id | string | 源侧唯一标识（如 RSS guid、API 返回的 id） |
| title | string | 标题 |
| link | string | 原文链接 |
| summary | string | 摘要/描述（可选） |
| published_at | datetime (ISO8601) 或 null | 发布时间 |
| extra | object | 扩展字段（如 tags、author） |

**Digest（早报）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 早报唯一 ID（如 uuid 或 日期） |
| title | string | 早报标题 |
| generated_at | string | ISO8601 时间 |
| sections | list | 分组列表，每项：{ name, items: [ RawItem 子集 ] } |
| rendered | object | { text?, markdown?, html? } 按需渲染 |

### 6.2 配置结构建议（示意）

以下为 YAML 示意，便于 AI 与人类理解；实际实现可采用 JSON 或兼容结构。

```yaml
# 信息源
sources:
  - id: rss-tech
    type: rss
    url: https://example.com/feed.xml
    name: "某科技博客"
  - id: api-news
    type: api
    endpoint: https://api.example.com/news
    headers: { "X-API-Key": "${NEWS_API_KEY}" }

# 过滤（支持规则 + Agent 两种方式，strategy 决定组合）
filter:
  strategy: rule_then_agent   # rule | agent | rule_then_agent
  # 规则过滤（strategy 为 rule 或 rule_then_agent 时生效）
  include_keywords: []
  exclude_keywords: ["广告"]
  allowed_sources: []
  blocked_sources: []
  max_age_hours: 24
  sort_by: published_at
  order: desc
  # Agent 过滤（strategy 含 agent 时必填）
  agent:
    endpoint: "https://api.openai.com/v1/chat/completions"
    api_key: "${FILTER_AGENT_API_KEY}"
    model: "gpt-4o-mini"
    user_preference: "我关注 AI、创业、产品；不关心娱乐八卦、营销软文"
    timeout_seconds: 60
    max_items_per_call: 100
    # prompt_template 可选，默认由实现方构造

# 早报（支持模板 + Agent 两种方式，strategy 决定组合）
digest:
  strategy: agent   # template | agent | template_then_agent
  # 模板生成（strategy 为 template 或 template_then_agent 时生效）
  title_template: "每日早报 {{date}}"
  max_items: 50
  group_by: source   # 或 tag / none
  # Agent 生成（strategy 含 agent 时必填）
  agent:
    endpoint: "https://api.openai.com/v1/chat/completions"
    api_key: "${DIGEST_AGENT_API_KEY}"
    model: "gpt-4o"
    constraints: "标题格式：每日早报 YYYY-MM-DD；按来源分组；总字数不超过 2000 字"
    output_format: structured   # structured | rendered
    timeout_seconds: 120
    max_input_items: 50

# 推送
push:
  channels:
    - type: email
      enabled: true
      smtp_host: smtp.example.com
      smtp_user: "${SMTP_USER}"
      smtp_password: "${SMTP_PASSWORD}"
      to: "me@example.com"
    - type: bark
      enabled: true
      base_url: "https://api.day.app"
      key: "${BARK_KEY}"
```

环境变量占位符（如 `${BARK_KEY}`）在加载配置时替换，实现时需约定规则。

### 6.3 与下游的接口约定

- **模块边界建议**：  
  - **采集层**：按 source type 调用对应 Fetcher（RSS Fetcher、API Fetcher、Crawler Fetcher），输出统一 RawItem 列表。  
  - **过滤层**：输入 RawItem 列表 + filter 配置；若 strategy 含规则则先执行规则过滤，若含 agent 则调用过滤 Agent（输入：条目 + user_preference，输出：保留 id 列表或打分列表），最终输出过滤并排序后的列表。  
  - **早报层**：输入过滤后列表 + digest 配置；若 strategy 为 template 则按模板生成 Digest，若含 agent 则调用生成 Agent（输入：条目 + constraints，输出：Digest JSON 或已渲染文本），失败时按 PRD 约定回退。  
  - **推送层**：输入 Digest + push 配置，按渠道渲染并发送。
- 下游 Agent 可实现为多语言（如 Python）或拆分为多个服务，只要满足上述数据实体、过滤/生成策略与 Agent 接口约定即可对接。

---

## 7. 验收标准

| 编号 | 功能/Epic | 验收条件 |
|------|-----------|----------|
| AC1 | F1 多源获取 | 配置至少 1 个 RSS、1 个 API 源后，能成功拉取并解析出 RawItem 列表；RSS 使用标准 feedparser 或等价实现。 |
| AC2 | F2 过滤（规则） | 配置关键词黑名单后，包含该关键词的条目不出现在过滤结果中；配置来源白名单后，仅白名单来源的条目保留。 |
| AC2b | F2 过滤（Agent） | 当 filter.strategy 为 agent 或 rule_then_agent 且配置了 filter.agent 时，能调用 Agent 并得到保留的条目 id 列表或打分列表；Agent 超时/失败时按文档约定执行 fallback 并打日志。 |
| AC3 | F3 早报（模板） | 当 digest.strategy 为 template 时，过滤结果能按模板生成包含 title、generated_at、sections 的 Digest，并至少输出一种 rendered 格式（如 markdown）。 |
| AC3b | F3 早报（Agent） | 当 digest.strategy 为 agent 或 template_then_agent 且配置了 digest.agent 时，能调用 Agent 并得到符合 Digest 结构的早报或已渲染文本；Agent 超时/失败时按文档约定回退到模板并打日志。 |
| AC4 | F4 推送 | 配置一种推送渠道（如邮件或 Bark）并填入有效凭证后，能成功发送一次早报；失败时日志中有明确错误信息。 |
| AC5 | F5 运行 | 通过配置文件 + 环境变量能完成全流程（拉取→过滤→早报→推送）；支持通过 cron 或内置调度在指定时间触发。 |
| AC6 | F6 去重 | 同一 link 或 raw_id 在多源出现时，早报中只出现一次。 |
| AC7 | F7 日志 | 一次完整运行中，拉取、过滤、推送各阶段有可区分的日志输出。 |

---

## 8. 范围与排除

| 范围 | 说明 |
|------|------|
| **本期不做** | 任何 Web 前端、用户注册/登录、多用户支持；不提供官方公开 SaaS 服务。 |
| **不做** | 对无 robots.txt 或无授权页面的激进爬虫；不支持需要图形验证码或强反爬的站点作为默认能力。 |
| **可选** | 管理端 API、Dashboard、多用户等均为后续扩展，不在本 PRD 承诺范围内。 |

---

## 附录 A：术语表

| 术语 | 定义 |
|------|------|
| 早报 | 将多源拉取并过滤后的条目，按模板或 Agent 聚合而成的单份日报/周期报。 |
| 信息源 (Source) | 单一 RSS/API/爬虫目标，对应配置中的一条 source。 |
| 推送渠道 (Channel) | 一种送达方式，如邮件、Bark、Telegram、企业微信、钉钉等。 |
| RawItem | 从任意信息源解析得到的统一结构的条目。 |
| Digest | 聚合后的早报对象，包含标题、时间、分组条目及渲染结果。 |
| 过滤策略 (filter.strategy) | 过滤方式：rule（仅规则）、agent（仅 Agent）、rule_then_agent（先规则后 Agent）。 |
| 生成策略 (digest.strategy) | 早报生成方式：template（仅模板）、agent（仅 Agent）、template_then_agent（先模板后 Agent 润色）。 |
| 过滤 Agent / 生成 Agent | 通过调用外部 LLM/API，对条目进行语义过滤或对早报进行生成/润色的逻辑模块；输入输出见 F2、F3 的 Agent 接口契约。 |

---

## 附录 B：参考与变更记录

- **参考**：RSS/Atom 解析（如 feedparser）；Bark API、Telegram Bot API、SMTP、企业微信/钉钉 Webhook 的官方文档。
- **变更记录**：v1.0 初稿，覆盖多源获取、可配置过滤、早报生成、多通道推送及纯后端运行模型。v1.1 增加基于 Agent 的过滤与早报生成：过滤支持 rule / agent / rule_then_agent，早报支持 template / agent / template_then_agent，并约定 Agent 输入输出、配置项与失败回退。

---

**文档结束。建议后续步骤**：与技术负责人/开发 Agent 评审本 PRD；按 F1～F5 拆分为迭代任务；确定技术栈与仓库结构后开始实现；配置与数据实体可按实现语言做细微调整，但需与本文档保持一致语义。**
