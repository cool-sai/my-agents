#!/usr/bin/env python3
"""04 — 使用 Pydantic 约束模型的结构化输出。

这一课包含三个小实验：

1. validation：不调用模型，只观察 Pydantic 如何校验普通 Python 数据。
2. model：给单次模型调用增加输出结构。
3. agent：让 create_agent 的最终结果符合相同结构。

运行：
    python 04_structured_output.py validation
    python 04_structured_output.py model
    python 04_structured_output.py agent
"""

from __future__ import annotations

import argparse
import json
from typing import Literal

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from common.llm import make_chat_openai

load_dotenv()

DEFAULT_TEXT = (
    "我正在学习 LangChain，已经理解了四种消息、工具绑定、"
    "手写 Tool Calling 循环和 create_agent，但还没有学结构化输出。"
)


class LearningAssessment(BaseModel):
    """对一段 LangChain 学习进展描述的结构化评估。"""

    topic: str = Field(description="当前学习主题")
    completed: list[str] = Field(description="已经掌握的知识点")
    missing: list[str] = Field(description="还未掌握的知识点")
    next_step: str = Field(description="下一步最具体的学习行动")
    confidence: int = Field(
        description="对评估结果的信心，范围是 0 到 100",
        ge=0,
        le=100,
    )
    status: Literal["not_started", "learning", "completed"] = Field(
        description="当前主题的学习状态"
    )


def show_result(result: LearningAssessment) -> None:
    """同时展示 Python 对象和可传给前端/API 的 JSON。"""
    print("\nPydantic 对象：")
    print(result)
    print("\nJSON：")
    print(result.model_dump_json(indent=2))


def run_validation_demo() -> None:
    """纯本地演示：Pydantic 会拒绝不符合约束的数据。"""
    valid_data = {
        "topic": "LangChain 结构化输出",
        "completed": ["理解自由文本和结构化数据的区别"],
        "missing": ["with_structured_output", "ToolStrategy"],
        "next_step": "运行 model 示例",
        "confidence": 90,
        "status": "learning",
    }
    show_result(LearningAssessment.model_validate(valid_data))

    invalid_data = {
        **valid_data,
        "confidence": 120,
        "status": "almost_done",
    }
    print("\n故意传入错误数据（confidence=120、status=almost_done）：")
    try:
        LearningAssessment.model_validate(invalid_data)
    except ValidationError as exc:
        print(exc)


def run_model_demo(text: str) -> None:
    """单次模型调用：模型输出直接解析成 LearningAssessment。"""
    model = make_chat_openai()
    structured_model = model.with_structured_output(
        LearningAssessment,
        # json_mode 保证输出合法 JSON，再由 Pydantic 校验字段和约束；
        # 对不支持强制调用指定工具的模型也更兼容。
        method="json_mode",
    )
    schema = json.dumps(
        LearningAssessment.model_json_schema(),
        ensure_ascii=False,
    )
    result = structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "你是 LangChain 学习教练。根据用户描述如实评估，"
                    "不要虚构用户已经掌握的内容。"
                    "必须只输出符合以下 JSON Schema 的 JSON，不要输出解释或 Markdown："
                    f"\n{schema}"
                )
            ),
            HumanMessage(content=text),
        ]
    )
    show_result(result)


def run_agent_demo(text: str) -> None:
    """Agent 调用：最终结构化结果位于 structured_response。"""
    agent = create_agent(
        # ToolStrategy 需要强制调用输出工具，所以在这个示例中关闭思考模式，
        # 避免部分模型的 Thinking mode 与 tool_choice 冲突。
        model=make_chat_openai(thinking=False),
        tools=[],
        system_prompt=(
            "你是 LangChain 学习教练。根据用户描述如实评估，"
            "不要虚构用户已经掌握的内容。"
            "最后必须通过 LearningAssessment 输出工具提交评估结果。"
        ),
        # ToolStrategy 把 Pydantic schema 转成一种特殊的“输出工具”。
        response_format=ToolStrategy(LearningAssessment),
    )
    state = agent.invoke(
        {"messages": [{"role": "user", "content": text}]}
    )
    result = state["structured_response"]
    show_result(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "demo",
        nargs="?",
        choices=("validation", "model", "agent"),
        default="validation",
        help="要运行的实验；默认 validation（无需 API）",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="要评估的学习进展；不填则使用内置示例",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = " ".join(args.text) if args.text else DEFAULT_TEXT

    if args.demo == "validation":
        run_validation_demo()
    elif args.demo == "model":
        run_model_demo(text)
    else:
        run_agent_demo(text)


if __name__ == "__main__":
    main()
