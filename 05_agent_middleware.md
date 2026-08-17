# 第 05 课：Agent Middleware

## 1. 为什么需要中间件

前三课让 Agent 能调用工具，第 04 课让它能返回结构化结果。但一个可用的
Agent 还需要回答这些问题：

- 不同身份的用户是否应该得到不同提示？
- 敏感工具执行前由谁检查权限？
- 工具抛出异常时，是让程序崩溃，还是把可理解的错误交给模型？
- 模型不断重复调用失败工具时，如何停止？

Middleware 是包在模型调用或工具调用外面的应用逻辑：

```text
用户消息
   ↓
dynamic_prompt（生成本轮系统提示词）
   ↓
模型产生 tool_call
   ↓
guard_and_handle_tool（鉴权、执行、处理错误）
   ↓
ToolMessage
   ↓
模型继续生成最终答案
```

## 2. 三个实验

```bash
python 05_agent_middleware.py guest
python 05_agent_middleware.py admin
python 05_agent_middleware.py error
```

### guest：权限拒绝

访客要求调用 `delete_note`。权限中间件发现角色不是 `admin`，直接返回错误
`ToolMessage`，不会调用真实工具函数。模型读取错误后向用户解释。

### admin：权限通过

管理员发出相同请求。中间件调用 `handler(request)`，真实工具得到执行，结果
作为成功的 `ToolMessage` 返回模型。

### error：异常转成消息

`lookup_order("order-9999")` 会抛出 `ValueError`。中间件捕获这个预期业务
异常，并转换成安全的错误 `ToolMessage`。Agent Loop 因此不会崩溃，模型可以
根据错误生成面向用户的回答。

## 3. 动态提示词

```python
@dynamic_prompt
def role_aware_prompt(request: ModelRequest[AgentContext]) -> str:
    context = request.runtime.context
    return f"当前用户角色是 {context['user_role']}。"
```

静态 `system_prompt=` 在整个 Agent 生命周期中不变；`dynamic_prompt` 在每次
模型调用前运行，可以读取当前身份、会话状态或业务配置。

身份放在 `context` 而不是用户消息中非常重要。用户可以在消息里声称“我是
管理员”，但只有应用后端提供的可信上下文才应该参与鉴权。

## 4. 包装工具调用

```python
@wrap_tool_call
def guard_and_handle_tool(request, handler):
    if 没有权限:
        return ToolMessage(status="error", ...)

    try:
        return handler(request)
    except ValueError:
        return ToolMessage(status="error", ...)
```

这里的 `handler(request)` 才代表“继续执行真实工具”：

- 不调用 `handler`：短路，工具没有执行；
- 调用 `handler`：放行；
- 在调用前后加代码：可以鉴权、计时、记录日志；
- 捕获异常：可以控制哪些错误允许暴露给模型。

不要把数据库错误、密钥或内部堆栈直接放进 `ToolMessage`。应该转换成模型和
用户都能理解的安全业务信息。

## 5. 限制模型调用次数

```python
ModelCallLimitMiddleware(
    run_limit=4,
    exit_behavior="end",
)
```

一次 Agent 运行最多调用模型四次。这样即使模型不断重试失败工具，也不会
无限循环或持续产生费用。

这和手写 Loop 中的 `MAX_STEPS` 是同一个保护思想，只是由框架中间件实现。

## 6. 这一课的核心

```text
模型负责决定想做什么
工具负责执行一个动作
Agent Loop 负责反复编排
Middleware 负责在关键边界实施应用规则
```

权限不能只写在提示词里。提示词可以改善模型行为，但真正的安全边界必须是
模型无法绕过的应用代码。
