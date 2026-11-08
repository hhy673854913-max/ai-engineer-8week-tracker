"""让 `code` 包在 pytest 下可导入，并隔离开发者本地的 .env。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """测试不应依赖本地 .env（否则别人 clone 下来能过、你本地反而挂）。"""
    import code.shared.llm_client as llm

    monkeypatch.setattr(llm, "load_env_file", lambda *args, **kwargs: None)
