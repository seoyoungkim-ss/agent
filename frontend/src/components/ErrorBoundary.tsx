import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * §79: 렌더 중 예외가 나면 React가 트리 전체를 언마운트해 화면이 통째로
 * 하얗게 빈다(콘솔에만 스택이 찍힘) — 담당자가 신고한 "메뉴편성 탭
 * 누르면 흰화면" 자체는 코드 결함으로 재현되지 않았지만, 이 앱엔
 * 에러 바운더리가 하나도 없어 앞으로 비슷한 일이 생기면 똑같이 아무
 * 안내 없이 하얗게 빈다. 최소한 무슨 일이 있었는지는 보이게 하는 안전망.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="m-6 rounded-xl border px-4 py-3 text-[13px]"
          style={{ borderColor: "var(--critical)", color: "var(--critical)", background: "var(--surface-2)" }}
        >
          <p className="font-medium">문제가 발생했습니다. 새로고침해 주세요.</p>
          <p className="mt-1" style={{ color: "var(--ink-muted)" }}>
            {this.state.error.message}
          </p>
          <button
            className="mt-3 rounded-md border px-3 py-1.5 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            onClick={() => window.location.reload()}
          >
            새로고침
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
