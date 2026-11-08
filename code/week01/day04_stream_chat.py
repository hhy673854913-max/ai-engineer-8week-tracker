"""Day 04 · 终端流式聊天：TTFT、多轮、命令、中断处理。

用法：
    python code/week01/day04_stream_chat.py
    python code/week01/day04_stream_chat.py --temperature 0.2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client  # noqa: E402

SYSTEM = "你是一个简洁的中文助手，回答控制在 150 字以内。"


def parse_cmd(line: str) -> tuple[str, str | None]:
    """返回 (命令, 参数)。非命令返回 ('chat', 原文)。"""
    if not line.startswith("/"):
        return "chat", line
    parts = line[1:].split(maxsplit=1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=800)
    args = parser.parse_args(argv)

    client = get_client()
    history: list[dict] = [{"role": "system", "content": SYSTEM}]
    temperature = args.temperature

    print("流式聊天已启动。命令：/exit 退出  /clear 清空  /temp 0.2 调温度")
    while True:
        try:
            line = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return 0
        if not line:
            continue

        cmd, arg = parse_cmd(line)
        if cmd == "exit":
            print("再见。")
            return 0
        if cmd == "clear":
            history = [{"role": "system", "content": SYSTEM}]
            print("上下文已清空。")
            continue
        if cmd == "temp" and arg:
            temperature = float(arg)
            print(f"温度已设为 {temperature}")
            continue
        if cmd != "chat":
            print("未知命令。可用：/exit /clear /temp <值>")
            continue

        history.append({"role": "user", "content": line})
        print("AI> ", end="", flush=True)

        t0 = time.perf_counter()
        first: float | None = None
        chars = 0
        buffer: list[str] = []
        try:
            for piece in client.stream(history, temperature=temperature, max_tokens=args.max_tokens):
                if first is None:
                    first = time.perf_counter() - t0
                chars += len(piece)
                buffer.append(piece)
                print(piece, end="", flush=True)
        except KeyboardInterrupt:
            print("\n[已中断，保留已输出的内容]")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[错误] {type(exc).__name__}: {exc}")
            history.pop()  # 失败的一轮不进上下文
            continue

        total = time.perf_counter() - t0
        answer = "".join(buffer)
        history.append({"role": "assistant", "content": answer})
        print(
            f"\n[TTFT {first:.2f}s | 总 {total:.2f}s | {chars} 字 | {chars / max(total, 1e-6):.1f} 字/s]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
