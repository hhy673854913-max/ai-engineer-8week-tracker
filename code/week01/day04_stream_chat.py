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

# 把项目根目录（本文件向上 2 级）插入模块搜索路径最前，
# 保证无论从哪个目录运行，都能 import code.shared.llm_client
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 中文终端默认 GBK 代码页，遇到 emoji 会 UnicodeEncodeError；
# 这里统一改为 UTF-8 输出，errors="replace" 兜底无法编码的字符
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from code.shared.llm_client import get_client  # noqa: E402

SYSTEM = "你是一个简洁的中文助手，回答控制在 150 字以内。"

# 断联重连参数：指数退避 1s → 2s → 4s，上限 5 次
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_ATTEMPTS = 5


def parse_cmd(line: str) -> tuple[str, str | None]:
    """解析斜杠命令。返回 (命令, 参数)；非命令输入返回 ('chat', 原文)。

    例："/temp 0.5" -> ("temp", "0.5")；"/exit" -> ("exit", None)；"你好" -> ("chat", "你好")
    """
    if not line.startswith("/"):
        return "chat", line
    parts = line[1:].split(maxsplit=1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else None)


def stream_with_reconnect(
    client,
    history: list[dict],
    temperature: float,
    max_tokens: int,
    received: dict[int, str],
    max_seq: list[int],
) -> tuple[bool, int]:
    """带自动重连的流式输出。

    断联后指数退避重试，从断点续传（利用 chunk 序号去重）。
    返回 (是否成功, 重连次数)。
    """
    retries = 0
    while True:
        try:
            # with_seq=True 获取带序号的 chunk，用于断点续传去重
            for seq, piece in client.stream(
                history,
                temperature=temperature,
                max_tokens=max_tokens,
                with_seq=True,
            ):
                # 序号去重：已接收过的 chunk 直接跳过（断点续传时可能重复）
                if seq in received:
                    continue
                # 序号连续性检查：乱序/跳跃说明协议异常，丢弃
                expected = max_seq[0] + 1
                if seq != expected and seq != 0:
                    print(f"\n[警告] chunk 序号异常: 期望 {expected}, 实际 {seq}, 已丢弃")
                    continue
                received[seq] = piece
                max_seq[0] = seq
                print(piece, end="", flush=True)
            return True, retries
        except KeyboardInterrupt:
            # 用户主动中断，不再重试
            raise
        except Exception as exc:  # noqa: BLE001
            retries += 1
            if retries > RECONNECT_MAX_ATTEMPTS:
                print(f"\n[重连失败] 已达最大重试次数 {RECONNECT_MAX_ATTEMPTS} 次")
                return False, retries
            delay = RECONNECT_BASE_DELAY * (2 ** (retries - 1))
            chars_received = sum(len(v) for v in received.values())
            print(
                f"\n[连接中断] 已接收 {chars_received} 字符，"
                f"{delay:.0f}s 后重连（第 {retries}/{RECONNECT_MAX_ATTEMPTS} 次）..."
            )
            time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=800)
    args = parser.parse_args(argv)

    client = get_client()
    history: list[dict] = [{"role": "system", "content": SYSTEM}]
    temperature = args.temperature

    print(f"流式聊天已启动。命令：/exit 退出  /clear 清空  /temp <值> 调温度，当前温度 {temperature}")
    while True:
        try:
            line = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+Z+回车 触发 EOFError，Ctrl+C 触发 KeyboardInterrupt，均优雅退出
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
        # 断点续传状态：seq -> text 映射，max_seq 记录当前最大序号
        received: dict[int, str] = {}
        max_seq = [-1]  # 用 list 以便在函数内修改

        try:
            # 流式：逐 chunk 输出并立即 flush，否则数据会积在缓冲区里变成"假流式"
            success, retries = stream_with_reconnect(
                client, history, temperature, args.max_tokens, received, max_seq
            )
            if not success:
                # 彻底失败：提示用户可选操作
                chars_received = sum(len(v) for v in received.values())
                print(f"\n[彻底失败] 已接收 {chars_received} 字符。")
                print("可选操作：")
                print("  1. 输入 /retry 重新生成（将从头开始，不是续传）")
                print("  2. 输入 /copy 复制已有内容")
                print("  3. 输入其他内容继续新对话")
                # 失败的一轮不进上下文，避免污染后续对话
                history.pop()
                continue

            # 按序号排序拼接完整回复
            buffer = [received[seq] for seq in sorted(received.keys())]
            answer = "".join(buffer)
            chars = len(answer)
            first = time.perf_counter() - t0  # 简化：用总时间代替 TTFT

        except KeyboardInterrupt:
            # 流式输出中按 Ctrl+C：停止拉取，已输出的部分内容仍然保留
            print("\n[已中断，保留已输出的内容]")
            # 将已接收内容加入历史
            if received:
                buffer = [received[seq] for seq in sorted(received.keys())]
                partial = "".join(buffer)
                history.append({"role": "assistant", "content": partial})
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"\n[错误] {type(exc).__name__}: {exc}")
            history.pop()  # 失败的一轮不进上下文，避免污染后续对话
            continue

        total = time.perf_counter() - t0
        history.append({"role": "assistant", "content": answer})  # 完整回复入历史，供多轮使用
        print(
            f"\n[TTFT {first:.2f}s | 总 {total:.2f}s | {chars} 字 | {chars / max(total, 1e-6):.1f} 字/s]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
