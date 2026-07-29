#!/usr/bin/env python3
"""03 — 过渡版：LangChain 封装模型，但 loop 仍自己写

适合「已经理解 01，还不想黑盒 create_agent」时阅读。

映射：
- ChatOpenAI.bind_tools(tools)  ≈  原生 tools=OPENAI_TOOLS
- AIMessage.tool_calls         ≈  response.choices[0].message.tool_calls
- ToolMessage                  ≈  {"role": "tool", ...}

跑：
    python 03_langchain_manual_loop.py
"""

from __future__ import annotations

import json
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()

MAX_STEPS = 8


def run_agent(user_input: str, *, verbose: bool = True) -> str:
    model = make_chat_openai()
    # bind_tools：把工具 schema 挂到请求上（等价于原生 tools=...）
    model_with_tools = model.bind_tools(LC_TOOLS)
    tools_by_name = {t.name: t for t in LC_TOOLS}

    messages: list = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ]

    for step in range(1, MAX_STEPS + 1):
        if verbose:
            print(f"\n{'=' * 50}")
            print(f"Step {step}: model.invoke")

        ai: AIMessage = model_with_tools.invoke(messages)
        messages.append(ai)

        if not ai.tool_calls:
            answer = ai.content if isinstance(ai.content, str) else str(ai.content)
            if verbose:
                print(f"最终回答: {answer}")
            return answer

        for tc in ai.tool_calls:
            name = tc["name"]
            args = tc["args"]
            if verbose:
                print(f"  → 工具调用: {name}({json.dumps(args, ensure_ascii=False)})")

            tool = tools_by_name[name]
            result = tool.invoke(args)
            if verbose:
                print(f"  ← 工具结果: {result}")

            messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tc["id"],
                    name=name,
                )
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
