# Day 09 · 多模态：让模型"看图"

> W2 · 周四 ｜ 5h ｜ 产出 `code/week02/day09_vision.py` ｜ [Day 08](day-08.md) · [Day 10](day-10.md)

**今日目标**
- 掌握图像输入的两种传法（URL / base64）与 `detail` 参数
- 理解视觉模型的计费方式，学会"先压缩再上传"
- 写一个"图片 → 可检索结构化描述"的脚本，为 Day 11 的向量检索准备数据

**验收**：对 10 张图输出结构化 JSON（主体 / 场景 / 画面文字 / 风格 / 标签），并落盘 `output/images.jsonl`。

---

## 上午 09:00–11:30 · 理论输入

### 1. 图像是怎么"进"模型的

两种传法，本质都是把图片变成一段特殊 token：

```python
# A. 公网 URL（最省事，但要求图片可公网访问）
{"type": "image_url", "image_url": {"url": "https://example.com/a.jpg", "detail": "high"}}

# B. base64 data URL（本地图片、内网图片用这个）
{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
```

`detail` 影响**图片被切成的 token 数**：
- `low`：固定少量 token，快且便宜，适合"这张图大概是什么"
- `high`：按分辨率切块，细节清楚，贵；用于读文字、识小数、看 UI 细节
- `auto`：由服务端决定

### 2. 计费直觉

视觉 token ≈ `(宽×高) / 750` 量级（不同厂商算法不同，以官方文档为准）。
一张 4K 截图可能上千 token，一张 512×512 缩略图可能只要几十 token。

所以工程上的第一反应应该是：**上传前先压缩**。

```python
from PIL import Image
import io

def to_data_url(path: Path, max_side: int = 1024, quality: int = 80) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
```

`max_side=1024` 是"够看清又不烧钱"的经验值；要读小字就调到 1600 并配合 `detail="high"`。

### 3. 多图输入与"对比型"任务

```python
content = [
    {"type": "text", "text": "对比这两张活动 Banner，指出 3 处视觉差异，并判断哪张点击率可能更高、为什么。"},
    {"type": "image_url", "image_url": {"url": url_a}},
    {"type": "image_url", "image_url": {"url": url_b}},
]
```

多图任务是视觉模型的强项场景：**设计稿走查、UI 回归对比、素材合规检查**。这类任务在你 11 年前端经验里到处都是。

### 4. 视觉任务的三个坑

| 坑 | 表现 | 对策 |
| --- | --- | --- |
| 幻觉读字 | 编造图里没有的文字 | 要求"逐字引用，不确定就写 unclear" |
| 坐标系错位 | 说"左上角"其实在右下 | 让模型用 9 宫格描述（"右上区域"） |
| 分辨率不足 | 小字识别错 | 提高 `max_side` / `detail`；或先裁剪再传 |

### 5. 结构化视觉描述的价值

一张图如果只有"一只猫"，它无法被检索。但如果输出：

```json
{
  "scene": "室内生日派对",
  "main_objects": ["蛋糕", "气球", "礼物盒"],
  "people": "3 人，均为儿童",
  "text_in_image": "HAPPY BIRTHDAY",
  "style": "暖色调 / 卡通",
  "search_tags": ["生日", "派对", "儿童", "室内", "暖色"]
}
```

它就能进入向量库，被"找一张暖色调的儿童生日图"这样的自然语言检索到。
**多模态的真正用途不是"看图说话"，而是"把非结构化数据变成可检索的结构化数据"。**

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 最小视觉调用（30 min）

```python
def describe(image_path: Path) -> dict:
    content = [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": to_data_url(image_path), "detail": "high"}},
    ]
    raw = chat([{"role": "user", "content": content}], json_mode=True, temperature=0.2)
    return json.loads(extract_json(raw))
```

注意：**messages 的 content 可以是"数组"**，这是文本调用与视觉调用的唯一结构差异。

### 任务 2 · 设计描述 schema（40 min）

```python
from pydantic import BaseModel, Field

class ImageDesc(BaseModel):
    scene: str = Field(description="一句话场景描述")
    main_objects: list[str] = Field(min_length=1, max_length=8)
    people: str | None = None
    text_in_image: str | None = Field(default=None, description="图中文字，逐字转录；无则 null")
    style: str
    search_tags: list[str] = Field(min_length=3, max_length=10)
    confidence: float = Field(ge=0, le=1)
```

用 Pydantic 的 `description` 做"字段级 prompt"——这是给模型看文档，也给下游看文档，一举两得。

### 任务 3 · 批量处理与成本核算（60 min）

```python
async def batch(images: list[Path], concurrency: int = 3) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)   # 防 429
    async def one(p: Path) -> dict:
        async with sem:
            return await describe_async(p)
    return await asyncio.gather(*(one(p) for p in images))
```

跑 10 张图，记录：平均耗时、平均输入 token、单张成本、失败率。写进 `logs/day-09.md`。

### 任务 4 · 图片合规初筛（30 min）

设计一个"素材合规检查"prompt：判断是否含敏感元素、是否有夸大宣传用语、是否有二维码/联系方式。
输出 `{"pass": bool, "issues": [...], "suggestion": "..."}`。
这是运营场景里极实用的自动化，也是你简历上"AI 提效"故事的另一种讲法。

---

## 代码思考（写进 `logs/day-09.md`）

1. `detail=low` 与 `high` 的差别，在"读图里的小字"任务上会带来多大准确率差？实测记录。
2. 为什么 base64 不适合传大图？除了 token 成本还有什么（请求体大小 / 网关限制 / 内存）？
3. 多图对比时，两张图的顺序会影响结论吗？怎么设计实验验证？
4. `text_in_image` 要求"逐字转录"，模型仍会"美化"错别字——这个错误在什么业务里是致命的？
5. 图片描述写入向量库后，"检索一张暖色调生日图"为什么会检索失败？（提示：描述字段与检索 query 的语义分布差异）

## 复盘清单

- [ ] 跑通 10 张图，有成本与耗时数据
- [ ] `output/images.jsonl` 可用于 Day 11 的检索实验
- [ ] 合规初筛 prompt 试过至少 3 张"问题图"
- [ ] commit：`day09: 多模态结构化描述`
