"""Day 25 · 三层记忆：滑动窗口 + 摘要 + 长期偏好（本地 JSON 版）。

离线也能演示：用 HashingEmbedder 做召回，用规则抽取偏好。
接上 LLM 后把 extract() 换成模型抽取即可。

用法：
    python -m code.week05.memory
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

PREFERENCE_PATTERNS = [
    (r"回答(?:尽量)?(?:简短|简洁|短)(?:一点|些)?", "偏好简短回答"),
    (r"(?:我|本人)(?:是|在做)([^，。；\n]{2,12})", "身份：{0}"),
    (r"不要(?:用)?(?:感叹号|表情)", "不喜欢感叹号与表情"),
]


@dataclass
class MemoryItem:
    id: str
    user_id: str
    kind: str  # preference | fact
    content: str
    quote: str
    confidence: float
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def make(cls, user_id: str, kind: str, content: str, quote: str, confidence: float) -> "MemoryItem":
        digest = hashlib.sha1(f"{user_id}:{content}".encode()).hexdigest()[:10]
        return cls(id=digest, user_id=user_id, kind=kind, content=content, quote=quote, confidence=confidence)


class LongTermMemory:
    """最简实现：JSON 文件 + 哈希向量召回。生产请换向量库并加隔离与过期策略。"""

    def __init__(self, path: Path, user_id: str, dim: int = 256):
        self.path = Path(path)
        self.user_id = user_id
        self.dim = dim
        self.items: list[MemoryItem] = []
        self._load()

    # -- 持久化 ----------------------------------------------------------
    def _load(self) -> None:
        if self.path.exists():
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = [MemoryItem(**r) for r in rows if r.get("user_id") == self.user_id]

    def _save(self) -> None:
        all_rows = []
        if self.path.exists():
            all_rows = json.loads(self.path.read_text(encoding="utf-8"))
        all_rows = [r for r in all_rows if r.get("user_id") != self.user_id] + [asdict(i) for i in self.items]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- 抽取 ------------------------------------------------------------
    def extract(self, user_text: str) -> list[MemoryItem]:
        found: list[MemoryItem] = []
        for pattern, template in PREFERENCE_PATTERNS:
            match = re.search(pattern, user_text)
            if not match:
                continue
            content = template.format(*match.groups()) if "{" in template else template
            quote = match.group(0)
            found.append(MemoryItem.make(self.user_id, "preference", content, quote, 0.9))
        return found

    def add(self, items: list[MemoryItem]) -> int:
        existing = {i.content for i in self.items}
        new = [i for i in items if i.content not in existing]
        self.items.extend(new)
        if new:
            self._save()
        return len(new)

    # -- 召回 ------------------------------------------------------------
    def _vector(self, text: str) -> list[float]:
        from code.week03.mini_rag.embeddings import HashingEmbedder

        return HashingEmbedder(dim=self.dim)([text])[0]

    def recall(self, query: str, k: int = 3, min_score: float = 0.3) -> list[MemoryItem]:
        from code.week03.mini_rag.similarity import cosine

        if not self.items:
            return []
        qv = self._vector(query)
        scored = [(cosine(qv, self._vector(i.content)), i) for i in self.items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for score, item in scored[:k] if score >= min_score]

    def forget(self, memory_id: str) -> bool:
        before = len(self.items)
        self.items = [i for i in self.items if i.id != memory_id]
        if len(self.items) != before:
            self._save()
            return True
        return False

    def forget_user(self) -> int:
        count = len(self.items)
        self.items = []
        self._save()
        return count


def build_system_prompt(base: str, memories: list[MemoryItem]) -> str:
    if not memories:
        return base + "\n\n已知用户信息：（无）"
    block = "\n".join(f"- {m.content}" for m in memories)
    return base + f"\n\n已知用户信息：\n{block}\n请在回答时遵守这些偏好。"


def demo() -> None:
    path = ROOT / "output" / "memory_store.json"
    memory = LongTermMemory(path, user_id="u_001")

    if path.exists():
        memory.forget_user()

    session1 = "你好，我是做游戏运营的。回答尽量简短一点，不要用感叹号"
    added = memory.add(memory.extract(session1))
    print(f"会话 1 抽取到 {added} 条记忆")

    query = "请简短回答：RAG 是什么"
    recalled = memory.recall(query, min_score=0.02)
    print(f"\n会话 2 的问题：{query}")
    print(f"召回 {len(recalled)} 条：{[m.content for m in recalled]}")
    print("\n会话 2 的 system 提示：")
    print(build_system_prompt("你是助手。", recalled))

    print(f"\n删除全部记忆：{memory.forget_user()} 条")
    print(f"删除后召回：{memory.recall(query)}")


if __name__ == "__main__":
    demo()
