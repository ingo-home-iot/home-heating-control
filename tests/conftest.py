"""Gemeinsame Testhilfen."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def custom_integrations(enable_custom_integrations):
    """Eigene Integration in den HA-Tests erlauben (nicht für die reinen Engine-Tests)."""
    return


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """Wartezeit zwischen Modus- und Temperaturbefehl in den Tests abschalten."""
    from custom_components.home_heating_control import const

    monkeypatch.setattr(const, "SETTLE_DELAY", 0)
