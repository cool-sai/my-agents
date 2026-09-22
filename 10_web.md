# 第 10 课：浏览器收同一条流

## 1. 前九课缺了什么

Agent 已经能调工具、流式输出、检索、被评估。调用方一直是终端。

页面不能 `import create_agent`。它和模型之间只剩 HTTP。07 已经把 loop 收成四种事件，这一课只换收件人：浏览器。

```text
输入框
  ↓
EventSource  GET /chat?q=...
  ↓
07 的 SSE：tool_call / tool_result / token / done
  ↓
页面把 token 拼成一段话，把工具调用另起一行
```

没有新的循环，也没有第二个 Agent。

## 2. 跑起来

两个终端：

```bash
python 10_web.py
cd 10_web && npm install && npm run dev
```

浏览器打开 http://127.0.0.1:5173 ，默认问题会走到天气和计算器。

`10_web.py` 加载的就是 `07_streaming.py` 里的 FastAPI。07 的 `sse` 场景收完一次就退出；这里服务一直开着，因为页面会连多次。

页面在 `:5173`，Agent 在 `:8765`。浏览器默认不把另一个端口的响应交给页面脚本，所以服务加了 CORS，允许这个页面来源。Vite 只负责把这个 React 页面送进浏览器，Agent 仍在 Python 里。

## 3. 页面在做什么

`EventSource` 只能发 GET，这和 07 的 `/chat?q=` 一致。每来一行 `data:`，解析 JSON：

| type | 页面 |
|---|---|
| `tool_call` | 一行 `→ 工具名(参数)` |
| `tool_result` | 一行 `← 工具名: 结果` |
| `token` | 接到上一段回答后面 |
| `done` | 关掉连接，按钮恢复 |

流正常结束时，浏览器会自动再连一次，同一个问题会再跑一遍 Agent。收到 `done` 或出错都要 `source.close()`。

## 4. 这一课的核心

```text
页面 = EventSource + 把事件画出来
Agent = 还是 07 那个 FastAPI
```

全栈这一刀切在 HTTP 上，不切在「再写一个会调工具的前端」。
