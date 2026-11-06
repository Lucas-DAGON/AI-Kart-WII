"""Resources the AI uses, mirrored from MTWManager/src/Config/memory.json.

Generated from the real file; tests/test_resources.py checks that every entry still
matches tests/data/memory_subset.json (a copy of those entries). If you rename or
retype a resource in memory.json, update both and the test tells you what drifted.
"""

from __future__ import annotations

from typing import NamedTuple


class ResourceSpec(NamedTuple):
    name: str
    dtype: str
    length: int
    dynamic: bool  # needs a player id (resolved through cache.json)
    race_only: bool  # availability == 1: only readable when GameState == 2


RESOURCES: dict[str, ResourceSpec] = {
    "GameState": ResourceSpec("GameState", "uint8", 1, False, False),
    "LeCodeTrackId": ResourceSpec("LeCodeTrackId", "uint32", 4, False, False),
    "LocalPlayerNumber": ResourceSpec("LocalPlayerNumber", "int8", 1, True, True),
    "PlayerType": ResourceSpec("PlayerType", "int32", 4, True, True),
    "TeamId": ResourceSpec("TeamId", "int32", 4, True, True),
    "Score": ResourceSpec("Score", "uint16", 2, True, True),
    "RaceCompletion": ResourceSpec("RaceCompletion", "single", 4, True, True),
    "RaceCompletionMax": ResourceSpec("RaceCompletionMax", "single", 4, True, True),
    "RacePosition": ResourceSpec("RacePosition", "uint8", 1, True, True),
    "RespawnState": ResourceSpec("RespawnState", "uint8", 1, True, True),
    "CurrentLap": ResourceSpec("CurrentLap", "uint16", 2, True, True),
    "CurrentLapCandidate": ResourceSpec("CurrentLapCandidate", "uint8", 1, True, True),
    "MaxLap": ResourceSpec("MaxLap", "uint8", 1, True, True),
    "CurrentKcp": ResourceSpec("CurrentKcp", "uint8", 1, True, True),
    "MaxKcp": ResourceSpec("MaxKcp", "uint8", 1, True, True),
    "RaceFrameCounter": ResourceSpec("RaceFrameCounter", "uint32", 4, True, True),
    "VehicleSpeed": ResourceSpec("VehicleSpeed", "single", 4, True, True),
    "DriftState": ResourceSpec("DriftState", "int16", 2, True, True),
    "MtCharge": ResourceSpec("MtCharge", "int16", 2, True, True),
    "SmtCharge": ResourceSpec("SmtCharge", "int16", 2, True, True),
    "StarTimer": ResourceSpec("StarTimer", "int16", 2, True, True),
    "MegaTimer": ResourceSpec("MegaTimer", "int16", 2, True, True),
    "ShockTimer": ResourceSpec("ShockTimer", "int16", 2, True, True),
    "CrushTimer": ResourceSpec("CrushTimer", "int16", 2, True, True),
    "BoostTypes": ResourceSpec("BoostTypes", "uint16", 2, True, True),
    "DirectionX": ResourceSpec("DirectionX", "single", 4, True, True),
    "DirectionY": ResourceSpec("DirectionY", "single", 4, True, True),
    "DirectionZ": ResourceSpec("DirectionZ", "single", 4, True, True),
    "PhysicsPositionX": ResourceSpec("PhysicsPositionX", "single", 4, True, True),
    "PhysicsPositionY": ResourceSpec("PhysicsPositionY", "single", 4, True, True),
    "PhysicsPositionZ": ResourceSpec("PhysicsPositionZ", "single", 4, True, True),
    "PreRespawnTimer": ResourceSpec("PreRespawnTimer", "int16", 2, True, True),
    "SolidOutOfBoundsTimer": ResourceSpec("SolidOutOfBoundsTimer", "int16", 2, True, True),
    "InputFlags0": ResourceSpec("InputFlags0", "uint32", 4, True, True),
    "InputFlags1": ResourceSpec("InputFlags1", "uint32", 4, True, True),
    "InputFlags2": ResourceSpec("InputFlags2", "uint32", 4, True, True),
    "InputFlags3": ResourceSpec("InputFlags3", "uint32", 4, True, True),
    "StickX": ResourceSpec("StickX", "single", 4, True, True),
    "StickY": ResourceSpec("StickY", "single", 4, True, True),
    "CheckpointId": ResourceSpec("CheckpointId", "uint32", 4, True, True),
    "LapCount": ResourceSpec("LapCount", "uint8", 1, True, True),
    "RaceInfoStage": ResourceSpec("RaceInfoStage", "uint32", 4, True, True),
    "RaceDataPlayerCount": ResourceSpec("RaceDataPlayerCount", "uint8", 1, True, True),
    "RaceDataLocalPlayerCount": ResourceSpec("RaceDataLocalPlayerCount", "uint8", 1, True, True),
    "HudPlayerId0": ResourceSpec("HudPlayerId0", "uint8", 1, True, True),
    "AirTime": ResourceSpec("AirTime", "uint32", 4, True, True),
    "IsBike": ResourceSpec("IsBike", "uint32", 4, True, True),
}

SLOT_COUNT = 12

GAME_STATE = "GameState"
GAME_STATE_RACE_NOT_LOADED = 0
GAME_STATE_CACHE_BUILD_REQUESTED = 1
GAME_STATE_CACHE_READY = 2

TRACK_ID = "LeCodeTrackId"  # Le-Code id (NOT CourseId), always readable

# Polled for the AI's own kart. Order is irrelevant; names are the memory.json keys.
OWN_STATE_RESOURCES: tuple[str, ...] = (
    "RaceFrameCounter",
    "PhysicsPositionX", "PhysicsPositionY", "PhysicsPositionZ",
    "DirectionX", "DirectionY", "DirectionZ",
    "VehicleSpeed",
    "RaceCompletion", "RaceCompletionMax", "RacePosition",
    "CurrentLap", "CurrentLapCandidate", "MaxLap",
    "CurrentKcp", "MaxKcp", "CheckpointId",
    "DriftState", "MtCharge", "SmtCharge",
    "StarTimer", "MegaTimer", "ShockTimer", "CrushTimer",
    "BoostTypes", "RespawnState", "PreRespawnTimer", "SolidOutOfBoundsTimer",
    "AirTime", "TeamId", "PlayerType",
)

# Extra reads used when recording a human (their stick/buttons as the game saw them).
RECORDING_INPUT_RESOURCES: tuple[str, ...] = (
    "StickX", "StickY", "InputFlags0", "InputFlags1", "InputFlags2", "InputFlags3",
)

SLOT_DISCOVERY_RESOURCE = "PlayerType"
PLAYER_TYPE_LOCAL = 0  # LivePlayerSnapshot.PlayerTypeText: 0 Local, 1 CPU, 3 Ghost, 4 Online, 5 None
