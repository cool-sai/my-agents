# 第 13 课：会话写进 MySQL

## 1. 第 10 课缺了什么

页面每次都是一次新的 `invoke`。刷新之后，上一句不在了。第二轮问「刚才那个城市」，模型看不见上一轮。

第 06 课已经用 `thread_id` 把多轮接上，但存在进程内存里，而且没有接到页面。这一课只换存放的地方：本机 Docker 里的 MySQL，库 `stu_agent`。

```text
页面 localStorage 里的 thread_id
  ↓
GET /chat?thread_id=...&q=这一句
  ↓
PyMySQLSaver 按这个 id 读出旧 messages，接上这一句，跑完再写回
  ↓
刷新后 GET /history?thread_id=... 把 messages 画出来
```

## 2. 跑起来

`.env` 里要有 `MYSQL_URI`，指向 `127.0.0.1:3306/stu_agent`。

```bash
python 13_session.py
cd 10_web && npm run dev
```

浏览器打开 http://127.0.0.1:5173 。

1. 问「北京天气怎么样？」
2. 再问「刚才那个城市，温度是多少？」不要把「北京」再打一遍。
3. 关掉标签再打开。上一句还在，会话号不变。

这一课不要再跑 `10_web.py`。那个服务没有 checkpointer，同一个端口会被占住。

## 3. 库里有什么

`checkpointer.setup()` 会建 `checkpoints` 这几张表。一行不是一条聊天气泡，是某一步的整份快照。`thread_id` 是钥匙。读出来给页面用的，是快照里的 `messages`。

进程停了再开，只要 MySQL 还在、`thread_id` 还在浏览器里，历史就还在。

## 4. 这一课的核心

```text
thread_id = 哪一段对话
checkpointer = 按这个 id 把快照写进 MySQL
每一轮只提交新的那一句，旧的由库里的快照接上
```
