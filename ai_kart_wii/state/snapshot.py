"""Typed snapshot of the AI's own kart, built from raw resource values."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from ai_kart_wii.geometry import Vec3, yaw_from_direction


@dataclass(frozen=True, slots=True)
class PlayerState:
    slot: int
    race_frame: int  # RaceFrameCounter, the key used to align images and state
    position: Vec3
    direction: Vec3
    speed: float
    race_completion: float
    race_completion_max: float
    race_position: int
    lap_u16: int  # "CurrentLap" (documented layout, uint16)
    lap_candidate: int  # "CurrentLapCandidate" (first byte, what the UI uses)
    max_lap: int
    kcp: int
    max_kcp: int
    checkpoint_id: int
    drift_state: int
    mt_charge: int
    smt_charge: int
    star_timer: int
    mega_timer: int
    shock_timer: int
    crush_timer: int
    boost_types: int
    respawn_state: int
    pre_respawn_timer: int
    solid_oob_timer: int
    air_time: int
    team_id: int
    player_type: int
    received_ns: int = 0  # perf_counter_ns when the batch came back
    read_latency_ms: float = 0.0
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    # Lap handling is uncertain (see memory.json notes). Until verified in game we
    # follow the DebugManager and use the uint8 candidate.
    @property
    def lap(self) -> int:
        return self.lap_candidate

    @property
    def yaw(self) -> float:
        return yaw_from_direction(self.direction.x, self.direction.z)

    @property
    def team_name(self) -> str:
        return {0: "Purple", 1: "Blue"}.get(self.team_id, f"Team {self.team_id}")

    @property
    def is_respawning(self) -> bool:
        return self.respawn_state != 0 or self.pre_respawn_timer > 0 or self.solid_oob_timer > 0

    @classmethod
    def from_raw(
        cls,
        slot: int,
        raw: Mapping[str, Any],
        received_ns: int = 0,
        read_latency_ms: float = 0.0,
    ) -> "PlayerState":
        def num(name: str) -> float:
            value = raw[name]
            return float(value)

        def integer(name: str) -> int:
            value = raw[name]
            if isinstance(value, float) and not math.isfinite(value):
                return 0
            return int(value)

        return cls(
            slot=slot,
            race_frame=integer("RaceFrameCounter"),
            position=Vec3(num("PhysicsPositionX"), num("PhysicsPositionY"), num("PhysicsPositionZ")),
            direction=Vec3(num("DirectionX"), num("DirectionY"), num("DirectionZ")),
            speed=num("VehicleSpeed"),
            race_completion=num("RaceCompletion"),
            race_completion_max=num("RaceCompletionMax"),
            race_position=integer("RacePosition"),
            lap_u16=integer("CurrentLap"),
            lap_candidate=integer("CurrentLapCandidate"),
            max_lap=integer("MaxLap"),
            kcp=integer("CurrentKcp"),
            max_kcp=integer("MaxKcp"),
            checkpoint_id=integer("CheckpointId"),
            drift_state=integer("DriftState"),
            mt_charge=integer("MtCharge"),
            smt_charge=integer("SmtCharge"),
            star_timer=integer("StarTimer"),
            mega_timer=integer("MegaTimer"),
            shock_timer=integer("ShockTimer"),
            crush_timer=integer("CrushTimer"),
            boost_types=integer("BoostTypes"),
            respawn_state=integer("RespawnState"),
            pre_respawn_timer=integer("PreRespawnTimer"),
            solid_oob_timer=integer("SolidOutOfBoundsTimer"),
            air_time=integer("AirTime"),
            team_id=integer("TeamId"),
            player_type=integer("PlayerType"),
            received_ns=received_ns,
            read_latency_ms=read_latency_ms,
            raw=dict(raw),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "race_frame": self.race_frame,
            "position": list(self.position.as_tuple()),
            "direction": list(self.direction.as_tuple()),
            "speed": self.speed,
            "race_completion": self.race_completion,
            "race_completion_max": self.race_completion_max,
            "race_position": self.race_position,
            "lap_u16": self.lap_u16,
            "lap_candidate": self.lap_candidate,
            "max_lap": self.max_lap,
            "kcp": self.kcp,
            "max_kcp": self.max_kcp,
            "checkpoint_id": self.checkpoint_id,
            "drift_state": self.drift_state,
            "mt_charge": self.mt_charge,
            "smt_charge": self.smt_charge,
            "star_timer": self.star_timer,
            "mega_timer": self.mega_timer,
            "shock_timer": self.shock_timer,
            "crush_timer": self.crush_timer,
            "boost_types": self.boost_types,
            "respawn_state": self.respawn_state,
            "pre_respawn_timer": self.pre_respawn_timer,
            "solid_oob_timer": self.solid_oob_timer,
            "air_time": self.air_time,
            "team_id": self.team_id,
            "player_type": self.player_type,
            "read_latency_ms": round(self.read_latency_ms, 3),
        }
