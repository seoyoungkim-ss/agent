// 클립보드 복사 (2026-09).
//
// navigator.clipboard(Async Clipboard API)는 **보안 컨텍스트**(HTTPS 또는
// localhost)에서만 존재한다. 이 서비스는 사내망에 평문 HTTP로 배포되므로
// (`docs/DEPLOYMENT.md` — `http://<서버 IP>:8000`), 실제 배포 환경에서는
// `navigator.clipboard` 자체가 `undefined`라 `.writeText()` 호출이 조용히
// 실패한다("표 복사 버튼이 안 눌린다" 신고, 2026-09) — 개발 컨테이너에서는
// localhost라 보안 컨텍스트로 처리돼 문제가 드러나지 않았다.
//
// 레거시 document.execCommand("copy")는 보안 컨텍스트 여부와 무관하게
// 동작하므로 폴백으로 쓴다.

/** 텍스트를 클립보드에 복사한다. 보안 컨텍스트면 navigator.clipboard를
 * 먼저 시도하고, 없거나 실패하면 document.execCommand("copy")로 폴백한다.
 * 반환값은 실제 성공 여부(호출부가 성공/실패를 다르게 보여줄 수 있게). */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 폴백으로 이어간다.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  // 화면에 보이거나 스크롤을 유발하지 않게 뷰포트 밖으로 고정.
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
}
