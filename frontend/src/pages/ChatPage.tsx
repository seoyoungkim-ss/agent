import { useRef, useState } from "react";
import { api, type ChatMessage } from "../api/client";
import { Button, Card } from "../components/ui";

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);
    try {
      let assistantText = "";
      for await (const chunk of api.chatStream(nextMessages)) {
        assistantText += chunk;
        setMessages([...nextMessages, { role: "assistant", content: assistantText }]);
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (err) {
      setMessages([
        ...nextMessages,
        { role: "assistant", content: `오류: ${err instanceof Error ? err.message : String(err)}` },
      ]);
    } finally {
      setStreaming(false);
    }
  }

  return (
    <Card title="Agent 채팅 (사내 LLM 연동)" className="flex h-[70vh] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            예: "이번 달 그린미트 코너 만족도 어때?", "지난주 대체공휴일 식수는 평소 대비 몇 %였어?"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <span
              className="inline-block max-w-[80%] whitespace-pre-wrap rounded-md px-3.5 py-2 text-[13px]"
              style={
                m.role === "user"
                  ? { background: "var(--accent)", color: "var(--accent-ink)" }
                  : { background: "var(--surface-2)", color: "var(--ink)" }
              }
            >
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="mt-3 flex gap-2 border-t pt-3" style={{ borderColor: "var(--border)" }}>
        <input
          className="flex-1 rounded-md border px-3 py-2 text-[13px]"
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          placeholder="메시지를 입력하세요"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={streaming}
        />
        <Button onClick={send} disabled={streaming}>
          전송
        </Button>
      </div>
    </Card>
  );
}
