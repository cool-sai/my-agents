import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const AGENT = "http://127.0.0.1:8765";
const SESSIONS_KEY = "stu-sessions";
const ACTIVE_KEY = "stu-active-thread";

type Row = { kind: "user" | "tool" | "answer"; text: string };
type Session = { id: string; title: string };
type Block =
  | { type: "user" | "answer"; text: string }
  | { type: "tools"; items: Row[] };

type AgentEvent =
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; content: string }
  | { type: "done" }
  | { type: "cancelled" };

function readSessions(): { sessions: Session[]; active: string } {
  const raw = localStorage.getItem(SESSIONS_KEY);
  if (raw) {
    const sessions = JSON.parse(raw) as Session[];
    const active = localStorage.getItem(ACTIVE_KEY) || sessions[0]?.id;
    if (sessions.length > 0 && active) {
      return { sessions, active };
    }
  }
  const id = localStorage.getItem("stu-thread-id") || crypto.randomUUID();
  return { sessions: [{ id, title: "新会话" }], active: id };
}

export function App() {
  const initial = readSessions();
  const [sessions, setSessions] = useState<Session[]>(initial.sessions);
  const [thread, setThread] = useState(initial.active);
  const [question, setQuestion] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const activeRef = useRef(thread);
  const stoppedRef = useRef(false);
  const loadGen = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  activeRef.current = thread;

  useEffect(() => {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
    localStorage.setItem(ACTIVE_KEY, thread);
  }, [sessions, thread]);

  useEffect(() => {
    const gen = ++loadGen.current;
    const id = thread;
    fetch(`${AGENT}/history?thread_id=${encodeURIComponent(id)}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((body: { rows: Row[]; pending?: AgentEvent[]; live?: boolean }) => {
        if (gen !== loadGen.current) {
          return;
        }
        const pending = body.pending ?? [];
        setRows(pending.reduce(applyEvent, body.rows));
        if (!body.live) {
          return;
        }
        stoppedRef.current = false;
        sourceRef.current?.close();
        const source = new EventSource(
          `${AGENT}/listen?thread_id=${encodeURIComponent(id)}&after=${pending.length}`,
        );
        sourceRef.current = source;
        setBusy(true);
        watch(source, id, true);
      })
      .catch(() => {
        if (gen !== loadGen.current) {
          return;
        }
        setRows((prev) =>
          prev.length > 0
            ? prev
            : [
                {
                  kind: "answer",
                  text: "连不上 Agent。先在另一个终端运行 python 14_cancel.py",
                },
              ],
        );
      });
    return () => {
      sourceRef.current?.close();
    };
  }, [thread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [rows]);

  function openSession(id: string) {
    if (id === thread) {
      return;
    }
    activeRef.current = id;
    const source = sourceRef.current;
    sourceRef.current = null;
    source?.close();
    stoppedRef.current = false;
    setBusy(false);
    setThread(id);
  }

  function addSession() {
    const id = crypto.randomUUID();
    setSessions((prev) => [{ id, title: "新会话" }, ...prev]);
    openSession(id);
  }

  function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) {
      return;
    }
    stoppedRef.current = false;
    sourceRef.current?.close();
    loadGen.current += 1;
    const id = thread;
    setQuestion("");
    setSessions((prev) =>
      prev.map((session) =>
        session.id === id && session.title === "新会话"
          ? { ...session, title: text.slice(0, 18) }
          : session,
      ),
    );
    setRows((prev) => [...prev, { kind: "user", text }]);
    setBusy(true);

    const source = new EventSource(
      `${AGENT}/chat?thread_id=${encodeURIComponent(id)}&q=${encodeURIComponent(text)}`,
    );
    sourceRef.current = source;
    watch(source, id, false);
  }

  function watch(source: EventSource, id: string, resume: boolean) {
    let saw = false;
    source.onmessage = (message) => {
      if (activeRef.current !== id) {
        return;
      }
      const agentEvent = JSON.parse(message.data) as AgentEvent;
      if (agentEvent.type === "token") {
        if (stoppedRef.current) {
          return;
        }
        saw = true;
        setRows((prev) => appendToken(prev, agentEvent.text));
      } else if (agentEvent.type === "tool_call") {
        saw = true;
        const args = JSON.stringify(agentEvent.args);
        push({ kind: "tool", text: `→ ${agentEvent.name}(${args})` });
      } else if (agentEvent.type === "tool_result") {
        saw = true;
        push({
          kind: "tool",
          text: `← ${agentEvent.name}: ${agentEvent.content}`,
        });
      } else if (agentEvent.type === "done" || agentEvent.type === "cancelled") {
        source.close();
        setBusy(false);
        if (resume && !saw) {
          fetch(`${AGENT}/history?thread_id=${encodeURIComponent(id)}`)
            .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
            .then((body: { rows: Row[] }) => {
              if (activeRef.current !== id) {
                return;
              }
              setRows(body.rows);
            })
            .catch(() => {});
        }
      }
    };

    source.onerror = () => {
      source.close();
      if (activeRef.current !== id) {
        return;
      }
      if (stoppedRef.current) {
        setBusy(false);
        return;
      }
      setBusy(false);
      setRows((prev) =>
        prev.some((row) => row.kind !== "user")
          ? prev
          : [
              ...prev,
              {
                kind: "answer",
                text: "连不上 Agent。先在另一个终端运行 python 14_cancel.py",
              },
            ],
      );
    };
  }

  function push(row: Row) {
    setRows((prev) => [...prev, row]);
  }

  function stop() {
    if (stoppedRef.current) {
      return;
    }
    stoppedRef.current = true;
    const id = thread;
    const source = sourceRef.current;
    void fetch(`${AGENT}/cancel?thread_id=${encodeURIComponent(id)}`)
      .then(async (response) => {
        const body = response.ok
          ? ((await response.json()) as { stopped?: boolean })
          : null;
        if (!body?.stopped && activeRef.current === id) {
          source?.close();
          setBusy(false);
        }
      })
      .catch(() => {
        if (activeRef.current !== id) {
          return;
        }
        source?.close();
        setBusy(false);
      });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const active = sessions.find((session) => session.id === thread);
  const waiting = busy && rows.at(-1)?.kind !== "answer";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark" />
          星林
        </div>
        <button type="button" className="new-session" onClick={addSession}>
          新会话
        </button>
        <p className="side-label">会话</p>
        <ul className="sessions">
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                className={session.id === thread ? "session active" : "session"}
                onClick={() => openSession(session.id)}
              >
                {session.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="chat">
        <header className="topbar">
          <p>{active?.title ?? "星林"}</p>
        </header>
        <div className="log">
          <div className="column">
            {rows.length === 0 ? (
              <div className="empty">
                <p className="empty-mark">星林</p>
                <p>问天气、算一笔，或者接着上一句。</p>
              </div>
            ) : null}
            {toBlocks(rows).map((block, index) =>
              block.type === "tools" ? (
                <ToolCard key={index} items={block.items} />
              ) : (
                <div key={index} className={`bubble-row ${block.type}`}>
                  <div className="bubble">
                    {block.type === "answer" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
                    ) : (
                      block.text
                    )}
                  </div>
                </div>
              ),
            )}
            {waiting ? (
              <div className="thinking" aria-hidden="true">
                <i />
                <i />
                <i />
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        </div>
        <form className="composer" onSubmit={ask}>
          <div className="composer-shell">
            <textarea
              value={question}
              placeholder="写一条消息"
              rows={1}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
            />
            <button
              type={busy ? "button" : "submit"}
              className={busy ? "stop" : undefined}
              aria-label={busy ? "停止" : "发送"}
              disabled={!busy && question.trim() === ""}
              onClick={busy ? stop : undefined}
            >
              {busy ? <i /> : "发送"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

function toBlocks(rows: Row[]): Block[] {
  const blocks: Block[] = [];
  for (const row of rows) {
    if (row.kind === "tool") {
      const last = blocks[blocks.length - 1];
      if (last?.type === "tools") {
        last.items.push(row);
      } else {
        blocks.push({ type: "tools", items: [row] });
      }
      continue;
    }
    blocks.push({ type: row.kind, text: row.text });
  }
  return blocks;
}

function ToolCard({ items }: { items: Row[] }) {
  return (
    <div className="tool-card">
      {items.map((item, index) => {
        const line = parseTool(item.text);
        return (
          <p key={index} className={line.kind}>
            <span>{line.kind === "call" ? line.name : "结果"}</span>
            {line.detail}
          </p>
        );
      })}
    </div>
  );
}

function parseTool(text: string): { kind: "call" | "result"; name: string; detail: string } {
  const call = text.match(/^→\s+([^(]+)\(([\s\S]*)\)$/);
  if (call) {
    return { kind: "call", name: call[1], detail: prettyArgs(call[2]) };
  }
  const result = text.match(/^←\s+([^:]+):\s*([\s\S]*)$/);
  if (result) {
    return { kind: "result", name: result[1], detail: result[2] };
  }
  return { kind: "result", name: "工具", detail: text };
}

function prettyArgs(raw: string): string {
  try {
    const value = JSON.parse(raw) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.values(value as Record<string, unknown>).map(String).join("，");
    }
  } catch {
    // 参数不是 JSON 时原样显示。
  }
  return raw;
}

function applyEvent(rows: Row[], event: AgentEvent): Row[] {
  if (event.type === "token") {
    return appendToken(rows, event.text);
  }
  if (event.type === "tool_call") {
    return [...rows, { kind: "tool", text: `→ ${event.name}(${JSON.stringify(event.args)})` }];
  }
  if (event.type === "tool_result") {
    return [...rows, { kind: "tool", text: `← ${event.name}: ${event.content}` }];
  }
  return rows;
}

function appendToken(rows: Row[], text: string): Row[] {
  const last = rows[rows.length - 1];
  if (last?.kind === "answer") {
    return [...rows.slice(0, -1), { kind: "answer", text: last.text + text }];
  }
  return [...rows, { kind: "answer", text }];
}
