"""meal_log에 완전히 같은 취식 기록이 여러 번 쌓인 경우를 하나로 합친다.

append-only 로그라 원래 자연 중복 방지가 없다. 같은 사번이 "12345678"과
"12345678.0"으로 갈라져 있다가 `normalize_employee_ids.py`로 나중에 합쳐지면,
그 전엔 서로 다른 사번처럼 보였던 완전히 같은 취식 기록(같은 사번·일시·
식사구분·코너·메뉴)이 진짜 중복으로 드러난다(2026-07 실사용 확인 — 맛평가가
매칭된 적재와 안 된 적재가 서로 다른 시점에 따로 들어가 있었던 경우, 다운로드한
데이터가 매칭 안 된 쪽만 걸려 "맛평가가 전부 비어있다"처럼 보일 수 있었다).

**`normalize_employee_ids.py`를 먼저 실행한 뒤** 이 스크립트를 돌려야 한다 —
사번이 아직 안 합쳐진 상태에서는 중복이 같은 사번으로 안 보여서 못 잡는다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.dedupe_meal_log

여러 번 실행해도 안전하다(idempotent) — 중복이 없으면 조용히 종료한다.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog


def dedupe_meal_log(db: Session) -> int:
    """같은 (사번, 취식일시, 식사구분, 코너, 메뉴) 조합이 여러 행이면 하나만 남긴다.

    맛평가(taste_score)가 있는 행을 우선 남기고(중복 제거 과정에서 실제 평가
    데이터를 잃지 않도록), 그다음 먼저 적재된 행을 남긴다.

    returns: 삭제된 중복 행 수.
    """
    logs = db.query(MealLog).all()
    groups: dict[tuple, list[MealLog]] = defaultdict(list)
    for log in logs:
        key = (log.employee_id, log.eaten_at, log.meal_type, log.corner_id, log.menu_id)
        groups[key].append(log)

    removed = 0
    for group in groups.values():
        if len(group) <= 1:
            continue
        group.sort(key=lambda log: (log.taste_score is None, log.loaded_at))
        _keeper, *duplicates = group
        for dup in duplicates:
            db.delete(dup)
            removed += 1
    db.commit()
    return removed


def run() -> None:
    db = SessionLocal()
    try:
        removed = dedupe_meal_log(db)
        if removed == 0:
            print("중복된 취식 기록이 없습니다.")
            return
        print(f"✅ 중복된 취식 기록 {removed}행을 정리했습니다.")
        print("⚠️ daily_corner_stats/daily_division_stats, menu_performance_stats를 다시 계산해야 합니다 —")
        print("   '최근 180일 배치 집계 재계산' 버튼과 menu-performance/recompute를 호출하세요.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
