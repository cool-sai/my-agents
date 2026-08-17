"""统一的 OpenAI 兼容 LLM 客户端配置。"""

from __future__ import annotations

import os
import warnings

import httpx
from openai import OpenAI


def _require_api_key() -> str:
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("GLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        raise SystemExit(
            "缺少模型 API Key。\n"
            "请在 .env 中设置通用的 LLM_API_KEY，或厂商专用的 "
            "GLM_API_KEY / DEEPSEEK_API_KEY。"
        )
    return api_key


def get_base_url() -> str:
    # 默认使用 DeepSeek；也可通过 .env 切换到其他 OpenAI 兼容接口。
    return os.getenv("LLM_BASE_URL", "https://api.deepseek.com")


def get_model() -> str:
    return os.getenv("LLM_MODEL", "deepseek-v4-flash")


def _ssl_verify() -> bool:
    """是否校验证书。走本地代理（Clash 等）时常需关掉。

    .env:
      LLM_SSL_VERIFY=false
    """
    raw = os.getenv("LLM_SSL_VERIFY", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _http_client() -> httpx.Client:
    verify = _ssl_verify()
    if not verify:
        warnings.warn(
            "LLM_SSL_VERIFY=false：已关闭证书校验（仅本地学习用；"
            "常见原因是 HTTPS 代理使用自签证书）。",
            stacklevel=2,
        )
    return httpx.Client(verify=verify, timeout=60.0)


def make_openai_client() -> OpenAI:
    """原生 openai SDK 客户端（01 用）。"""
    return OpenAI(
        api_key=_require_api_key(),
        base_url=get_base_url(),
        http_client=_http_client(),
    )


def make_chat_openai(*, thinking: bool | None = None):
    """LangChain ChatOpenAI（02 / 03 / 04 用）。

    thinking 仅用于支持该参数的模型；None 表示使用服务端默认值。
    """
    from langchain_openai import ChatOpenAI

    extra_body = None
    if thinking is not None:
        extra_body = {
            "thinking": {
                "type": "enabled" if thinking else "disabled",
            }
        }

    return ChatOpenAI(
        model=get_model(),
        api_key=_require_api_key(),
        base_url=get_base_url(),
        temperature=0,
        http_client=_http_client(),
        extra_body=extra_body,
    )
