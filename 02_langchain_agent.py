#!/usr/bin/env python3
"""02 — 用 LangChain 实现同一个 Agent

对照 01_raw_agent.py：

| 原生手写                     | LangChain                          |
|-----------------------------|------------------------------------|
| OPENAI_TOOLS JSON schema    | @tool + 函数类型注解 / docstring   |
| while + chat.completions    | create_agent 内部循环              |
| role=tool 消息自己拼        | 框架自动拼 ToolMessage             |
| run_tool 自己分发           | 框架按 name 调用 @tool 函数        |

跑：
    python 02_langchain_agent.py
    python 02_langchain_agent.py "上海天气如何？23*17 等于多少"
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv
from langchain.agents import create_agent

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()


def run_agent(user_input: str, *, verbose: bool = True) -> str:
    agent = create_agent(
        model=make_chat_openai(),
        tools=LC_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]}
    )

    messages = result["messages"]
    if verbose:
        print("\n--- 中间步骤（LangChain 自动维护的 messages）---")
        for m in messages:
            kind = type(m).__name__
            content = getattr(m, "content", None)
            tool_calls = getattr(m, "tool_calls", None)
            name = getattr(m, "name", None)
            print(f"m: {m}")
            if tool_calls:
                print(f"[{kind}] tool_calls={tool_calls}")
            elif name:
                print(f"[{kind} name={name}] {content}")
            else:
                text = content if content else str(m)
                print(f"[{kind}] {text}")

    last = messages[-1]
    return getattr(last, "content", None) or str(last)


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
