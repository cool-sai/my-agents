# 第 08 课：基础 RAG 与 Agentic RAG

## 1. 模型为什么会瞎编

前七课的工具给的是实时事实（天气、计算）。还有一类知识模型**没见过**：你们公司的制度、产品说明、内部手册。

问「星辉卡怎么升级成银卡？」，预训练里没有这份虚构手册。不把原文塞进上下文，模型只能猜。

RAG 不是新模型。它就是：先找相关文档，再让模型根据文档说话。

```text
用户问题
   ↓
retrieve(问题) → 几条私有文档
   ↓
把文档放进 messages
   ↓
LLM 回答
```

向量数据库、embedding 只是 `retrieve` 的一种实现。本课用标签匹配，接口一样：`问题 → 几条文档`。

## 2. 四个实验

```bash
python 08_rag.py blind
python 08_rag.py naive
python 08_rag.py agentic
python 08_rag.py miss
```

建议先跑 `blind`，再跑 `naive`，看同一句「银卡怎么升级？退卡的钱怎么退？」答案变了没有。

手册里的硬事实是：

- 星辉卡消费满 **200** 元升银卡，银卡积分 **1.2** 倍
- 退卡须到店，余额 **30 天**内原路返回

### blind：不检索

只发用户问题。模型看不见手册，通常会说不知道，或编一套听起来像咖啡店的规则。编出来的数字对不上 200 / 1.2 / 30 天。

### naive：先搜再答

```python
hits = retrieve(question)
model.invoke([
    SystemMessage("只根据手册回答，没有就说没有"),
    HumanMessage(f"手册：\n{hits}\n\n用户问题：{question}"),
])
```

每次提问都检索。不需要 Agent，也不需要工具。这就是基础 RAG。

命中规则：文档带若干 `tags`，问题里出现该标签就加分，取 top 2。换 embedding 只换 `retrieve` 函数，后面的 messages 拼法不变。

### agentic：检索变成工具

```python
@tool
def search_handbook(query: str) -> str:
    """检索星林咖啡员工手册。"""
    ...

create_agent(..., tools=[search_handbook])
```

模型自己决定要不要查、用什么 query 查。查到的内容以 `ToolMessage` 回来，和 01 的天气工具同一条路。

适合：有的问题要查手册，有的不用；或要先改写检索词再查。

### miss：手册里没有

问「星林咖啡上市了吗？股票代码是多少？」。标签对不上，`retrieve` 返回空。提示词要求说「手册里没有」，不要编股票代码。

## 3. 对照

| | 基础 RAG (`naive`) | Agentic RAG |
|---|---|---|
| 谁决定检索 | 你的代码，每次都搜 | 模型，通过 tool_call |
| 文档怎么进上下文 | 你写进 HumanMessage | 框架写成 ToolMessage |
| 要不要 Agent | 不必 | `create_agent` + 检索工具 |
| 检索落空 | 你把「没有命中」塞进提示词 | 工具返回「没有相关条目」 |

两种都不是记忆。06 的 `messages` 记得的是**这轮对话说过什么**；RAG 每次按问题去知识库里**现查**。

## 4. 这一课的核心

```text
RAG = retrieve(问题) + 把文档放进 messages
基础 RAG：你的代码每次都检索
Agentic RAG：检索是工具，模型决定调不调
```

模型仍然不会「记住公司制度」。制度必须作为文本，出现在这一次调用的上下文里。
