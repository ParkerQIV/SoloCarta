import pytest
from app.database import init_db


@pytest.fixture(autouse=True, scope="session")
async def setup_db():
    """Ensure database tables are created before tests run."""
    await init_db()
