// 주 단위 날짜 헬퍼 (2026-08).
//
// 예전엔 HomePage와 WeeklyMenuVoeDetailPage에 **같은 함수가 복제**돼 있었고, 둘 다
// 아래 버그를 갖고 있었다:
//
//   const d = new Date(date);
//   d.setDate(d.getDate() - day);      // ← 로컬 시간 기준
//   return d.toISOString().slice(0,10) // ← UTC 기준
//
// `getDay()`/`setDate()`는 로컬인데 `toISOString()`은 UTC라, KST(UTC+9)에서 오전
// 9시 이전에 부르면 **전날(=일요일)**이 나온다. 그러면 "월요일"이 아닌 날짜가
// 주 시작으로 잡혀 월~토 6일 창이 통째로 하루 밀린다.
//
// 아래는 전부 **로컬 기준**으로 포맷해 그 어긋남을 없앤다.

/** Date → "YYYY-MM-DD" (로컬 기준). toISOString은 UTC라 쓰지 않는다. */
export function toIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** 그 날짜가 속한 주의 월요일 "YYYY-MM-DD". */
export function mondayOf(date: Date): string {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // 월=0 ... 일=6
  d.setDate(d.getDate() - day);
  return toIsoDate(d);
}

/** "YYYY-MM-DD"에서 days만큼 이동한 "YYYY-MM-DD". */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`); // 시간대 해석 흔들림을 막는다
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}

/** 오늘로부터 days일 전 "YYYY-MM-DD". */
export function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return toIsoDate(d);
}

/** 이번 주 월요일 — 화면 진입 기본값으로 쓴다. */
export function currentMonday(): string {
  return mondayOf(new Date());
}
