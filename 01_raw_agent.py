#!/usr/bin/env python3
"""01 — 不用框架：手写 Tool-Calling Agent

核心循环（所有 agent 框架的本质）：

    messages = [system, user]
    while True:
        response = llm(messages, tools=...)
        if 没有 tool_calls:
            return 最终文本
        把 assistant 消息 append 到 messages
        本地执行每个 tool
        把 tool 结果以 role=tool 的消息 append 回去
        继续 while

跑：
    cp .env.example .env   # 填入 DEEPSEEK_API_KEY
    pip install -r requirements.txt
    python 01_raw_agent.py
    python 01_raw_agent.py "北京天气怎么样？另外算一下 23*17"
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from common.llm import get_model, make_openai_client
from common.tools import OPENAI_TOOLS, SYSTEM_PROMPT, run_tool

load_dotenv()

MAX_STEPS = 8


def run_agent(user_input: str, *, verbose: bool = True) -> str:
    client = make_openai_client()
    model = get_model()

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    for step in range(1, MAX_STEPS + 1):
        if verbose:
            print(f"\n{'=' * 50}")
            print(f"Step {step}: 调用模型 ({model})")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",  # 模型自己决定是否调工具
        )
        msg = response.choices[0].message

        # 1) 没有 tool call → 最终答案
        if not msg.tool_calls:
            answer = msg.content or ""
            if verbose:
                print(f"最终回答: {answer}")
            return answer

        # 2) 把「模型想调工具」的消息写回对话历史
        #    注意：必须原样保留 tool_calls，下一轮才能把 tool 结果对上 id
        assistant_msg = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)

        # 3) 本地执行工具，结果以 role=tool 回传
        for tc in msg.tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            if verbose:
                print(f"  → 工具调用: {name}({raw_args})")

            result = run_tool(name, raw_args)
            if verbose:
                print(f"  ← 工具结果: {result}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    return f"超过最大步数 {MAX_STEPS}，停止。"


def main() -> None:
    user_input = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "北京天气怎么样？另外帮我算一下 (12+8)*3，再告诉我现在 UTC 几点。"
    )
    print(f"用户: {user_input}")
    answer = run_agent(user_input)
    print(f"\n>>> {answer}")


if __name__ == "__main__":
    main()
