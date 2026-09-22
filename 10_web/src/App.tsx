import { FormEvent, useRef, useState } from "react";

const AGENT = "http://127.0.0.1:8765";

type Row = { kind: "tool" | "answer"; text: string };

type AgentEvent =
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; content: string }
  | { type: "done" };

export function App() {
  const [question, setQuestion] = useState("北京天气怎么样？再算一下 12*8");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function ask(event: FormEvent) {
    event.preventDefault();
    sourceRef.current?.close();
    setRows([]);
    setBusy(true);

    const source = new EventSource(
      `${AGENT}/chat?q=${encodeURIComponent(question)}`,
    );
    sourceRef.current = source;

    source.onmessage = (message) => {
      const agentEvent = JSON.parse(message.data) as AgentEvent;
      if (agentEvent.type === "tool_call") {
        const args = JSON.stringify(agentEvent.args);
        push({ kind: "tool", text: `→ ${agentEvent.name}(${args})` });
      } else if (agentEvent.type === "tool_result") {
        push({
          kind: "tool",
          text: `← ${agentEvent.name}: ${agentEvent.content}`,
        });
      } else if (agentEvent.type === "token") {
        setRows((prev) => appendToken(prev, agentEvent.text));
      } else if (agentEvent.type === "done") {
        source.close();
        setBusy(false);
      }
    };

    source.onerror = () => {
      // 流结束时浏览器会自动重连，再把同一个问题打给 Agent。这里直接关掉。
      source.close();
      setBusy(false);
      setRows((prev) =>
        prev.length > 0
          ? prev
          : [
              {
                kind: "tool",
                text: "连不上 Agent。先在另一个终端运行 python 10_web.py",
              },
            ],
      );
    };
  }

  function push(row: Row) {
    setRows((prev) => [...prev, row]);
  }

  return (
    <main>
      <h1>星林 Agent</h1>
      <p>页面不跑循环。它只收 07 那条 SSE：工具调用、工具结果、文字片段。</p>
      <form onSubmit={ask}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || question.trim() === ""}>
          {busy ? "回答中" : "发送"}
        </button>
      </form>
      <ul>
        {rows.map((row, index) => (
          <li key={index} className={row.kind}>
            {row.text}
          </li>
        ))}
      </ul>
    </main>
  );
}

function appendToken(rows: Row[], text: string): Row[] {
  const last = rows[rows.length - 1];
  if (last?.kind === "answer") {
    return [...rows.slice(0, -1), { kind: "answer", text: last.text + text }];
  }
  return [...rows, { kind: "answer", text }];
}
