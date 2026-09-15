# 第 07 课：流式输出

## 1. 前六课缺了什么

到目前为止，对话都是 `invoke`：整个 Agent loop 跑完，才把最终文本一次性给你。

中间其实已经发生了：模型决定调工具 → 工具执行 → 模型再写答案。用户看不见，只能盯着空白等。

流式不是新 loop。还是 01 里那个 while，只是每走一步（或每个 token）就 `yield` 出去。

```text
invoke :  [............全部跑完............] → 一次返回
stream :  模型 → yield → 工具 → yield → 文字 token token token
```

## 2. 四个实验

```bash
python 07_streaming.py invoke
python 07_streaming.py updates
python 07_streaming.py tokens
python 07_streaming.py sse
```

建议先跑 `invoke`，再跑 `updates`，对比「结束前有没有输出」。

### invoke：等全部结束

`agent.invoke(...)` 和 02 / 06 一样。打印「开始 invoke」之后，直到模型跑完，终端不会再出现新行。最后一秒才整段吐出答案。

### updates：每一步推一次

```python
for step in agent.stream(..., stream_mode="updates"):
    # step 长这样：
    # {"model": {"messages": [AIMessage(tool_calls=...)]}}
    # {"tools": {"messages": [ToolMessage(...)]}}
    # {"model": {"messages": [AIMessage("北京今天晴...")]}}
```

字典的 key 就是图上的节点名：`model` 或 `tools`。这就是 01 手写 loop 的每一步，被框架按节点切开发出来。

### tokens：文字边生成边出来

```python
for token, metadata in agent.stream(..., stream_mode="messages"):
    print(token.text, end="", flush=True)
```

`updates` 的粒度是「一步」；`messages` 的粒度是「模型吐出的一个片段」。聊天框里一个字一个字往外蹦，用的是这个。

`stream_mode="messages"` 也会把工具节点的返回值当成 token 推出来。本课只把 `langgraph_node == "model"` 的文字当成答案；遇到工具名就另起一行 `→ get_weather`。

### sse：把 yield 推过 HTTP

SSE 协议就一件事：每条事件是一行 `data: {json}\n\n`。

本课的 `/chat` 把两种 stream 收成给前端的事件：

| type | 何时 |
|---|---|
| `tool_call` | 模型决定调工具（来自 updates） |
| `tool_result` | 工具执行完（来自 updates） |
| `token` | 最终文字片段（来自 messages） |
| `done` | loop 结束 |

`07_streaming.py sse` 会在本机起 FastAPI，再自己当客户端把这些行打出来。等价的手动请求：

```bash
curl -N "http://127.0.0.1:8765/chat" --get --data-urlencode 'q=北京天气怎么样？'
```

浏览器侧之后用 `EventSource` 收同一条流。那是学习目标第 12 条，这一课只把协议跑通。

## 3. 和 01 / 02 的对照

| | 手写 (`01`) | `create_agent` |
|---|---|---|
| 等全部结束 | `create(..., stream=False)` | `agent.invoke(...)` |
| 边跑边看 | `create(..., stream=True)` 自己读 delta | `agent.stream(...)` |
| 一步一步 | 自己在 while 里 print | `stream_mode="updates"` |
| 一个字一个字 | `chunk.choices[0].delta.content` | `stream_mode="messages"` |
| 推给前端 | 自己写 HTTP 响应 | 本课：FastAPI + SSE |

`thread_id` / checkpointer 和 06 一样可以叠在 `stream` 的 config 上。流式不负责记忆，只负责往外递。

## 4. 这一课的核心

```text
invoke  = 等 loop 结束，给你最终 messages
stream  = 同一个 loop，边跑边 yield
SSE     = 每次 yield 包成 data: ...\n\n
```

流式不让模型更聪明。它只让调用方不用干等到最后。
