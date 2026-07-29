"""LangChain @tool 包装：业务逻辑仍在 common.tools。"""

from langchain.tools import tool

from common.tools import (
    calculator as _calculator,
    get_current_time as _get_current_time,
    get_weather as _get_weather,
)


@tool
def get_weather(city: str) -> str:
    """查询某个城市的当前天气（演示假数据）。"""
    return _get_weather(city)


@tool
def calculator(expression: str) -> str:
    """计算数学表达式，支持 + - * / 和括号。"""
    return _calculator(expression)


@tool
def get_current_time(timezone_name: str = "UTC") -> str:
    """获取当前时间。timezone_name 用 UTC 或 CST。"""
    return _get_current_time(timezone_name)


LC_TOOLS = [get_weather, calculator, get_current_time]
