# Day 35 · Docker 化、部署与降本实验

> W7 · 周五 ｜ 5h ｜ 产出 `code/week07/api/Dockerfile` + 公网 demo + 降本数据 ｜ [Day 34](day-34.md) ｜ **本周里程碑**

**今日目标**
- 用 Docker 把服务打包，做到"一条命令在任意机器跑起来"
- 部署到一台公网可访问的机器（云服务器 / 函数计算 / 隧道都行）
- 做一次真实的降本实验：模型分级 + 语义缓存，记录成本与质量变化

**验收**：公网 URL 可访问且能流式问答；降本实验有前后对比数据。

---

## 上午 09:00–11:30 · 理论

### 1. 镜像的四个原则

| 原则 | 做法 | 收益 |
| --- | --- | --- |
| 小 | 用 `python:3.12-slim`，多阶段构建 | 拉取快、攻击面小 |
| 可复现 | 锁定依赖版本 | 今天能跑，半年后也能跑 |
| 无状态 | 数据挂卷，配置用环境变量 | 可水平扩展 |
| 非 root | `USER app` | 安全基线 |

表里"多阶段构建"这个词值得单独解释：多阶段构建是把"装依赖 / 编译"和"运行时"拆成两个 FROM：第一个阶段（builder）里装 gcc 和需要编译的包，第二个阶段只 `COPY --from=builder /usr/local/lib/python3.12/site-packages` 加上你的代码，最终镜像里没有编译器、也没有 apt 缓存，体积和攻击面一起降下来。任务 1 这份依赖全是纯 Python 包，单阶段就够，所以只写了一个 `AS base`；等你把 `faiss-cpu`、`onnxruntime` 装进镜像时再加第二个阶段。

### 2. 环境变量与密钥

```text
❌ 把 Key 写进 Dockerfile 或镜像
✅ 运行时注入：docker run --env-file .env
```

生产环境用平台的 Secret 管理（K8s Secret、云厂商密钥服务）。
**镜像一旦推到公共仓库，里面的 Key 就等于泄露**——这是最常见的安全事故。

### 3. 部署选项对比

| 方案 | 成本 | 适合 | 注意 |
| --- | --- | --- | --- |
| 云服务器 + docker compose | ¥30–60/月 | 长期 demo、作品集 | 要自己管证书/防火墙 |
| 函数计算（FC / Lambda） | 按量，便宜 | 低流量 | 冷启动、SSE 支持有限 |
| Railway / Render / Fly.io | 免费额度 | 海外 demo | 国内访问慢 |
| 内网穿透（frp / ngrok） | 免费 | 临时演示 | 不稳定，不适合放简历 |

**作品集优先"能长期访问"**：一台 2 核 2G 的轻量服务器足够。

### 4. 降本两板斧

**板斧一：模型分级**

| 任务 | 模型 | 理由 |
| --- | --- | --- |
| 查询改写 | 小模型（qwen-turbo / deepseek-chat） | 任务简单 |
| 最终生成 | 大模型（qwen-plus / deepseek-chat） | 质量关键 |
| 评估 judge | 固定中档模型 | 保证可比 |

**板斧二：语义缓存**

```python
def cache_key(question: str, top_k: int) -> str:
    return hashlib.sha256(f"{normalize(question)}|{top_k}".encode()).hexdigest()
```

两级缓存：
- 精确缓存：同问题直接命中（省钱 100%）
- 语义缓存：embedding 相似度 > 0.95 视为同一问题（省 60–80%，但有答错风险）

**语义缓存的风险**：两个问法相似但答案不同（"春节奖励"vs"春节报名"），会返回错误答案。
对策：只在"高频、低风险"的问题上开；或者缓存后仍然做一次轻量校验。

### 5. 观测部署是否健康

```bash
curl -s https://your-domain/healthz
curl -N -X POST https://your-domain/api/query -H 'Content-Type: application/json' \
     -d '{"question":"奖励什么时候发"}'
```

`-N` 关闭缓冲，才能看到流式。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 写 Dockerfile（50 min）

```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install -r requirements/base.txt -r requirements/api.txt

COPY code/ ./code/
COPY data/ ./data/
COPY config.yaml ./

RUN useradd -m app && chown -R app:app /app
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "code.week07.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

注意 `PYTHONUNBUFFERED=1`：不加的话日志会在缓冲里，容器崩了看不到最后几行。

### 任务 2 · 本地跑通 compose（40 min）

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    volumes: ["./chroma_db:/app/chroma_db"]
    restart: unless-stopped
```

```powershell
docker compose up --build
curl http://localhost:8000/healthz
```

### 任务 3 · 部署（60 min）

按你的条件选一条：
- 云服务器：`scp` 代码 + `docker compose up -d`，配 Nginx 反代 + HTTPS（certbot）
- 平台：推镜像到镜像仓库，在平台创建服务

**Nginx 关键配置**（SSE 必须）：

```nginx
location /api/query {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_set_header X-Accel-Buffering no;
}
```

### 任务 4 · 降本实验（50 min）

跑同一批 30 个问题，对比三组：

| 配置 | 平均延迟 | 平均成本 | Faithfulness | 拒答正确率 |
| --- | --- | --- | --- | --- |
| 全用大模型 | | | | |
| 分级（改写走小模型） | | | | |
| 分级 + 精确缓存 | | | | |
| 分级 + 语义缓存（0.95） | | | | |

**结论要写成一句话**，例如："分级 + 精确缓存省 38%，Faithfulness 不变；语义缓存再省 22%，但出现 2 例错答，不建议默认开启。"

这就是面试时"你如何控制成本"的标准答案。

---

## 代码思考（写进 `logs/day-35.md`）

1. 为什么 `PYTHONUNBUFFERED=1` 对容器日志是必需的？
2. 镜像里包含 `data/` 和 `chroma_db/` 有什么问题？（提示：镜像体积、更新方式）
3. 语义缓存阈值 0.95 是怎么定的？调到 0.90 会发生什么？
4. 分级模型后，改写质量下降会影响最终答案吗？怎么验证？
5. 公网 demo 暴露给所有人，你怎么防止别人刷你的 API Key？

## 复盘清单（本周里程碑自检）

- [ ] 公网 URL 可访问，流式正常
- [ ] 降本实验有四组数据
- [ ] README 里有在线 demo 链接与截图
- [ ] 有基础防护（限流 / 鉴权 / 预算告警）
- [ ] commit：`M2 上线：Docker + 部署 + 降本实验`
