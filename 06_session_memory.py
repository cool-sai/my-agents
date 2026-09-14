#!/usr/bin/env python3
"""06 — 短期会话记忆：messages 列表就是记忆。

四个实验：

1. manual：像 01/03 一样自己保存 messages，第二轮能接上。
2. forget：create_agent 每次只传入本轮用户消息，没有 checkpointer，第二轮失忆。
3. remember：InMemorySaver + 同一个 thread_id，框架把历史 messages 接回去。
4. threads：两个 thread_id 互不串话。

运行：
    python 06_session_memory.py manual
    python 06_session_memory.py forget
    python 06_session_memory.py remember
    python 06_session_memory.py threads
"""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()

MAX_STEPS = 8

WEATHER_TURNS = [
    "北京天气怎么样？",
    "我刚才问的是哪个城市？那里多少度？",
]


def last_text(messages: list) -> str:
    last = messages[-1]
    return getattr(last, "content", None) or str(last)


def print_messages(messages: list, title: str) -> None:
    print(f"\n--- {title} ({len(messages)} 条) ---")
    for message in messages:
        kind = type(message).__name__
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)
        name = getattr(message, "name", None)
        if tool_calls:
            print(f"[{kind}] tool_calls={tool_calls}")
        elif name:
            print(f"[{kind} name={name}] {content}")
        else:
            print(f"[{kind}] {content}")


def run_manual_turn(model_with_tools, tools_by_name, messages: list) -> str:
    """03 的 loop：历史 messages 一直留在同一个列表里。"""
    for _ in range(MAX_STEPS):
        ai = model_with_tools.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return last_text(messages)

        for tc in ai.tool_calls:
            name = tc["name"]
            args = tc["args"]
            print(f"  → 工具调用: {name}({json.dumps(args, ensure_ascii=False)})")
            result = tools_by_name[name].invoke(args)
            print(f"  ← 工具结果: {result}")
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"], name=name)
            )
    return f"超过最大步数 {MAX_STEPS}，停止。"


def run_manual() -> None:
    model_with_tools = make_chat_openai().bind_tools(LC_TOOLS)
    tools_by_name = {t.name: t for t in LC_TOOLS}
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

    print("场景: manual（自己保存 messages）")
    for i, user_input in enumerate(WEATHER_TURNS, start=1):
        print(f"\n{'=' * 50}")
        print(f"第 {i} 轮用户: {user_input}")
        messages.append(HumanMessage(content=user_input))
        answer = run_manual_turn(model_with_tools, tools_by_name, messages)
        print_messages(messages, "当前 messages")
        print(f"\n>>> {answer}")


def make_stateless_agent():
    return create_agent(
        model=make_chat_openai(),
        tools=LC_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


def make_memory_agent(checkpointer: InMemorySaver):
    return create_agent(
        model=make_chat_openai(),
        tools=LC_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


def run_forget() -> None:
    agent = make_stateless_agent()
    print("场景: forget（无 checkpointer，每轮只传本轮用户消息）")

    for i, user_input in enumerate(WEATHER_TURNS, start=1):
        print(f"\n{'=' * 50}")
        print(f"第 {i} 轮用户: {user_input}")
        result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
        print_messages(result["messages"], "本轮 messages")
        print(f"\n>>> {last_text(result['messages'])}")


def invoke_turn(agent, user_input: str, thread_id: str) -> list:
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config,
    )
    snapshot = agent.get_state(config)
    print_messages(snapshot.values["messages"], f"thread={thread_id} 的 checkpoint")
    return result["messages"]


def run_remember() -> None:
    agent = make_memory_agent(InMemorySaver())
    thread_id = "user-xiaolin"
    print(f"场景: remember（InMemorySaver + thread_id={thread_id}）")

    for i, user_input in enumerate(WEATHER_TURNS, start=1):
        print(f"\n{'=' * 50}")
        print(f"第 {i} 轮用户: {user_input}")
        messages = invoke_turn(agent, user_input, thread_id)
        print(f"\n>>> {last_text(messages)}")


def run_threads() -> None:
    agent = make_memory_agent(InMemorySaver())
    print("场景: threads（同一个 Agent、两份 thread_id）")

    first_turns = {
        "thread-a": "北京天气怎么样？",
        "thread-b": "上海天气怎么样？",
    }
    follow_up = "我刚才问的是哪个城市？"

    for thread_id, user_input in first_turns.items():
        print(f"\n{'=' * 50}")
        print(f"{thread_id} 第 1 轮: {user_input}")
        messages = invoke_turn(agent, user_input, thread_id)
        print(f"\n>>> {last_text(messages)}")

    for thread_id in first_turns:
        print(f"\n{'=' * 50}")
        print(f"{thread_id} 第 2 轮: {follow_up}")
        messages = invoke_turn(agent, follow_up, thread_id)
        print(f"\n>>> {last_text(messages)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=("manual", "forget", "remember", "threads"),
        default="forget",
        help="演示场景；默认 forget",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.scenario == "manual":
        run_manual()
    elif args.scenario == "forget":
        run_forget()
    elif args.scenario == "remember":
        run_remember()
    else:
        run_threads()


if __name__ == "__main__":
    main()
