"""PRD 9.3: APScheduler 기반 배치 작업 (Celery 없이 앱 프로세스 내 크론으로 처리).

- 매일 새벽: 전날 daily_corner_stats/daily_division_stats 재계산,
  최근 6개월 menu_performance_stats 재계산(PRD 6.3 "6개월 누적 데이터" 기준),
  employee_taste_profile 재계산
- 매월 1일 새벽: 지난달 monthly_voe_cluster 재계산 (사내 LLM 임베딩 필요),
  taste_cluster(취향 군집) 재계산 — 표본이 부족하면 조용히 건너뜀(0건 생성)
"""

import asyncio
import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.services.aggregation import aggregate_daily_stats, aggregate_menu_performance
from app.services.llm_client import InternalLLMClient
from app.services.taste_clustering import compute_taste_clusters
from app.services.taste_profile import compute_employee_taste_profiles
from app.services.voe_clustering import cluster_monthly_voe

logger = logging.getLogger(__name__)

MENU_PERFORMANCE_WINDOW_DAYS = 180  # PRD: 취식 데이터는 6개월 누적
DEFAULT_TASTE_CLUSTER_K = 5  # PRD 6.1: 취향 군집 개수 (데이터 보고 튜닝 가능)


def run_daily_batch() -> None:
    db = SessionLocal()
    try:
        yesterday = dt.date.today() - dt.timedelta(days=1)
        aggregate_daily_stats(db, yesterday)

        period_end = yesterday
        period_start = period_end - dt.timedelta(days=MENU_PERFORMANCE_WINDOW_DAYS)
        aggregate_menu_performance(db, period_start, period_end)

        compute_employee_taste_profiles(db)
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
        run_monthly_taste_clustering,
        "cron",
        day=1,
        hour=3,
        minute=30,
        id="monthly_taste_clustering",
        replace_existing=True,
    )
    return scheduler
