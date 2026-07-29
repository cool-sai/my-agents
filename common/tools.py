"""演示用工具：两套 agent 共用同一业务逻辑。

学习点：
- 工具 = 普通 Python 函数 + 给模型看的「说明书」(name / description / parameters)
- 模型不会直接执行代码，只会输出「我想调哪个工具、参数是什么」
- 真正执行函数的是你的代码（agent loop）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 1) 纯业务函数（框架无关）
# ---------------------------------------------------------------------------

def get_weather(city: str) -> str:
    """查询城市天气（演示用假数据，不访问外网）。"""
    catalog = {
        "北京": "晴，18°C，北风 2 级",
        "上海": "多云，22°C，东南风 3 级",
        "深圳": "阵雨，27°C，湿度 80%",
        "杭州": "阴，20°C，微风",
        "beijing": "Sunny, 18°C, light north wind",
        "shanghai": "Cloudy, 22°C, SE wind level 3",
    }
    key = city.strip()
    # 简单归一化
    weather = catalog.get(key) or catalog.get(key.lower())
    if weather is None:
        return f"暂无「{city}」的天气数据（演示库只含北京/上海/深圳/杭州）"
    return f"{city} 当前天气：{weather}"


def calculator(expression: str) -> str:
    """计算数学表达式，仅允许数字和 + - * / ( ) . 空格。"""
    allowed = set("0123456789+-*/(). ")
    expr = expression.strip()
    if not expr:
        return "错误：表达式为空"
    if any(ch not in allowed for ch in expr):
        return "错误：只允许数字和运算符 + - * / ( )"
    try:
        # 演示用 eval；生产环境请用 ast 安全求值
        result = eval(expr, {"__builtins__": {}}, {})
        return f"{expr} = {result}"
    except Exception as e:  # noqa: BLE001 - 演示时把错误回传给模型
        return f"计算失败：{e}"


def get_current_time(timezone_name: str = "UTC") -> str:
    """返回当前时间（演示只支持 UTC / CST）。"""
    name = timezone_name.strip().upper()
    if name in {"UTC", "GMT"}:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d %H:%M:%S UTC")
    if name in {"CST", "ASIA/SHANGHAI", "BEIJING", "CN"}:
        # CST = UTC+8
        from datetime import timedelta

        now = datetime.now(timezone.utc) + timedelta(hours=8)
        return now.strftime("%Y-%m-%d %H:%M:%S CST(UTC+8)")
    return f"不支持时区「{timezone_name}」，请用 UTC 或 CST"


# 函数注册表：name -> callable
TOOL_FUNCS: dict[str, Callable[..., str]] = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
}


def run_tool(name: str, arguments: dict[str, Any] | str) -> str:
    """统一执行入口：根据工具名 + JSON 参数调用函数。"""
    if name not in TOOL_FUNCS:
        return f"未知工具：{name}"
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as e:
            return f"参数 JSON 解析失败：{e}"
    if not isinstance(arguments, dict):
        return "参数必须是 JSON 对象"
    try:
        return TOOL_FUNCS[name](**arguments)
    except TypeError as e:
        return f"参数错误：{e}"
    except Exception as e:  # noqa: BLE001
        return f"工具执行异常：{e}"


# ---------------------------------------------------------------------------
# 2) OpenAI / xAI 风格的 tools schema（原生 agent 用）
# ---------------------------------------------------------------------------

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的当前天气（演示假数据）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，例如 北京、上海、深圳、杭州",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式，支持 + - * / 和括号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，例如 (12+8)*3",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_name": {
                        "type": "string",
                        "description": "时区：UTC 或 CST",
                        "default": "UTC",
                    }
                },
                "required": [],
            },
        },
    },
]


SYSTEM_PROMPT = (
    "你是一个会使用工具的助手。"
    "需要查天气、做计算、或看时间时，请调用对应工具；"
    "拿到工具结果后再用中文给出简洁最终回答。"
)
