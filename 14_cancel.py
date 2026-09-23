#!/usr/bin/env python3
"""14 — 取消正在跑的一轮。停掉页面上的流，也停掉还没做完的工具。

关掉 EventSource 只是浏览器不听了。这一课用同一面旗：
/cancel 把旗放下，slow_search 看见就返回，图不再往下叫模型。

运行（两个终端，不要和 10_web.py、13_session.py 同时开）：
    python 14_cancel.py
    cd 10_web && npm run dev

浏览器打开 http://127.0.0.1:5173
发送「慢查询：会员规则」，工具还在跑时点停止。
再发一句别的，那是新的一轮。
"""

from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.errors import GraphDrained
from langgraph.runtime import RunControl

from common.lc_tools import LC_TOOLS
from common.llm import make_chat_openai
from common.tools import SYSTEM_PROMPT

load_dotenv()

PAGE_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
PORT = 8765
SLOW_SECONDS = 20
CANCELLED = "已取消，没有查完"
PROMPT = (
    SYSTEM_PROMPT
    + "只有用户这一句里明确出现「慢查询」时才调用 slow_search。"
    + "不要补做上一轮被取消的慢查询。"
)


class Run:
    def __init__(self) -> None:
        self.control = RunControl()
        self.done = threading.Event()
        # 用户这句话落库之后就置上。历史只等这一下，不等整篇文章。
        self.started = threading.Event()
        self.base_rows: list | None = None
        self.events: list[dict] = []
        self.listeners: list[queue.Queue] = []
        self.finished = False
        self.lock = threading.Lock()

    def publish(self, event: dict | None) -> None:
        with self.lock:
            if event is None:
                self.finished = True
            else:
                self.events.append(event)
            targets = list(self.listeners)
            for box in targets:
                box.put(event)

    def subscribe(self, after: int = 0) -> queue.Queue:
        # after 之前的字历史接口已经带回去了。这里只补后面的，避免刷新再从头吐一遍。
        box: queue.Queue = queue.Queue()
        with self.lock:
            for event in self.events[after:]:
                box.put(event)
            if self.finished:
                box.put(None)
            else:
                self.listeners.append(box)
        return box

    def unsubscribe(self, box: queue.Queue) -> None:
        with self.lock:
            if box in self.listeners:
                self.listeners.remove(box)


# 一个 thread 同时只跑一轮。取消和工具看的是同一个 Run。
running: dict[str, Run] = {}


def load_lesson13():
    """13_session 不是合法模块名。历史记录的形状继续用那一课的。"""
    path = Path(__file__).with_name("13_session.py")
    spec = importlib.util.spec_from_file_location("lesson13", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def begin_run(thread_id: str) -> Run:
    run = Run()
    old = running.get(thread_id)
    if old is not None:
        old.control.request_drain("replaced")
        old.done.wait(timeout=5)
    running[thread_id] = run
    return run


def finish_run(thread_id: str, run: Run) -> None:
    if running.get(thread_id) is run:
        del running[thread_id]
    run.done.set()


@tool
def slow_search(topic: str, config: RunnableConfig) -> str:
    """慢查询，要好几秒。只有用户这一句明确写出「慢查询」时才调用。"""
    thread_id = str((config.get("configurable") or {}).get("thread_id", ""))
    run = running.get(thread_id)
    control = run.control if run is not None else None
    # 一次睡满 6 秒的话，停止要等它睡完。所以每 0.1 秒看一次旗。
    for _ in range(SLOW_SECONDS * 10):
        if control is not None and control.drain_requested:
            return CANCELLED
        time.sleep(0.1)
    return f"慢查询结果：{topic}"


def seal_cancelled_turn(agent, thread_id: str) -> list[tuple[str, str]]:
    """工具调用已经进快照、结果还没有时，补一条取消结果。

    缺了 ToolMessage，下一轮的消息列表是坏的，模型接口会拒。
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = agent.get_state(config)
    messages = (snapshot.values or {}).get("messages", [])
    answered = {
        message.tool_call_id
        for message in messages
        if isinstance(message, ToolMessage)
    }
    missing = [
        call
        for message in messages
        if isinstance(message, AIMessage)
        for call in (message.tool_calls or [])
        if call["id"] not in answered
    ]
    if not missing:
        return []
    agent.update_state(
        config,
        {
            "messages": [
                ToolMessage(
                    content=CANCELLED,
                    tool_call_id=call["id"],
                    name=call["name"],
                )
                for call in missing
            ]
        },
        as_node="tools",
    )
    return [(call["name"], CANCELLED) for call in missing]


def iter_sse_events(agent, question: str, thread_id: str, run: Run, rows_from_messages):
    config = {"configurable": {"thread_id": thread_id}}
    control = run.control
    # 先把这一句写入快照，再跑模型。刷新读历史时用的就是这份，不等文章写完。
    agent.update_state(
        config,
        {"messages": [{"role": "user", "content": question}]},
        as_node="__start__",
    )
    snapshot = agent.get_state(config)
    run.base_rows = rows_from_messages((snapshot.values or {}).get("messages", []))
    run.started.set()
    try:
        for mode, chunk in agent.stream(
            None,
            config,
            stream_mode=["messages", "updates"],
            control=control,
            durability="sync",
        ):
            if mode == "messages":
                token, metadata = chunk
                node = metadata.get("langgraph_node")
                # 工具结果也会从 messages 里过。在这里停会把后面的 tool_result 丢掉。
                # 只停模型接着往下吐的字。
                if control.drain_requested and node == "model":
                    break
                if node != "model":
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
    except GraphDrained:
        pass
    if control.drain_requested:
        for name, content in seal_cancelled_turn(agent, thread_id):
            yield {"type": "tool_result", "name": name, "content": content}
        yield {"type": "cancelled"}
        return
    yield {"type": "done"}


def build_app(agent, lesson) -> FastAPI:
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
        run = running.get(thread_id)
        if run is not None:
            # 库被这一轮占着。开跑时的快照加上已经吐出的字，马上返回。
            run.started.wait(timeout=5)
            with run.lock:
                rows = list(run.base_rows or [])
                pending = list(run.events)
            return {
                "thread_id": thread_id,
                "rows": rows,
                "pending": pending,
                "live": True,
            }
        # 别的会话不跟这一轮抢。检查点自己的锁只包住一次读取。
        snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
        messages = (snapshot.values or {}).get("messages", [])
        return {
            "thread_id": thread_id,
            "rows": lesson.rows_from_messages(messages),
            "live": False,
        }

    def stream_run(run: Run, after: int = 0):
        box = run.subscribe(after)
        try:
            while True:
                event = box.get()
                if event is None:
                    break
                yield lesson.format_sse(event)
        finally:
            run.unsubscribe(box)

    @app.get("/cancel")
    def cancel(thread_id: str):
        if not thread_id.strip():
            raise HTTPException(status_code=400, detail="thread_id 要有")
        run = running.get(thread_id)
        if run is None:
            return {"ok": True, "stopped": False}
        run.control.request_drain("cancel")
        return {"ok": True, "stopped": True}

    @app.get("/listen")
    def listen(thread_id: str, after: int = 0):
        if not thread_id.strip():
            raise HTTPException(status_code=400, detail="thread_id 要有")
        run = running.get(thread_id)
        if run is None:
            def once():
                yield lesson.format_sse({"type": "done"})

            return StreamingResponse(once(), media_type="text/event-stream")
        return StreamingResponse(
            stream_run(run, max(after, 0)),
            media_type="text/event-stream",
        )

    @app.get("/chat")
    def chat(q: str, thread_id: str):
        if not q.strip() or not thread_id.strip():
            raise HTTPException(status_code=400, detail="q 和 thread_id 都要有")
        run = begin_run(thread_id)

        def worker() -> None:
            try:
                # 页面关掉只是没人听，这里继续跑。写库只在每个节点结束时占一下连接。
                for event in iter_sse_events(
                    agent, q, thread_id, run, lesson.rows_from_messages
                ):
                    run.publish(event)
            except Exception:
                traceback.print_exc()
                run.publish({"type": "done"})
            finally:
                if not run.started.is_set():
                    run.started.set()
                run.publish(None)
                finish_run(thread_id, run)

        threading.Thread(target=worker, daemon=True).start()
        return StreamingResponse(stream_run(run), media_type="text/event-stream")

    return app


def main() -> None:
    import os

    uri = os.environ.get("MYSQL_URI")
    if not uri:
        raise SystemExit("缺少 MYSQL_URI。在 .env 里写成 mysql://用户:密码@127.0.0.1:3306/stu_agent")
    lesson = load_lesson13()
    with PyMySQLSaver.from_conn_string(uri) as checkpointer:
        checkpointer.setup()
        agent = create_agent(
            model=make_chat_openai(),
            tools=[*LC_TOOLS, slow_search],
            system_prompt=PROMPT,
            checkpointer=checkpointer,
        )
        print("MySQL: stu_agent.checkpoints")
        print(f"Agent: http://127.0.0.1:{PORT}/chat")
        print("取消:  http://127.0.0.1:{0}/cancel?thread_id=...".format(PORT))
        print("页面:  http://127.0.0.1:5173")
        print("另一个终端: cd 10_web && npm run dev")
        uvicorn.run(build_app(agent, lesson), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
