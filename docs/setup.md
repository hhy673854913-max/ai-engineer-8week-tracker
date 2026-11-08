# 环境准备

> 目标：30 分钟内拥有一个能跑通 `python code/week01/day01_md5.py` 的环境。
> 全程只需要 Python 3.11+、Git、一个模型 API Key。

## 1. Python 与包管理

推荐 **Python 3.12 + uv**（速度比 pip 快一个数量级，Day 01 会讲原理）。

```powershell
# Windows PowerShell 安装 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 校验
uv --version
uv python install 3.12
```

不想装 uv 也可以，`python -m venv .venv` + `pip` 完全等价，后文命令给出两种写法。

```powershell
# 方式一：uv（推荐）
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements/base.txt

# 方式二：venv + pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements/base.txt
```

后续按周追加：`rag.txt`（W3）、`agent.txt`（W5）、`api.txt`（W7）、`eval.txt`（W7）、`dev.txt`（随时）。

> macOS / Linux 把 `.\.venv\Scripts\Activate.ps1` 换成 `source .venv/bin/activate` 即可。

## 2. 申请模型 API Key

四个方案任选其一，代码通过 `.env` 切换，不改业务代码。

| 方案 | 适合 | 注册入口 | 备注 |
| --- | --- | --- | --- |
| DeepSeek | 起步首选，便宜 | platform.deepseek.com | `deepseek-chat` 足够跑完 W1-W6 |
| 阿里云百炼 | 需要视觉 + 嵌入 | bailian.console.aliyun.com | `qwen-vl-max`（Day 09）、`text-embedding-v3`（Day 11） |
| 智谱 GLM | 备选 | open.bigmodel.cn | 有免费额度 |
| Kimi / Moonshot | 长上下文、代码与 Agent 强 | platform.kimi.com | `kimi-k3.1-pro`（1M 上下文）；无 embedding 接口 |

四家都提供 **OpenAI 兼容接口**，所以代码里统一用 `openai` SDK + `base_url` 即可，这也是第 1 周要建立的认知：
**"模型厂商"是可替换的，你的工程封装才是资产。**

> Kimi 的两个差异已由 `code/shared/llm_client.py` 自动处理：K3.1 Pro 的 `temperature/top_p` 是固定值不能显式传，
> 输出上限字段叫 `max_completion_tokens`。另外 K2 系列已对新人关闭、年底下线，直接用 K3.1 系列即可。

**聊天和嵌入可以不是同一家。** Kimi、DeepSeek 都没有 embedding 接口，Day 11 要做真向量检索时，
单独配一段 `EMBED_*` 即可（例如聊天用 Kimi、嵌入用百炼）：

```ini
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_API_KEY=sk-你的百炼Key
EMBED_MODEL=qwen3.7-text-embedding
EMBED_DIMENSIONS=1024
```

代码优先读 `EMBED_*`，没配才回退到聊天配置；回退到不支持 embedding 的厂商时会给出明确提示。

## 3. 配置 `.env`

```powershell
Copy-Item .env.example .env
notepad .env   # 填入自己的 Key
```

`.env` 已在 `.gitignore` 里。**永远不要把 Key 提交到 Git**——这是本仓库的第一条红线，
Day 33 讲密钥管理时会再强调一次（泄露后的处理方式：立即吊销 + 重新签发，历史提交要清洗）。

## 4. 冒烟测试

```powershell
# 不需要 Key 的纯函数自测
python -m pytest tests -q

# 需要 Key 的第一行代码
python code/week01/day01_md5.py --help
```

## 5. 目录说明

```
├─ docs/            每日课程（week-01 … week-08）
├─ code/            每日实战代码
├─ logs/            每日学习留痕（打卡）
├─ scripts/         辅助脚本（打卡、生成日程表）
├─ requirements/    按月/周拆分的依赖
└─ tests/           纯函数单元测试（CI 可跑，不需要 Key）
```

## 6. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `SSL: CERTIFICATE_VERIFY_FAILED` | 公司代理 / 证书链 | 设 `HTTPS_PROXY`，或临时 `export SSL_CERT_FILE=...` |
| `429 Too Many Requests` | 触发限流 | 这正是 Day 03 要写的退避重试 |
| `insufficient_quota` | 欠费 / 免费额度用尽 | 换方案或充值 |
| `chromadb` 装不上 | 缺 C++ 编译环境 | 升级 pip；或改用 `faiss-cpu`/自写 numpy 向量库（Day 13 有实现） |
| 中文乱码（Windows） | 控制台默认 GBK | `chcp 65001`，或代码里 `sys.stdout.reconfigure(encoding="utf-8")` |
| PowerShell 禁止运行脚本 | 执行策略 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `python` 命令**没有任何输出**、`$LASTEXITCODE=9009` | 装的是应用商店占位符，机器上其实没有 Python | 见下面「Windows：python 命令静默失败」 |

### Windows：`python` 命令静默失败

症状：敲 `python -c "print('hi')"` 后命令行立刻回到提示符，**不报错也没输出**。

```powershell
where.exe python
# C:\Users\<你>\AppData\Local\Microsoft\WindowsApps\python.exe   ← 0 字节的商店占位符
python -c "print(1)"; $LASTEXITCODE   # 9009 = 命令不存在
```

处理三步：

```powershell
# 1) 装真 Python（已装可跳过）
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements

# 2) 重开一个 PowerShell 窗口，确认版本
python --version          # 期望 3.12.x

# 3) 建虚拟环境并装依赖（仓库根目录执行）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements/base.txt
```

重开窗口后仍指向 `WindowsApps` 的话，去「设置 → 应用 → 高级应用设置 → 应用执行别名」，
把 `python.exe` / `python3.exe` 两个开关关掉，再重开终端。

**每次开工先激活虚拟环境**，之后所有 `python` 命令都会用 `.venv` 里的解释器与依赖：

```powershell
cd C:\space\AI学习\ai-engineer-8week-tracker
.\.venv\Scripts\Activate.ps1
python -m pytest tests -q
```

不想激活也可以直接用全路径：`.\.venv\Scripts\python.exe -m pytest tests -q`。
