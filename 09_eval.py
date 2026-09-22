#!/usr/bin/env python3
"""09 — 轨迹、测试、评估：同一段 messages 的三种读法。

08 的 Agent 跑完只有一段答案。看不出它有没有查手册、数字是不是手册里的。

1. trace：把 messages 按时间读成轨迹。要调模型。
2. test：不调模型。检索结果、评分器，用固定输入钉死。
3. eval：调模型。不要求逐字相同，只查工具和关键事实。

运行：
    python 09_eval.py test
    python 09_eval.py trace
    python 09_eval.py eval
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from common.llm import make_chat_openai

load_dotenv()

ALLERGY_QUESTION = "燕麦奶会过敏吗？"


def load_lesson08():
    """08_rag 不是合法模块名，按文件加载，复用手册和检索。"""
    path = Path(__file__).with_name("08_rag.py")
    spec = importlib.util.spec_from_file_location("lesson08", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content or "")


def one_line(text: str, limit: int = 72) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def trace_lines(messages: list) -> list[str]:
    lines: list[str] = []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            for call in tool_calls:
                args = json.dumps(call["args"], ensure_ascii=False)
                lines.append(f"model → {call['name']}({args})")
            continue
        name = getattr(message, "name", None)
        text = message_text(message)
        if name:
            lines.append(f"tool {name} ← {one_line(text)}")
        elif type(message).__name__ == "HumanMessage":
            lines.append(f"user: {one_line(text)}")
        elif text:
            lines.append(f"model: {one_line(text)}")
    return lines


def tool_names(messages: list) -> list[str]:
    names: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            names.append(call["name"])
    return names


def grade(messages: list, *, must_tool: str, answer_has: list[str]) -> tuple[bool, str]:
    """不比整段原文。只查：该调的工具调了没有，关键事实在不在。"""
    names = tool_names(messages)
    answer = message_text(messages[-1])
    missing = [bit for bit in answer_has if bit not in answer]
    reasons: list[str] = []
    if must_tool not in names:
        reasons.append(f"没有调用 {must_tool}，实际调用 {names or '无'}")
    if missing:
        reasons.append(f"回答缺少 {missing}")
    if reasons:
        return False, "；".join(reasons)
    return True, f"调用了 {must_tool}，回答含 {'、'.join(answer_has)}"


def ask(rag, question: str) -> list:
    agent = create_agent(
        model=make_chat_openai(),
        tools=[rag.search_handbook],
        system_prompt=rag.AGENTIC_PROMPT,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"]


def good_messages() -> list:
    return [
        HumanMessage(content="银卡怎么升级？退卡的钱怎么退？"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_handbook",
                    "args": {"query": "银卡 退卡"},
                    "id": "call_1",
                }
            ],
        ),
        ToolMessage(
            content="星辉卡消费满 200 元升级为银卡。退卡余额 30 天内原路返回。",
            tool_call_id="call_1",
            name="search_handbook",
        ),
        AIMessage(content="消费满 200 元升银卡，余额 30 天内原路返回。"),
    ]


def bad_messages() -> list:
    return [
        HumanMessage(content="银卡怎么升级？"),
        AIMessage(content="大概消费满 100 元就可以升级。"),
    ]


def check(name: str, ok: bool, detail: str) -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}")
    print(f"         {detail}")
    return ok


def run_trace(rag) -> None:
    print("场景: trace（把 messages 按时间读成轨迹）")
    question = rag.KNOWN_QUESTION
    print(f"用户: {question}")
    messages = ask(rag, question)
    print("\n轨迹:")
    for line in trace_lines(messages):
        print(f"  {line}")


def run_test(rag) -> None:
    print("场景: test（不调模型）")
    hits = rag.retrieve(rag.KNOWN_QUESTION)
    hit_ids = [doc["id"] for doc in hits]
    missed = rag.retrieve(rag.UNKNOWN_QUESTION)
    good_ok, good_detail = grade(
        good_messages(), must_tool="search_handbook", answer_has=["200", "30"]
    )
    bad_ok, bad_detail = grade(
        bad_messages(), must_tool="search_handbook", answer_has=["200"]
    )
    passed = [
        check("已知问题检索到会员条目", "member" in hit_ids, f"命中 {hit_ids or '无'}"),
        check("手册里没有的问题检索为空", not missed, f"命中 {[d['id'] for d in missed] or '无'}"),
        check("有工具、回答含事实 → 通过", good_ok, good_detail),
        check("没调工具 → 评分器必须失败", not bad_ok, bad_detail),
    ]
    if not all(passed):
        raise SystemExit(1)


def run_eval(rag) -> None:
    print("场景: eval（调模型，只查工具和关键事实）")
    cases = [
        {
            "name": "会员升级",
            "question": rag.KNOWN_QUESTION,
            "answer_has": ["200", "30"],
        },
        {
            "name": "燕麦过敏",
            "question": ALLERGY_QUESTION,
            "answer_has": ["坚果"],
        },
        {
            "name": "手册没有",
            "question": rag.UNKNOWN_QUESTION,
            "answer_has": ["没有"],
        },
    ]
    failed = False
    for case in cases:
        print(f"\n评估: {case['name']}")
        print(f"用户: {case['question']}")
        messages = ask(rag, case["question"])
        for line in trace_lines(messages):
            print(f"  {line}")
        ok, detail = grade(
            messages,
            must_tool="search_handbook",
            answer_has=case["answer_has"],
        )
        failed = not check(case["name"], ok, detail) or failed
    if failed:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=("trace", "test", "eval"),
        default="test",
        help="演示场景；默认 test（不调模型）",
    )
    return parser.parse_args()


def main() -> None:
    rag = load_lesson08()
    args = parse_args()
    if args.scenario == "trace":
        run_trace(rag)
    elif args.scenario == "test":
        run_test(rag)
    else:
        run_eval(rag)


if __name__ == "__main__":
    main()
