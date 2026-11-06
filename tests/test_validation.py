from ai_kart_wii.state.validation import StateValidator, check_value


def good_raw():
    return {"CurrentLap": 1, "CurrentLapCandidate": 1, "MaxLap": 3, "CurrentKcp": 2, "MaxKcp": 9,
            "DirectionX": 0.0, "DirectionY": 0.0, "DirectionZ": 1.0, "RacePosition": 3, "TeamId": 1,
            "PhysicsPositionX": 10.0, "PhysicsPositionZ": 20.0, "RaceFrameCounter": 100}


def test_in_range_values_pass():
    assert check_value("RacePosition", 12) is None
    assert check_value("TeamId", 0) is None
    assert check_value("Unknown", 12345) is None


def test_out_of_range_and_allowed_set():
    assert check_value("RacePosition", 13).reason == "above 12"
    assert "not one of" in check_value("TeamId", 2).reason
    assert check_value("VehicleSpeed", float("nan")).reason == "not finite"


def test_good_read_has_no_violations():
    assert StateValidator().check_raw(good_raw()) == []


def test_lap_width_mismatch_is_diagnosed():
    raw = good_raw()
    raw["CurrentLap"] = 256  # uint8 01 read as big-endian uint16
    problems = StateValidator().check_raw(raw)
    assert any("uint8 read as uint16" in p.reason for p in problems)


def test_direction_not_unit_and_kcp_order():
    raw = good_raw()
    raw.update(DirectionZ=3.0, CurrentKcp=20)
    reasons = " ".join(p.reason for p in StateValidator().check_raw(raw))
    assert "vector length" in reasons and "exceeds MaxKcp" in reasons


def test_sequence_detects_restart_and_teleport():
    v = StateValidator()
    v.check_sequence({"RaceFrameCounter": 500, "PhysicsPositionX": 0.0, "PhysicsPositionZ": 0.0})
    teleport = v.check_sequence({"RaceFrameCounter": 501, "PhysicsPositionX": 99999.0, "PhysicsPositionZ": 0.0})
    assert "jumped" in teleport[0].reason
    back = v.check_sequence({"RaceFrameCounter": 3})
    assert "backwards" in back[0].reason


def test_summary_counts():
    v = StateValidator()
    for _ in range(5):
        v.check_raw({"RacePosition": 99})
    assert "5x" in v.summary()
