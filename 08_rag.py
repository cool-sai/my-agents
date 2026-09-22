#!/usr/bin/env python3
"""08 — RAG：先检索私有文档，再让模型根据文档回答。

四个实验：

1. blind：不给手册，模型只能猜或说不知道。
2. naive：每次先 retrieve，把命中文档塞进提示词，再调用模型。
3. agentic：retrieve 收成工具，模型自己决定要不要查。
4. miss：问题在手册里没有，检索为空，模型应说不知道。

运行：
    python 08_rag.py blind
    python 08_rag.py naive
    python 08_rag.py agentic
    python 08_rag.py miss
"""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from common.llm import make_chat_openai

load_dotenv()

# 虚构手册：预训练里不可能有「星辉卡满 200 升银卡」这种细节。
DOCS = [
    {
        "id": "hours",
        "title": "营业时间",
        "tags": ["营业", "时间", "几点", "开门", "打烊", "闭店", "检修"],
        "text": "门店 07:30-21:30，厨房 08:00-20:30。每周二闭店检修。",
    },
    {
        "id": "member",
        "title": "会员与退卡",
        "tags": ["会员", "银卡", "星辉", "积分", "退卡", "余额", "升级"],
        "text": "星辉卡消费满 200 元升级为银卡，银卡积分 1.2 倍。退卡须到店办理，余额 30 天内原路返回。",
    },
    {
        "id": "refund",
        "title": "退款规则",
        "tags": ["退款", "取消", "后悔", "储值", "转赠"],
        "text": "饮品开始制作后不退。未制作可在下单 5 分钟内取消。储值卡不兑现，可转赠一次。",
    },
    {
        "id": "allergy",
        "title": "过敏原",
        "tags": ["过敏", "燕麦", "坚果", "核桃"],
        "text": "燕麦奶走独立设备，仍可能有坚果微量。核桃蛋糕含坚果。",
    },
]

KNOWN_QUESTION = "银卡怎么升级？退卡的钱怎么退？"
UNKNOWN_QUESTION = "星林咖啡上市了吗？股票代码是多少？"

NAIVE_PROMPT = (
    "你是星林咖啡客服。只根据下面提供的手册条目回答。"
    "手册没有的信息必须说「手册里没有」，不要编造。"
)
BLIND_PROMPT = (
    "你是星林咖啡客服。你没有内部手册。"
    "不确定的制度不要编造，直接说不知道。"
)
AGENTIC_PROMPT = (
    "你是星林咖啡客服。店内制度、会员、退款必须先调用 search_handbook。"
    "只根据工具返回的手册条目回答；工具说没有相关条目，就告诉用户手册里没有，不要编。"
)


def score_doc(query: str, doc: dict) -> int:
    return sum(1 for tag in doc["tags"] if tag in query)


def retrieve(query: str, k: int = 2) -> list[dict]:
    ranked = sorted(
        ((score_doc(query, doc), doc) for doc in DOCS),
        key=lambda item: item[0],
        reverse=True,
    )
    return [doc for points, doc in ranked if points > 0][:k]


def format_hits(hits: list[dict]) -> str:
    if not hits:
        return "（没有命中）"
    return "\n\n".join(
        f"[{doc['id']}] {doc['title']}\n{doc['text']}" for doc in hits
    )


def print_hits(query: str, hits: list[dict]) -> None:
    print(f"\n检索: {query}")
    if not hits:
        print("命中: 无")
        return
    print(f"命中 {len(hits)} 条:")
    for doc in hits:
        print(f"  [{doc['id']}] {doc['title']}  score={score_doc(query, doc)}")
        print(f"    {doc['text']}")


def last_text(messages: list) -> str:
    last = messages[-1]
    return getattr(last, "content", None) or str(last)


def run_blind(question: str) -> None:
    print("场景: blind（不检索，模型看不见手册）")
    print(f"用户: {question}")
    model = make_chat_openai()
    result = model.invoke(
        [SystemMessage(content=BLIND_PROMPT), HumanMessage(content=question)]
    )
    print(f"\n>>> {result.content}")


def answer_with_docs(question: str) -> None:
    hits = retrieve(question)
    print_hits(question, hits)
    context = format_hits(hits)
    model = make_chat_openai()
    result = model.invoke(
        [
            SystemMessage(content=NAIVE_PROMPT),
            HumanMessage(content=f"手册：\n{context}\n\n用户问题：{question}"),
        ]
    )
    print(f"\n>>> {result.content}")


def run_naive(question: str) -> None:
    print("场景: naive（先 retrieve，再把文档塞进提示词）")
    print(f"用户: {question}")
    answer_with_docs(question)


def run_miss(question: str) -> None:
    print("场景: miss（问题不在手册里，检索应为空）")
    print(f"用户: {question}")
    answer_with_docs(question)


@tool
def search_handbook(query: str) -> str:
    """检索星林咖啡员工手册。店内制度、会员、退款、过敏原问这个。"""
    hits = retrieve(query)
    print_hits(query, hits)
    if not hits:
        return "知识库没有相关条目。"
    return format_hits(hits)


def run_agentic(question: str) -> None:
    print("场景: agentic（检索是工具，模型自己决定要不要查）")
    print(f"用户: {question}")
    agent = create_agent(
        model=make_chat_openai(),
        tools=[search_handbook],
        system_prompt=AGENTIC_PROMPT,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for message in result["messages"]:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                args = json.dumps(tc["args"], ensure_ascii=False)
                print(f"  → {tc['name']}({args})")
    print(f"\n>>> {last_text(result['messages'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=("blind", "naive", "agentic", "miss"),
        default="blind",
        help="演示场景；默认 blind",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.scenario == "blind":
        run_blind(KNOWN_QUESTION)
    elif args.scenario == "naive":
        run_naive(KNOWN_QUESTION)
    elif args.scenario == "agentic":
        run_agentic(KNOWN_QUESTION)
    else:
        run_miss(UNKNOWN_QUESTION)


if __name__ == "__main__":
    main()
