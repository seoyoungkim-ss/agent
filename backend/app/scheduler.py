"""PRD 9.3: APScheduler 기반 배치 작업 (Celery 없이 앱 프로세스 내 크론으로 처리).

- 매일 새벽: 전날 daily_corner_stats/daily_division_stats 재계산,
  최근 6개월 menu_performance_stats 재계산(PRD 6.3 "6개월 누적 데이터" 기준),
  employee_taste_profile 재계산,
  LLM 분석 캐시 갱신(메뉴 만족도 변화 원인 · 편성 notice · 신규 메뉴 식재료 추출)
- 매월 1일 새벽: 지난달 monthly_voe_cluster 재계산 (사내 LLM 임베딩 필요),
  지난달 VOE 고정 분류(맛/간/위생/서비스) LLM 재계산(meal_log.voe_categories),
  taste_cluster(취향 군집) 재계산 — 표본이 부족하면 조용히 건너뜀(0건 생성)
"""

import asyncio
import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.services.aggregation import aggregate_daily_stats, aggregate_menu_performance
from app.services.food_vector_tagging import run_llm_ingredient_extraction
from app.services.llm_analysis import refresh_llm_analyses
from app.services.llm_client import InternalLLMClient
from app.models.stats import DailyWeather
from app.services.taste_clustering import compute_taste_clusters
from app.services.taste_profile import compute_employee_taste_profiles
from app.services.voe_category_llm import classify_monthly_voe_via_llm
from app.services.voe_clustering import cluster_monthly_voe
from app.services.weather_client import KmaWeatherClient

logger = logging.getLogger(__name__)

MENU_PERFORMANCE_WINDOW_DAYS = 180  # PRD: 취식 데이터는 6개월 누적
DEFAULT_TASTE_CLUSTER_K = 5  # PRD 6.1: 취향 군집 개수 (데이터 보고 튜닝 가능)


async def _run_llm_daily_steps(db, period_start: dt.date, period_end: dt.date) -> None:
    """매일 도는 LLM 단계들. 한 단계가 실패해도 나머지는 돌아야 한다(§44).

    식재료 추출을 여기 둔 이유: 매주 식단표가 올라오며 새 메뉴가 생기는데,
    `ingredients`가 비어 있으면 한 끼 구성 중복 판정이 키워드 사전으로 되돌아간다
    (담당자가 "외국산을 '국'으로 인식한다"고 지적한 그 경로). 대상이
    `ingredients IS NULL`인 행뿐이라 첫 실행 이후엔 하루 몇 건 수준이다.
    """
    client = InternalLLMClient(get_settings())
    try:
        extracted = await run_llm_ingredient_extraction(db, client)
        logger.info("LLM 식재료 추출 %d건", extracted)
    except Exception:
        logger.exception("LLM 식재료 추출 실패 — 나머지 LLM 단계는 계속 진행")

    counts = await refresh_llm_analyses(db, period_start=period_start, period_end=period_end)
    logger.info("LLM 분석 캐시 갱신 %s", counts)


def _fetch_weather_step(db, target_date: dt.date) -> None:
    """PRD 7.1: 전날 강수 실측치를 daily_weather에 채운다(2026-08).

    사내망이 data.go.kr에 못 닿는 배포가 있을 수 있어(is_configured=False),
    그 경우 아무 것도 하지 않고 조용히 넘어간다 — 나머지 배치를 절대 막지 않는다.
    """
    client = KmaWeatherClient(get_settings())
    if not client.is_configured:
        return
    records = asyncio.run(client.fetch_daily_range(target_date, target_date))
    for rec in records:
        existing = db.get(DailyWeather, rec.stat_date)
        if existing:
            existing.precip_mm = rec.precip_mm
            existing.avg_temp_c = rec.avg_temp_c
            existing.had_rain = rec.had_rain
            existing.snow_cm = rec.snow_cm
            existing.max_temp_c = rec.max_temp_c
            existing.min_temp_c = rec.min_temp_c
            existing.source = "kma_api"
        else:
            db.add(
                DailyWeather(
                    stat_date=rec.stat_date,
                    precip_mm=rec.precip_mm,
                    avg_temp_c=rec.avg_temp_c,
                    had_rain=rec.had_rain,
                    snow_cm=rec.snow_cm,
                    max_temp_c=rec.max_temp_c,
                    min_temp_c=rec.min_temp_c,
                    source="kma_api",
                )
            )
    db.commit()


def run_daily_batch() -> None:
    db = SessionLocal()
    try:
        yesterday = dt.date.today() - dt.timedelta(days=1)
        aggregate_daily_stats(db, yesterday)

        try:
            _fetch_weather_step(db, yesterday)
        except Exception:
            logger.exception("날씨 수집 실패 — 나머지 배치는 계속 진행")

        period_end = yesterday
        period_start = period_end - dt.timedelta(days=MENU_PERFORMANCE_WINDOW_DAYS)
        aggregate_menu_performance(db, period_start, period_end)

        compute_employee_taste_profiles(db)

        # LLM 분석은 화면 로드가 아니라 여기서 미리 계산해 캐시에 넣는다(2026-08).
        # 실패해도 위 집계는 이미 끝났으므로 배치 전체를 죽이지 않는다.
        try:
            asyncio.run(_run_llm_daily_steps(db, period_start, period_end))
        except Exception:
            logger.exception("LLM 분석 갱신 실패 — 집계는 정상 완료됨")

        logger.info("daily batch completed for %s", yesterday)
    except Exception:
        logger.exception("daily batch failed")
    finally:
        db.close()


def run_monthly_voe_clustering() -> None:
    db = SessionLocal()
    try:
        settings = get_settings()
        client = InternalLLMClient(settings)
        last_month_end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
        period_month = last_month_end.replace(day=1)
        asyncio.run(cluster_monthly_voe(db, period_month, client))
        logger.info("monthly VOE clustering completed for %s", period_month)
    except Exception:
        logger.exception("monthly VOE clustering failed")
    finally:
        db.close()


def run_monthly_voe_category_classification() -> None:
    db = SessionLocal()
    try:
        settings = get_settings()
        client = InternalLLMClient(settings)
        last_month_end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
        period_month = last_month_end.replace(day=1)
        classified = asyncio.run(classify_monthly_voe_via_llm(db, period_month, client))
        logger.info("monthly VOE category classification completed for %s (%d comments)", period_month, classified)
    except Exception:
        logger.exception("monthly VOE category classification failed")
    finally:
        db.close()


def run_monthly_taste_clustering() -> None:
    db = SessionLocal()
    try:
        created = compute_taste_clusters(db, k=DEFAULT_TASTE_CLUSTER_K)
        logger.info("monthly taste clustering created %d clusters", created)
    except Exception:
        logger.exception("monthly taste clustering failed")
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(run_daily_batch, "cron", hour=2, minute=0, id="daily_batch", replace_existing=True)
    scheduler.add_job(
        run_monthly_voe_clustering, "cron", day=1, hour=3, minute=0, id="monthly_voe", replace_existing=True
    )
    scheduler.add_job(
        run_monthly_voe_category_classification,
        "cron",
        day=1,
        hour=3,
        minute=15,
        id="monthly_voe_category",
        replace_existing=True,
    )
    scheduler.add_job(
        run_monthly_taste_clustering,
        "cron",
        day=1,
        hour=3,
        minute=30,
        id="monthly_taste_clustering",
        replace_existing=True,
    )
    return scheduler
