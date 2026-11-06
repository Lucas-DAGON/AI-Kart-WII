import pytest

from ai_kart_wii.testing.fake_backend import FakeBackend
from ai_kart_wii.testing.fake_race import FakeRace


@pytest.fixture
def race():
    return FakeRace()


@pytest.fixture
def backend(race):
    b = FakeBackend(race)
    b.connect()
    return b
