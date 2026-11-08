"""嵌入：真实 API + 离线哈希嵌入器。

为什么需要单独的配置？
- 聊天模型和嵌入模型通常来自不同厂商（例如 Kimi 聊天 + 百炼嵌入）
- Kimi / DeepSeek 都没有 embedding 接口，复用聊天 Key 会 404

所以这里支持独立的 EMBED_API_KEY / EMBED_BASE_URL / EMBED_MODEL / EMBED_DIMENSIONS；
不配置时再回退到聊天客户端（仅当那家确实提供 embedding 接口）。
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Callable, Sequence

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


@dataclass(frozen=True)
class EmbedSettings:
    base_url: str
    api_key: str
    model: str
    dimensions: int | None = None


class EmbedConfigError(RuntimeError):
    """嵌入配置缺失或该厂商不提供 embedding 接口。"""


# 明确不提供 embedding 接口的厂商：回退时给出可行动的提示，而不是让它 404
NO_EMBEDDING_HOSTS = ("api.moonshot.cn", "api.deepseek.com")


def _default_model_for(base_url: str) -> str:
    if "aliyuncs" in base_url or "dashscope" in base_url:
        return "qwen3.7-text-embedding"
    if "openai.com" in base_url:
        return "text-embedding-3-small"
    return "text-embedding-v3"


def load_embed_settings() -> EmbedSettings:
    """优先级：EMBED_* > 聊天客户端配置（仅当厂商支持 embedding）。"""
    from code.shared.llm_client import load_env_file

    load_env_file()  # 独立调用本模块时也要能读到 .env 里的 EMBED_*

    base_url = os.getenv("EMBED_BASE_URL", "")
    api_key = os.getenv("EMBED_API_KEY", "")
    model = os.getenv("EMBED_MODEL", "")
    raw_dims = os.getenv("EMBED_DIMENSIONS", "").strip()
    dimensions = int(raw_dims) if raw_dims else None

    if base_url and api_key:
        return EmbedSettings(
            base_url=base_url,
            api_key=api_key,
            model=model or _default_model_for(base_url),
            dimensions=dimensions,
        )

    # 回退：复用聊天配置
    from code.shared.llm_client import load_config

    cfg = load_config()
    if any(host in cfg.base_url for host in NO_EMBEDDING_HOSTS):
        raise EmbedConfigError(
            f"{cfg.provider} 不提供 embedding 接口。\n"
            "请在 .env 里单独配置嵌入服务，例如百炼：\n"
            "EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            "EMBED_API_KEY=sk-xxx\n"
            "EMBED_MODEL=qwen3.7-text-embedding\n"
            "或者继续用离线模式（HashingEmbedder）跑通流程。"
        )
    return EmbedSettings(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=model or _default_model_for(cfg.base_url),
        dimensions=dimensions,
    )


def get_embed_fn(model: str | None = None, batch_size: int = 16, dimensions: int | None = None) -> EmbedFn:
    """返回一个"批量文本 → 向量"的函数（OpenAI 兼容 /embeddings 接口）。"""
    from openai import OpenAI

    settings = load_embed_settings()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=60)
    model = model or settings.model
    dimensions = dimensions or settings.dimensions

    def embed(texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            kwargs: dict = {"model": model, "input": batch}
            if dimensions:
                kwargs["dimensions"] = dimensions
            resp = client.embeddings.create(**kwargs)
            vectors.extend([d.embedding for d in resp.data])
        return vectors

    return embed


class HashingEmbedder:
    """零依赖的确定性嵌入器：字符 n-gram → 哈希桶 → 归一化。

    只用于离线演示与测试；语义能力远弱于真实模型。
    """

    def __init__(self, dim: int = 256, ngram: int = 2):
        self.dim, self.ngram = dim, ngram

    def _tokens(self, text: str) -> list[str]:
        text = re.sub(r"\s+", "", text.lower())
        padded = f"<{text}>"
        return [padded[i : i + self.ngram] for i in range(len(padded) - self.ngram + 1)]

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in self._tokens(text):
                bucket = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big") % self.dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out
