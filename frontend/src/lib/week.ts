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

/** 오늘 이전(오늘 제외)의 가장 최근 "완결된" 평일 5일(월~금) 구간의 월요일.
 * 오늘이 금요일이어도 그날 데이터가 아직 안 끝났을 수 있어 지난 금요일부터
 * 거슬러 올라간다 — 예: 오늘이 화요일(9/1)이면 지난 금요일(8/28)이 속한 주의
 * 월요일(8/24)을 반환한다. 식수추이 기본 기간(2026-09, 담당자 요청)처럼
 * "항상 데이터가 꽉 찬 최근 평일 구간"이 필요한 화면 진입 기본값으로 쓴다. */
export function lastCompleteWeekdayMonday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1); // 오늘 제외, 어제부터 거슬러 올라간다
  while (d.getDay() !== 5) d.setDate(d.getDate() - 1); // 5 = 금요일
  return mondayOf(d);
}

/** 두 "YYYY-MM-DD" 사이의 일수(양끝 포함). */
export function daysBetweenInclusive(startIso: string, endIso: string): number {
  const start = new Date(`${startIso}T00:00:00`).getTime();
  const end = new Date(`${endIso}T00:00:00`).getTime();
  return Math.round((end - start) / 86_400_000) + 1;
}
