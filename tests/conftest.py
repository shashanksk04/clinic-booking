import os

# IMPORTANT: tests use their OWN database, because every test wipes its tables.
# This must be set before the app is imported.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://clinic:clinic@localhost:5432/clinic_test",
)
assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1], (
    "Refusing to run: the test database name must contain 'test' "
    "(tests delete all data!)"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["BCRYPT_ROUNDS"] = "4"  # cheap hashing so tests run fast

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import models  # noqa: E402,F401
from database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    """Every test starts with empty tables."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)
