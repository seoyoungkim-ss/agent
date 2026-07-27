# PRD 9.4/9.5: 사내망에서 `docker compose up` 한 번으로 웹 대시보드를 구동하는 것이
# 목표다. 이 이미지가 FastAPI + 빌드된 React 정적 파일을 함께 서빙한다
# (ingestion-tool은 이 이미지에 포함하지 않는다 — 별도로 운영자 PC에 배포됨, PRD 9.2).

# ---- 1단계: 프론트엔드 빌드 ----
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- 2단계: 백엔드 런타임 ----
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /frontend/dist /app/frontend_dist
ENV FRONTEND_DIST_DIR=/app/frontend_dist

COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
