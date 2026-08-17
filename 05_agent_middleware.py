#!/usr/bin/env python3
"""05 — 使用 Middleware 让 Agent 具备动态提示、权限和错误边界。

三个场景：

1. guest：访客尝试删除笔记，被权限中间件阻止。
2. admin：管理员执行同一工具，允许通过。
3. error：查询不存在的订单，工具异常被转换成 ToolMessage 交给模型处理。

运行：
    python 05_agent_middleware.py guest
    python 05_agent_middleware.py admin
    python 05_agent_middleware.py error
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    dynamic_prompt,
    wrap_tool_call,
)
from langchain.tools import tool
from langchain_core.messages import ToolMessage

from common.llm import make_chat_openai

load_dotenv()


class AgentContext(TypedDict):
    """由应用传入、不会让用户在消息里自行伪造的运行时身份。"""

    user_name: str
    user_role: Literal["guest", "admin"]


ORDER_CATALOG = {
    "order-1001": "已付款，预计明天送达",
    "order-1002": "运输中，当前位于杭州分拨中心",
}


@tool
def lookup_order(order_id: str) -> str:
    """查询订单状态。订单号格式示例：order-1001。"""
    if order_id not in ORDER_CATALOG:
        raise ValueError("订单不存在")
    return f"{order_id}：{ORDER_CATALOG[order_id]}"


@tool
def delete_note(note_id: str) -> str:
    """删除指定笔记。这是演示工具，不会真的修改任何外部数据。"""
    return f"演示操作完成：已删除笔记 {note_id}"


@dynamic_prompt
def role_aware_prompt(request: ModelRequest[AgentContext]) -> str:
    """每次调用模型前，根据可信运行时上下文生成 SystemMessage。"""
    context = request.runtime.context
    user_name = context.get("user_name", "用户")
    user_role = context.get("user_role", "guest")
    print(f"[middleware/dynamic_prompt] user={user_name}, role={user_role}")

    return (
        "你是一个简洁的中文业务助手。"
        f"当前用户是 {user_name}，应用确认的角色是 {user_role}。"
        "需要查询订单或删除笔记时必须调用工具，不要自己编造结果。"
        "如果工具返回权限或执行错误，不要重复调用同一个失败工具，"
        "而要向用户清楚说明原因。"
    )


@wrap_tool_call
def guard_and_handle_tool(request, handler):
    """在工具外包一层：先鉴权，再执行，并把预期异常变成 ToolMessage。"""
    tool_call = request.tool_call
    tool_name = tool_call["name"]
    context = request.runtime.context
    user_role = context.get("user_role", "guest")

    print(f"[middleware/tool] before name={tool_name}, role={user_role}")

    # 权限控制：不调用 handler，就意味着真实工具根本没有执行。
    if tool_name == "delete_note" and user_role != "admin":
        print("[middleware/tool] denied: delete_note requires admin")
        return ToolMessage(
            content="权限不足：delete_note 只允许 admin 调用，请不要重试。",
            tool_call_id=tool_call["id"],
            name=tool_name,
            status="error",
        )

    try:
        result = handler(request)
        print(f"[middleware/tool] after name={tool_name}, status=success")
        return result
    except ValueError:
        # 只暴露可安全展示的业务错误，不把内部异常细节直接发给模型。
        print(f"[middleware/tool] after name={tool_name}, status=error")
        return ToolMessage(
            content="订单查询失败：订单不存在，请让用户检查订单号。",
            tool_call_id=tool_call["id"],
            name=tool_name,
            status="error",
        )


SCENARIOS: dict[str, tuple[str, Literal["guest", "admin"], str]] = {
    "guest": (
        "小林",
        "guest",
        "请删除笔记 note-123，并告诉我结果。",
    ),
    "admin": (
        "管理员小周",
        "admin",
        "请删除笔记 note-123，并告诉我结果。",
    ),
    "error": (
        "小林",
        "guest",
        "请查询订单 order-9999 的状态。",
    ),
}


def run_agent(
    user_input: str,
    *,
    user_name: str,
    user_role: Literal["guest", "admin"],
    verbose: bool = True,
) -> str:
    agent = create_agent(
        model=make_chat_openai(),
        tools=[lookup_order, delete_note],
        # 三个中间件运行时兼容；库的 State/Context 泛型是 invariant，检查器无法对齐。
        middleware=cast(
            Sequence[AgentMiddleware[Any, AgentContext]],
            [
                role_aware_prompt,
                guard_and_handle_tool,
                # 防止模型反复调用失败工具造成死循环和额外费用。
                ModelCallLimitMiddleware(run_limit=4, exit_behavior="end"),
            ],
        ),
        context_schema=AgentContext,
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        context={"user_name": user_name, "user_role": user_role},
    )

    messages = result["messages"]
    if verbose:
        print("\n--- Agent 消息轨迹 ---")
        for message in messages:
            kind = type(message).__name__
            content = getattr(message, "content", "")
            tool_calls = getattr(message, "tool_calls", None)
            status = getattr(message, "status", None)
            if tool_calls:
                print(f"[{kind}] tool_calls={tool_calls}")
            elif status:
                print(f"[{kind} status={status}] {content}")
            else:
                print(f"[{kind}] {content}")

    last = messages[-1]
    return getattr(last, "content", None) or str(last)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=tuple(SCENARIOS),
        default="guest",
        help="演示场景；默认 guest",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="可选的自定义问题；身份仍由 scenario 决定",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_name, user_role, default_input = SCENARIOS[args.scenario]
    user_input = " ".join(args.text) if args.text else default_input

    print(f"场景: {args.scenario}")
    print(f"用户: {user_name} ({user_role})")
    print(f"问题: {user_input}\n")
    answer = run_agent(
        user_input,
        user_name=user_name,
        user_role=user_role,
    )
    print(f"\n>>> {answer}")


if __name__ == "__main__":
    main()
