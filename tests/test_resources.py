import json
from pathlib import Path

from ai_kart_wii.state.resources import OWN_STATE_RESOURCES, RECORDING_INPUT_RESOURCES, RESOURCES

DATA = json.loads((Path(__file__).parent / "data" / "memory_subset.json").read_text())


def test_every_used_resource_is_declared():
    for name in OWN_STATE_RESOURCES + RECORDING_INPUT_RESOURCES:
        assert name in RESOURCES, name


def test_specs_match_memory_json_subset():
    assert set(RESOURCES) == set(DATA)
    for name, spec in RESOURCES.items():
        entry = DATA[name]
        assert spec.dtype == entry["type"], name
        assert spec.length == entry["length"], name
        assert spec.dynamic == bool(entry.get("dynamic")), name
        assert spec.race_only == (entry.get("availability", 0) == 1), name
