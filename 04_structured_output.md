# 第 04 课：Pydantic 结构化输出

## 1. 这一步解决什么问题

普通模型返回的是自由文本：

```text
你已经掌握消息和工具调用，建议下一步学习结构化输出。
```

人能读懂，但程序很难稳定地提取字段。我们希望程序拿到：

```json
{
  "topic": "LangChain 结构化输出",
  "completed": ["消息类型", "工具调用"],
  "missing": ["Pydantic 结构化输出"],
  "next_step": "练习 with_structured_output",
  "confidence": 90,
  "status": "learning"
}
```

Pydantic 的作用是定义并验证这份“数据合同”：

- 字段是否存在；
- 字段类型是否正确；
- 数值是否在指定范围；
- 字符串是否属于允许的枚举值。

它不是提示词，也不是模型。LangChain 会把 Pydantic schema 告诉模型，再把模型返回的数据交给 Pydantic 校验。

## 2. 先运行本地校验

```bash
python 04_structured_output.py validation
```

观察两件事：

1. 合法字典被转换成 `LearningAssessment` 对象；
2. `confidence=120` 和非法 `status` 会触发 `ValidationError`。

重点阅读：

- `LearningAssessment` 中的类型注解；
- `Field(description=...)` 给模型看的字段说明；
- `ge=0, le=100` 和 `Literal[...]` 对数据施加的硬约束。

## 3. 给单次模型调用增加结构

```bash
python 04_structured_output.py model
```

核心代码：

```python
structured_model = model.with_structured_output(
    LearningAssessment,
    method="json_mode",
)
result = structured_model.invoke(messages)
```

此时 `result` 不再是 `AIMessage` 或字符串，而是通过校验的
`LearningAssessment` 实例。

DeepSeek V4 默认启用 Thinking mode，而该模式不接受 LangChain
`function_calling` 方法发出的“强制调用指定工具”请求。因此，本项目的单次
模型示例使用 DeepSeek 官方支持的 JSON mode，并在系统提示词中附上完整
JSON Schema。JSON mode 保证返回合法 JSON，Pydantic 继续负责字段校验。

## 4. 给 Agent 的最终答案增加结构

```bash
python 04_structured_output.py agent
```

核心代码：

```python
agent = create_agent(
    model=make_chat_openai(thinking=False),
    tools=[],
    response_format=ToolStrategy(LearningAssessment),
)
state = agent.invoke({"messages": [...]})
result = state["structured_response"]
```

`ToolStrategy` 会把 schema 转换成一种特殊的输出工具。模型通过工具调用
提交字段，LangChain 负责校验；如果数据不合法，默认会把错误反馈给模型并让它重试。

这里仅为 Agent 示例关闭 DeepSeek Thinking mode，因为 `ToolStrategy` 必须
强制模型调用输出工具，而当前 Thinking mode 不支持这种 `tool_choice`。

## 5. 两种写法怎么选

| 场景 | 写法 |
|---|---|
| 只调用一次模型做分类、抽取、信息整理 | `model.with_structured_output(...)` |
| Agent 需要先调用业务工具，再返回固定结构 | `create_agent(..., response_format=...)` |
| 模型厂商原生支持严格 JSON Schema | `ProviderStrategy` |
| 模型支持强制 Tool Calling | `ToolStrategy` / `method="function_calling"` |
| DeepSeek Thinking mode 下的单次抽取 | `method="json_mode"` + 提示词中的 schema |

本项目的 Agent 示例仍使用 `ToolStrategy`，它会把前三课学过的 Tool Calling
机制用于提交最终结构。

## 6. 课后练习

把 `LearningAssessment` 改成会议待办提取模型：

```python
class ActionItem(BaseModel):
    task: str
    assignee: str | None
    priority: Literal["low", "medium", "high"]
```

再定义包含 `list[ActionItem]` 的 `MeetingSummary`，从一段会议文字中提取待办。
