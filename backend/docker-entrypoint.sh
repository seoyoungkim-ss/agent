#!/bin/sh
# 컨테이너 기동 시 마이그레이션을 먼저 적용한 뒤 서버를 띄운다 (PRD 9.5 DB 마이그레이션 배포).
set -e

echo "Alembic 마이그레이션 적용 중..."
alembic upgrade head

echo "휴일 마스터 데이터 시딩 (이미 있는 날짜는 건너뜀)..."
python -m app.seed.run_seed_holidays || true

echo "서버 시작..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
