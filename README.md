# 私人消息流推送助手（后端）

一个部署在服务器上的纯后端项目：从多源拉取信息，过滤后生成早报并推送。

当前代码已实现：
- `models` / `config`
- `sources`（`rss` / `api` / `crawler`）
- `dedup`
- `filter`（`rule`）
- `digest`（`template`）
- `push`（`email` / `bark`）
- `pipeline`（全链路编排）

---

## 1. 环境要求

- Python `>= 3.9`
- 推荐使用虚拟环境（`venv`）

---

## 2. 安装依赖

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你要跑测试，再安装：

```bash
pip install pytest
```

---

## 3. 配置文件

1) 复制示例配置：

```bash
cp config.yaml.example config.yaml
```

2) 按你的实际信息修改 `config.yaml`（至少改这些）：
- `sources`：换成真实 RSS/API/网页地址
- `push.channels`：保留你要用的渠道（email/bark）

3) 设置环境变量（配置里用了 `${VAR}` 占位符）：

```bash
export SMTP_USER="your_smtp_user"
export SMTP_PASSWORD="your_smtp_password"
export BARK_KEY="your_bark_key"
export NEWS_API_KEY="your_news_api_key"
export GITHUB_TOKEN="your_github_pat"
export SEMANTIC_SCHOLAR_API_KEY="your_semantic_scholar_key"   # 可选
```

> 未使用的变量可以不设置；只要对应配置里不启用即可。

---

## 4. 启动项目（手动跑一次）

当前还没接 CLI 命令，先用一段 Python 启动全流程：

```bash
PYTHONPATH=src python3 - <<'PY'
from app import load_config, run

cfg = load_config("config.yaml")
result = run(cfg)

print("ok:", result.ok)
print("steps:", result.steps_completed)
print("raw_count:", result.raw_count)
print("dedup_count:", result.dedup_count)
print("filtered_count:", result.filtered_count)
print("push_success_count:", result.push_success_count)
print("errors:", result.errors)

if result.digest:
    print("digest_title:", result.digest.title)
PY
```

如果你喜欢用环境变量指定配置路径：

```bash
export CONFIG_PATH=/absolute/path/to/config.yaml
PYTHONPATH=src python3 - <<'PY'
from app import load_config, run
cfg = load_config()  # 会读取 CONFIG_PATH
print(run(cfg))
PY
```

---

## 5. 定时运行（服务器）

可先用 cron 定时触发（例如每天早上 7:00）：

```bash
0 7 * * * cd /path/to/multi_agent_1 && /path/to/.venv/bin/python3 - <<'PY'
from app import load_config, run
cfg = load_config("config.yaml")
res = run(cfg)
print(res.ok, res.errors)
PY
```

---

## 6. 运行测试

```bash
PYTHONPATH=src python3 -m pytest tests -v
```

如需验证 arXiv 线上真实数据（集成测试）：

```bash
RUN_LIVE_ARXIV_TEST=1 PYTHONPATH=src python3 -m pytest tests/test_arxiv_live.py -v
```

---

## 7. 当前未完成项（已知）

- `filter.agent`（当前是占位，调用会 `NotImplementedError`）
- `digest.agent` / `template_then_agent`（当前占位）
- `scheduler`、`cli`、`api` 入口文件尚未实现
- 仅实现了 `push.email` 与 `push.bark`，其他渠道待补充

---

## 8. 常见问题

- **`ModuleNotFoundError: app`**  
  运行命令前加 `PYTHONPATH=src`，或做 editable install（`pip install -e .`）。

- **配置加载失败 (`ConfigLoadError`)**  
  先检查 `config.yaml` 语法，再检查策略必填项：  
  - `filter.strategy=agent/rule_then_agent` 时必须配置 `filter.agent`  
  - `digest.strategy=agent/template_then_agent` 时必须配置 `digest.agent`

- **推送失败**  
  优先检查对应渠道配置和环境变量是否正确（SMTP host/账号密码、Bark key 等）。
