import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import analysis, chat, dashboard, ingest, simulation
from app.config import get_settings
from app.scheduler import create_scheduler

scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="사내 카페테리아 운영 관리 홈페이지 API", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# 프론트엔드(src/api/client.ts)는 모든 API 호출을 "/api" 아래로 보낸다 — 개발 중에는
# vite proxy가, 배포 시에는 이 prefix가 그 경로와 그대로 맞아떨어지게 한다(PRD 9.4).
api_router = APIRouter(prefix="/api")
api_router.include_router(ingest.router)
api_router.include_router(dashboard.router)
api_router.include_router(analysis.router)
api_router.include_router(simulation.router)
api_router.include_router(chat.router)
app.include_router(api_router)

# PRD 9.4: Docker 이미지 안에서 프론트엔드 빌드 결과(dist/)를 같은 컨테이너가 정적
# 파일로 서빙한다. /api/*가 먼저 매칭되므로 그 외 경로만 SPA로 넘어간다.
_FRONTEND_DIST_DIR = os.environ.get("FRONTEND_DIST_DIR", "/app/frontend_dist")
if os.path.isdir(_FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST_DIR, html=True), name="frontend")
