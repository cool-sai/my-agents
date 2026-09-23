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
| `05_agent_middleware.py` | **中间件**：动态提示、权限、错误处理、调用限制 |
| `05_agent_middleware.md` | 第 05 课讲义与运行场景 |
| `06_session_memory.py` | **短期记忆**：自己保存 messages / checkpointer + thread_id |
| `06_session_memory.md` | 第 06 课讲义与运行场景 |
| `07_streaming.py` | **流式输出**：invoke / 逐步 updates / token / FastAPI + SSE |
| `07_streaming.md` | 第 07 课讲义与运行场景 |
| `08_rag.py` | **RAG**：不检索 / 先搜再答 / 检索当工具 / 手册没有 |
| `08_rag.md` | 第 08 课讲义与运行场景 |
| `09_eval.py` | **轨迹 / 测试 / 评估**：读 messages、不调模型的测试、只查工具和事实 |
| `09_eval.md` | 第 09 课讲义与运行场景 |
| `10_web.py` | **页面**：把 07 的 SSE 留给浏览器，服务一直开着 |
| `10_web/` | Vite + React 页面，只用 EventSource 收事件 |
| `10_web.md` | 第 10 课讲义与运行场景 |
| `13_session.py` | **会话**：PyMySQLSaver，按 thread_id 把快照写进本机 MySQL |
| `13_session.md` | 第 13 课讲义 |
| `14_cancel.py` | **取消**：停掉正在跑的一轮，包括还没做完的工具 |
| `14_cancel.md` | 第 14 课讲义 |

建议阅读/运行顺序：`01 → 03 → 02 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 13 → 14`。

## 准备

```bash
cd /Users/bytedance/Desktop/Agents/stu
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY，并选择兼容 OpenAI 协议的接口和模型
```

当前示例配置使用 **GLM** 的 OpenAI 兼容接口
（`https://open.bigmodel.cn/api/paas/v4`，模型 `glm-4.7-flash`）。
也可以把 `LLM_BASE_URL` 和 `LLM_MODEL` 换回 DeepSeek；配置见
`common/llm.py` 与 `.env.example`。

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

# Middleware：访客拒绝 / 管理员放行 / 工具错误
python 05_agent_middleware.py guest
python 05_agent_middleware.py admin
python 05_agent_middleware.py error

# 短期记忆：失忆 / 手写保存 / checkpointer / 多线程隔离
python 06_session_memory.py forget
python 06_session_memory.py manual
python 06_session_memory.py remember
python 06_session_memory.py threads

# 流式：整段等待 / 每一步 / token / FastAPI+SSE
python 07_streaming.py invoke
python 07_streaming.py updates
python 07_streaming.py tokens
python 07_streaming.py sse

# RAG：不检索 / 先搜再答 / 检索当工具 / 手册没有
python 08_rag.py blind
python 08_rag.py naive
python 08_rag.py agentic
python 08_rag.py miss

# 轨迹 / 测试 / 评估（test 不调模型）
python 09_eval.py test
python 09_eval.py trace
python 09_eval.py eval

# 页面收同一条 SSE（两个终端）
python 10_web.py
cd 10_web && npm install && npm run dev

# 会话写进本机 MySQL（不要和 10_web.py 同时开，端口都是 8765）
python 13_session.py

# 取消正在跑的一轮（不要和 10_web.py、13_session.py 同时开）
python 14_cancel.py
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
| 多轮记忆 | 自己保存 `messages` 列表 | `checkpointer` + `thread_id` |
| 流式输出 | `create(..., stream=True)` | `agent.stream(stream_mode=...)` |
| 私有知识 | 检索结果写进 messages | 基础 RAG 塞提示词；Agentic RAG 用检索工具 |
| 怎么知道答对了 | 自己看打印 | trace 读 messages；test 不调模型；eval 只查工具和关键词 |
| 接到页面 | curl 收 SSE | 浏览器 EventSource 收同一条流 |
| 取消这一轮 | 客户端不听了，循环还在跑 | `/cancel` 放下旗，工具看见就停 |

## 你在学什么

1. **LLM 不会执行函数**  
   它只输出结构化的「我想调用 `get_weather(city=北京)`」。  
   执行函数、把结果塞回上下文，永远是应用层的事。

2. **Agent = 这个循环的 harness**  
   LangChain / LangGraph 的价值：消息类型、tool schema 生成、循环、中间件、记忆、流式……  
   不是换了一种「智能」，是换了一种「编排方式」。

3. **先能 debug 原生 loop，再敢用框架**  
   出问题先问：模型有没有发出 tool_call？参数对不对？tool 结果有没有正确回传？

## 下一步

基础 1–12 已完成。第 13 课把会话按 `thread_id` 写进本机 MySQL。第 14 课可以取消正在跑的一轮，包括还没做完的工具。再往下是第 15 课：会失败的真工具，有副作用的动作先等人点头。

完整顺序和每条怎么算过，见 `学习目标.md`。

官方文档：https://docs.langchain.com/oss/python/langchain/agents
