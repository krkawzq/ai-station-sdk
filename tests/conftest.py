from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def fixture_dir() -> Path:
    return ROOT / "tests" / "fixtures"


@pytest.fixture
def load_json_fixture(fixture_dir: Path):
    def _load(name: str):
        with (fixture_dir / name).open("r", encoding="utf-8") as fh:
            return json.load(fh)

    return _load


@pytest.fixture
def sample_user():
    from .helpers import make_user

    return make_user()
