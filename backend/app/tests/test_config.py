import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="change-this-secret",
        )


def test_dev_keeps_the_local_default_secret() -> None:
    settings = Settings(_env_file=None, app_env="dev", jwt_secret="change-this-secret")

    assert settings.jwt_secret == "change-this-secret"
