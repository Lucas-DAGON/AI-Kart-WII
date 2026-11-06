import json

import pytest

from ai_kart_wii.testing.fake_backend import FakeBackend
from ai_kart_wii.testing.fake_protocol import FakeProtocolHandler


def send(handler, **message):
    message.setdefault("MessageType", "Request")
    return json.loads(handler.handle_line(json.dumps(message)))


@pytest.fixture
def handler(race):
    race.begin_race(instant=True)
    return FakeProtocolHandler(FakeBackend(race))


def test_register_and_duplicate(race):
    registry: set[str] = set()
    a = FakeProtocolHandler(FakeBackend(race), registry)
    b = FakeProtocolHandler(FakeBackend(race), registry)
    assert send(a, RequestId=1, Operation="Register", Value="AI-Kart-WIIManager")["Success"] is True
    reply = send(b, RequestId=1, Operation="Register", Value="ai-kart-wiimanager")
    assert reply["Error"]["Code"] == "INVALID_REQUEST"


def test_get_resource_shapes(handler):
    reply = send(handler, RequestId=7, Operation="GetResource", Resource="GameState")
    assert reply == {"RequestId": 7, "Success": True, "Value": 2, "MessageType": "Response", "Error": None}
    assert send(handler, RequestId=8, Operation="GetResource", Resource="VehicleSpeed")["Error"]["Code"] == "INVALID_REQUEST"
    assert send(handler, RequestId=9, Operation="GetResource", Resource="Nope")["Error"]["Code"] == "INVALID_RESOURCE"


def test_get_resources_batch_items_fail_individually(handler):
    reply = send(handler, RequestId=3, Operation="GetResources",
                 Value=[{"Resource": "VehicleSpeed", "PlayerId": 0}, {"Resource": "Nope", "PlayerId": None}])
    ok, bad = reply["Value"]
    assert ok["Success"] is True and bad["Success"] is False and "not found" in bad["Error"]


def test_not_ready_when_no_race(race):
    h = FakeProtocolHandler(FakeBackend(race))
    reply = send(h, RequestId=1, Operation="GetResource", Resource="VehicleSpeed", PlayerId=0)
    assert reply["Error"]["Code"] == "RESOURCE_NOT_READY"


def test_ignores_status_responses_and_garbage(handler):
    assert handler.handle_line(json.dumps({"MessageType": "Response", "RequestId": 1})) is None
    assert json.loads(handler.handle_line("not json"))["Error"]["Code"] == "INVALID_REQUEST"
