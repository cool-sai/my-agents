# 第 06 课：短期会话记忆

## 1. 前五课缺了什么

到目前为止，每次运行脚本都是**一轮对话**：传入一句用户消息，拿到一句回答，进程结束。

真实聊天不是这样。用户会说「北京天气怎么样？」，下一句变成「那适合穿什么？」。第二句本身没有城市名，Agent 必须还记得上一轮。

短期记忆不是新能力，它就是你一直在维护的 `messages`：

```text
第 1 轮: [system, user1, ai, tool, ai]
第 2 轮: [system, user1, ai, tool, ai, user2, ...]
                              ↑
                     没扔掉，所以还记得
```

丢掉这个列表，Agent 就失忆。`checkpointer` 只是帮你保管这份列表。

## 2. 四个实验

```bash
python 06_session_memory.py forget
python 06_session_memory.py manual
python 06_session_memory.py remember
python 06_session_memory.py threads
```

建议先跑 `forget`，再跑 `remember`，对比第二轮回答。

### forget：每轮只传新消息

`create_agent` 不带 `checkpointer`。两次 `invoke` 各自只传入当前这句用户话。

第二轮问「我刚才问的是哪个城市？」时，模型看不到第一轮，通常会说不知道，或要求你再提供城市。

### manual：自己保存 messages

和 01 / 03 一样，把 `messages` 放在函数外的列表里。每轮只 `append` 新的 `HumanMessage`，旧消息还在。

第二轮能答出「北京」。这就是记忆的本质，没有框架魔法。

### remember：checkpointer + thread_id

```python
agent = create_agent(..., checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "user-xiaolin"}}

agent.invoke({"messages": [本轮用户消息]}, config)
agent.invoke({"messages": [下一轮用户消息]}, config)
```

你仍然只传**本轮新消息**。框架用 `thread_id` 把 checkpoint 里的旧 `messages` 取出来，接在后面再跑 loop。

`get_state(config)` 可以看到这份已保存的列表在变长。

### threads：thread_id 就是会话主键

同一个 Agent、同一份 `InMemorySaver`，`thread-a` 问北京，`thread-b` 问上海。

各自再问「我刚才问的是哪个城市？」时，A 答北京，B 答上海。记忆按线程隔离，不会串话。

## 3. 和 01 手写 loop 的对照

| | 手写 | `create_agent` |
|---|---|---|
| 一轮之内的 tool loop | 自己 `while` | 框架内部 |
| 多轮之间的历史 | 自己拿着 `messages` 列表 | `checkpointer` 按 `thread_id` 存取 |
| 你每轮传给模型的内容 | 完整历史 | 只传新消息，旧的由 checkpoint 拼回去 |

`InMemorySaver` 存在当前进程的内存里。脚本结束，记忆消失。所以它叫**短期**会话记忆：跨请求记得，跨进程不记得。

生产里会换成 SQLite / Postgres 等持久化 checkpointer；接口不变，仍是 `thread_id`。那是换存储器，不是换记忆模型。

跨用户、跨会话要长期记住的事实（「用户叫小林」「过敏原」）走 `store`，不是这一课的 checkpointer。

## 4. 这一课的核心

```text
短期记忆 = 没被扔掉的 messages
thread_id = 这份 messages 的钥匙
checkpointer = 替你保管 messages 的抽屉
```

不要在提示词里写「请记住上一轮」。上一轮必须作为消息真的出现在上下文里。
