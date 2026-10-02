import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    original = {name: getattr(settings, name) for name in ("database_path", "ai_provider", "ai_base_url", "ai_api_key", "ai_model", "google_cse_api_key", "google_cse_id", "enable_rdap", "allow_private_lab")}
    object.__setattr__(settings, "database_path", str(tmp_path / "isolated.db"))
    object.__setattr__(settings, "ai_provider", "rules-demo")
    object.__setattr__(settings, "enable_rdap", False)
    object.__setattr__(settings, "allow_private_lab", False)
    for name in ("ai_base_url", "ai_api_key", "ai_model"):
        object.__setattr__(settings, name, "")
    for name in ("google_cse_api_key", "google_cse_id"):
        object.__setattr__(settings, name, "")
    yield
    for name, value in original.items():
        object.__setattr__(settings, name, value)
