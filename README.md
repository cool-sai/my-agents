# LangChain 学习：先原生，再框架

目标：先搞懂 **Agent 本质是「模型 + 工具 + 循环」**，再看 LangChain 把哪几层帮你写了。

```
用户问题
   ↓
┌──────────────────────────────┐
│  while True:                 │
│    LLM(messages, tools)      │  ← 模型：决定调不调工具
│    若无 tool_calls → 返回    │
│    执行 tools                │  ← 你的代码：真干活
│    把结果塞回 messages       │
└──────────────────────────────┘
```

## 目录

| 文件 | 作用 |
|------|------|
| `common/tools.py` | 业务工具 + OpenAI 风格 schema（两套共用） |
| `common/lc_tools.py` | LangChain `@tool` 薄包装 |
| `01_raw_agent.py` | **原生**：`openai` SDK 手写 loop |
| `03_langchain_manual_loop.py` | **过渡**：LangChain 消息/工具，loop 仍手写 |
| `02_langchain_agent.py` | **框架**：`create_agent` 一行搞定 loop |
| `04_structured_output.py` | **结构化输出**：Pydantic + 模型 / Agent |
| `04_structured_output.md` | 第 04 课讲义与课后练习 |

建议阅读/运行顺序：`01 → 03 → 02`。

## 准备

```bash
cd /Users/bytedance/Desktop/Agents/stu
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（https://platform.deepseek.com/api_keys）
```

默认走 **DeepSeek** OpenAI 兼容接口（`https://api.deepseek.com`，模型 `deepseek-v4-flash`）。
配置见 `common/llm.py` 与 `.env`。

## 运行

```bash
# 原生 agent
python 01_raw_agent.py
python 01_raw_agent.py "上海天气如何？算一下 99/3"

# 过渡：bind_tools + 手写 loop
python 03_langchain_manual_loop.py

# LangChain create_agent
python 02_langchain_agent.py

# Pydantic 结构化输出（按顺序运行）
python 04_structured_output.py validation
python 04_structured_output.py model
python 04_structured_output.py agent
```

默认问题会同时触发：天气 + 计算器 + 时间（多 tool call）。

## 概念对照表

| 概念 | 原生 (`01`) | LangChain (`02` / `03`) |
|------|-------------|-------------------------|
| 模型客户端 | `OpenAI(base_url=...)` | `ChatOpenAI(base_url=...)` |
| 工具说明书 | `OPENAI_TOOLS` JSON | `@tool` + docstring / 类型注解 |
| 绑定工具 | `tools=OPENAI_TOOLS` | `model.bind_tools(tools)` 或 `create_agent(..., tools=)` |
| 对话状态 | `list[dict]` messages | `HumanMessage` / `AIMessage` / `ToolMessage` |
| 工具结果 | `{"role":"tool", "tool_call_id":...}` | `ToolMessage(tool_call_id=...)` |
| Agent 循环 | 自己写 `while` | `create_agent` 内部（基于 LangGraph） |
| 系统提示 | system message | `system_prompt=` |

## 你在学什么

1. **LLM 不会执行函数**  
   它只输出结构化的「我想调用 `get_weather(city=北京)`」。  
   执行函数、把结果塞回上下文，永远是应用层的事。

2. **Agent = 这个循环的 harness**  
   LangChain / LangGraph 的价值：消息类型、tool schema 生成、循环、中间件、记忆、流式……  
   不是换了一种「智能」，是换了一种「编排方式」。

3. **先能 debug 原生 loop，再敢用框架**  
   出问题先问：模型有没有发出 tool_call？参数对不对？tool 结果有没有正确回传？

## 下一步（按需）

- 给 `create_agent` 加 `checkpointer` 做多轮记忆  
- 流式输出 `agent.stream` / `stream_events`  
- 换真实工具（HTTP API、数据库、检索）  
- 进 LangGraph 自己画图（多 agent、人机审批）

官方文档：https://docs.langchain.com/oss/python/langchain/agents
