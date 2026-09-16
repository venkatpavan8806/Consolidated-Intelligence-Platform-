import pytest

from app.pipeline import run_full_pipeline
from app.db.schema import get_connection


@pytest.fixture(scope="session", autouse=True)
def pipeline():
    run_full_pipeline(reset_data=True)


@pytest.fixture()
def conn():
    c = get_connection()
    yield c
    c.close()
