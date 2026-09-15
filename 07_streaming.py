#!/usr/bin/env python3
"""07 — 流式输出：同一个 loop，边跑边往外递。

四个实验：

1. invoke：等整个 loop 结束，才拿到最终文本。
2. updates：每完成一步（模型 / 工具）推一次。
3. tokens：模型生成的文字一个片段一个片段出来。
4. sse：FastAPI 把上面的事件包成 SSE，本脚本再当「前端」收。

运行：
    python 07_streaming.py invoke
    python 07_streaming.py updates
    python 07_streaming.py tokens
    python 07_streaming.py sse
"""

from __future__ import annotations

import argparse
import json
import shlex
import threading
import time

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()

DEFAULT_QUESTION = "北京天气怎么样？再算一下 12*8"
SSE_PORT = 8765


def make_agent():
    return create_agent(
        model=make_chat_openai(),
        tools=LC_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


def last_text(messages: list) -> str:
    last = messages[-1]
    return getattr(last, "content", None) or str(last)


def print_message(message) -> None:
    kind = type(message).__name__
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            args = json.dumps(tc["args"], ensure_ascii=False)
            print(f"  [{kind}] → {tc['name']}({args})")
        return
    if isinstance(message, ToolMessage):
        print(f"  [ToolMessage name={message.name}] ← {message.content}")
        return
    content = getattr(message, "content", "")
    if content:
        print(f"  [{kind}] {content}")


def run_invoke(user_input: str) -> None:
    agent = make_agent()
    print("场景: invoke（等全部结束才返回）")
    print(f"用户: {user_input}")
    print("开始 invoke，结束前这里不会再有输出...\n")
    started = time.perf_counter()
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    elapsed = time.perf_counter() - started
    print(f"[{elapsed:.1f}s] 整段回来")
    print(f"\n>>> {last_text(result['messages'])}")


def run_updates(user_input: str) -> None:
    agent = make_agent()
    print("场景: updates（每完成一步推一次）")
    print(f"用户: {user_input}")
    started = time.perf_counter()
    for step in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        stream_mode="updates",
    ):
        elapsed = time.perf_counter() - started
        for node, payload in step.items():
            print(f"\n[{elapsed:.1f}s] node={node}")
            for message in payload.get("messages", []):
                print_message(message)


def run_tokens(user_input: str) -> None:
    agent = make_agent()
    print("场景: tokens（模型文字边生成边出来）")
    print(f"用户: {user_input}\n")
    started_answer = False
    for token, metadata in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        stream_mode="messages",
    ):
        node = metadata.get("langgraph_node", "?")
        tool_call_chunks = getattr(token, "tool_call_chunks", None) or []
        for chunk in tool_call_chunks:
            name = chunk.get("name")
            if name:
                print(f"[{node}] → {name}", flush=True)
        if node != "model":
            continue
        text = getattr(token, "text", None) or ""
        if not text:
            continue
        if not started_answer:
            print(f"[{node}] ", end="", flush=True)
            started_answer = True
        print(text, end="", flush=True)
    print()


def iter_sse_events(user_input: str):
    """把 stream 的两种粒度收成给前端的事件。"""
    agent = make_agent()
    for mode, chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            token, metadata = chunk
            if metadata.get("langgraph_node") != "model":
                continue
            text = getattr(token, "text", None) or ""
            if text:
                yield {"type": "token", "text": text}
            continue

        for _node, payload in chunk.items():
            print(f'chunk: {chunk}, {chunk.items()}')
            for message in payload.get("messages", []):
                if isinstance(message, AIMessage) and message.tool_calls:
                    for tc in message.tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc["name"],
                            "args": tc["args"],
                        }
                if isinstance(message, ToolMessage):
                    yield {
                        "type": "tool_result",
                        "name": message.name,
                        "content": message.content,
                    }
    yield {"type": "done"}


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/chat")
def chat(q: str = DEFAULT_QUESTION):
    def events():
        for event in iter_sse_events(q):
            yield format_sse(event)

    return StreamingResponse(events(), media_type="text/event-stream")


def wait_for_server(url: str, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=0.3).raise_for_status()
            return
        except (httpx.HTTPError, httpx.InvalidURL):
            time.sleep(0.05)
    raise SystemExit(f"SSE 服务没有起来: {url}")


def run_sse(user_input: str) -> None:
    print("场景: sse（FastAPI 把事件推成 text/event-stream）")
    print(f"用户: {user_input}")
    print(f"服务: http://127.0.0.1:{SSE_PORT}/chat")
    print(
        "等价 curl:\n"
        f'  curl -N "http://127.0.0.1:{SSE_PORT}/chat" '
        f"--get --data-urlencode q={shlex.quote(user_input)}\n"
    )

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=SSE_PORT,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for_server(f"http://127.0.0.1:{SSE_PORT}/health")

    with httpx.stream(
        "GET",
        f"http://127.0.0.1:{SSE_PORT}/chat",
        params={"q": user_input},
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                print(line, flush=True)

    server.should_exit = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=("invoke", "updates", "tokens", "sse"),
        default="invoke",
        help="演示场景；默认 invoke",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.scenario == "invoke":
        run_invoke(DEFAULT_QUESTION)
    elif args.scenario == "updates":
        run_updates(DEFAULT_QUESTION)
    elif args.scenario == "tokens":
        run_tokens(DEFAULT_QUESTION)
    else:
        run_sse(DEFAULT_QUESTION)


if __name__ == "__main__":
    main()
