import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest

from app.core.db import pool


@pytest.fixture(scope="session")
def db_pool():
    p = pool()
    p.open()
    p.wait()
    yield p
    p.close()
