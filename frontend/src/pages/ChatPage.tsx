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
    <Card title="Agent 채팅 (사내 LLM 연동, PRD 8)" className="flex h-[70vh] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            예: "이번 달 그린미트 코너 만족도 어때?", "지난주 대체공휴일 식수는 평소 대비 몇 %였어?"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <span
              className={
                "inline-block max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm " +
                (m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100")
              }
            >
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="mt-3 flex gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <input
          className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
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
