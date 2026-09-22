#!/usr/bin/env python3
"""13 — 会话落在本机 MySQL。刷新之后还在，第二轮只传新的一句。

checkpointer 是 PyMySQLSaver。每一步的快照按 thread_id 写进库 stu_agent。
页面把 thread_id 放在 localStorage，刷新后用同一个 id 把 messages 读回来。

运行（两个终端）：
    python 13_session.py
    cd 10_web && npm run dev

浏览器打开 http://127.0.0.1:5173
先问城市，再问「刚才那个城市」。关掉标签再打开，上一句还在。
"""

from __future__ import annotations

import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()

PAGE_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
PORT = 8765


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content or "")


def rows_from_messages(messages: list) -> list[dict]:
    rows: list[dict] = []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            for call in tool_calls:
                args = json.dumps(call["args"], ensure_ascii=False)
                rows.append({"kind": "tool", "text": f"→ {call['name']}({args})"})
            continue
        name = getattr(message, "name", None)
        text = message_text(message)
        if name:
            rows.append({"kind": "tool", "text": f"← {name}: {text}"})
        elif type(message).__name__ == "HumanMessage" and text:
            rows.append({"kind": "user", "text": text})
        elif text:
            rows.append({"kind": "answer", "text": text})
    return rows


def iter_sse_events(agent, question: str, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    for mode, chunk in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        config,
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
            for message in payload.get("messages", []):
                if isinstance(message, AIMessage) and message.tool_calls:
                    for call in message.tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": call["name"],
                            "args": call["args"],
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


def build_app(agent) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=PAGE_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/history")
    def history(thread_id: str):
        snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
        messages = (snapshot.values or {}).get("messages", [])
        return {"thread_id": thread_id, "rows": rows_from_messages(messages)}

    @app.get("/chat")
    def chat(q: str, thread_id: str):
        if not q.strip() or not thread_id.strip():
            raise HTTPException(status_code=400, detail="q 和 thread_id 都要有")

        def events():
            for event in iter_sse_events(agent, q, thread_id):
                yield format_sse(event)

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def main() -> None:
    uri = os.environ.get("MYSQL_URI")
    if not uri:
        raise SystemExit("缺少 MYSQL_URI。在 .env 里写成 mysql://用户:密码@127.0.0.1:3306/stu_agent")
    with PyMySQLSaver.from_conn_string(uri) as checkpointer:
        checkpointer.setup()
        agent = create_agent(
            model=make_chat_openai(),
            tools=LC_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
        print("MySQL: stu_agent.checkpoints")
        print(f"Agent: http://127.0.0.1:{PORT}/chat")
        print("页面:  http://127.0.0.1:5173")
        print("另一个终端: cd 10_web && npm run dev")
        uvicorn.run(build_app(agent), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
