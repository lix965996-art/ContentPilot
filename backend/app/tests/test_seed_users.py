"""Seed account policy: production only gets an admin with configurable password."""

from app.core.config import settings
from app.db.seed import user_definitions


def test_production_seed_creates_only_admin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_demo_mode", False)
    monkeypatch.setattr(settings, "admin_initial_password", "Customer@Secret99")

    users = user_definitions()

    assert [u[0] for u in users] == ["admin"]
    assert users[0][1] == "Customer@Secret99"


def test_demo_seed_creates_three_demo_accounts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_demo_mode", True)
    monkeypatch.setattr(settings, "admin_initial_password", "")

    users = user_definitions()

    assert [u[0] for u in users] == ["admin", "operator", "viewer"]
    assert users[0][1] == "Admin@123456"
