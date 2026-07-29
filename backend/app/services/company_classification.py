"""식당취식정보의 "회사" 원문 → 본사/계열사/기타 분류 (PRD 6.1).

사용자 확정 규칙(2026-07-28):
  삼성전자 = 본사, 삼성SDI/삼성에스원/삼성SDS = 계열사, 나머지 = 기타.

이 매핑을 백엔드에만 두는 이유: ingestion-tool(운영자 Windows PC)은 원문 회사명
그대로("회사" 컬럼 원문)만 실어 보내고, 분류 규칙이 바뀌어도 그 실행 파일을
재배포할 필요 없이 이 딕셔너리만 고치면 되게 하기 위함. 회사명 자체는 항상
`employee_master.company_name`에 원문 그대로 남기므로(계열사는 "계열사"라는
라벨이 아니라 실제 회사명으로 화면에 표시된다), 분류가 바뀌어도 원본 데이터는
안 잃는다.
"""

from app.models.enums import Division

COMPANY_DIVISION_MAP: dict[str, Division] = {
    "삼성전자": Division.HEADQUARTERS,
    "삼성SDI": Division.AFFILIATE,
    "삼성에스원": Division.AFFILIATE,
    "삼성SDS": Division.AFFILIATE,
}


def classify_division(company_name: str | None) -> Division:
    if not company_name:
        return Division.OTHER
    return COMPANY_DIVISION_MAP.get(company_name.strip(), Division.OTHER)
