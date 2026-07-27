import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import app

# 개발용 DB(cafeteria)를 건드리지 않도록 테스트 전용 DB를 별도로 사용한다.
TEST_DATABASE_URL = "postgresql+psycopg://cafeteria:cafeteria@localhost:5432/cafeteria_test"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        # 각 테스트마다 데이터 초기화 (스키마는 세션 스코프로 유지)
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture()
def client(engine, db_session):
    Session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

