"""The checked-in OpenAPI document is the search and read API contract."""

import json
from pathlib import Path

from soc_platform.config import Settings
from soc_platform.main import create_app

CONTRACT = Path("contracts/openapi.json")


def test_openapi_contract_matches_the_application() -> None:
    app = create_app(
        Settings(
            database_url="postgresql+psycopg://soc:soc@localhost:5434/soc",
            redis_url="redis://localhost:6379/0",
        )
    )
    generated = json.loads(json.dumps(app.openapi(), sort_keys=True))
    checked_in = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert generated == checked_in
