#!/usr/bin/env python3
"""10 — 把 07 的 SSE 留给浏览器。Agent 不动，服务一直开着。

07 的 sse 场景自己当客户端，收完就关服务。这一课让服务停在那里，
等 Vite 页面用 EventSource 来连。

运行（两个终端）：
    python 10_web.py
    cd 10_web && npm install && npm run dev

浏览器打开 http://127.0.0.1:5173
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import uvicorn
from fastapi.middleware.cors import CORSMiddleware


def load_lesson07():
    """07_streaming 不是合法模块名，按文件加载，复用同一条 SSE。"""
    path = Path(__file__).with_name("07_streaming.py")
    spec = importlib.util.spec_from_file_location("lesson07", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    lesson = load_lesson07()
    # 页面在 :5173，Agent 在 :8765。浏览器要读另一端口的响应，必须带这个头。
    lesson.app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    port = lesson.SSE_PORT
    print(f"Agent: http://127.0.0.1:{port}/chat")
    print("页面:  http://127.0.0.1:5173")
    print("另一个终端: cd 10_web && npm install && npm run dev")
    uvicorn.run(lesson.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
