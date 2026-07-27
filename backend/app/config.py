from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://cafeteria:cafeteria@localhost:5432/cafeteria"

    # PRD 9.2: 운영자 PC의 ingestion-tool이 이 토큰으로 /ingest/* API를 호출한다.
    ingest_api_token: str = "change-me-in-env"

    # PRD 8: 사내 LLM API 연동 정보. 실제 값은 사내 배포 시 .env로만 주입한다.
    internal_llm_base_url: str = ""
    internal_llm_api_key: str = ""
    internal_llm_chat_model: str = "internal-chat"
    internal_llm_embedding_model: str = "internal-embedding"

    # PRD 6.3.1: 표본 수 보정(베이지안 축소)에 쓰는 신뢰 기준 평가건수 m
    menu_score_shrinkage_m: int = 20
    # PRD 6.3.1: 평가건수가 이 값 미만이면 "표본 부족" 배지를 붙인다
    menu_score_low_sample_threshold: int = 10

    # PRD 6.2: 피크타임 구간 (분석/집계 배치에서 사용)
    peak_time_start: str = "11:40:00"
    peak_time_end: str = "12:00:00"

    cors_allow_origins: list[str] = ["http://localhost:5173"]

    # PRD 9.4: 프론트엔드 빌드 결과(dist/)를 이 백엔드가 정적 파일로 함께 서빙할 때
    # 사용하는 경로. 디렉터리가 없으면 정적 서빙 자체를 건너뛴다(app/main.py).
    frontend_dist_dir: str = "/app/frontend_dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
