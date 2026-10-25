import pytest
from fastapi.testclient import TestClient

from agora_api.config import CATALOG_DB
from agora_api.main import app

# The tests run against the real catalogue and data: build them first.
if not CATALOG_DB.exists():
    pytest.exit(f"Missing {CATALOG_DB}: run `python -m agora_api.catalog.build` (after the pipelines)", returncode=1)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        yield client
