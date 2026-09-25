"""
ON1 Physical AI Mission Protocol.

Defines the canonical machine-readable objects exchanged between
the ON1 mission requester, miner, and validator.

The protocol is intentionally deterministic so that the same verified
mission evidence produces the same SHA-256 fingerprint.

This module is local protocol infrastructure. It does not perform
Konnex network communication or blockchain submission.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


PROTOCOL_NAME = "ON1 Physical AI Mission Protocol"
PROTOCOL_VERSION = "0.1.0"
SCHEMA_NAME = "on1.physical-ai.mission.v1"


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def calculate_distance(
    start: Tuple[float, float],
    target: Tuple[float, float],
) -> float:
    """Calculate Euclidean distance between two 2D coordinates."""
    dx = float(target[0]) - float(start[0])
    dy = float(target[1]) - float(start[1])
    return math.sqrt((dx * dx) + (dy * dy))


def calculate_evidence_fingerprint(payload: Dict[str, Any]) -> str:
    """
    Generate a deterministic SHA-256 fingerprint.

    JSON keys are sorted and separators are canonicalized so equivalent
    dictionaries produce the same fingerprint.
    """
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class MissionTarget:
    """A 2D mission coordinate."""

    x: float
    y: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": float(self.x),
            "y": float(self.y),
        }


@dataclass(frozen=True)
class MachineIdentity:
    """
    Machine identity used throughout the local protocol.

    The identity is descriptive and does not imply cryptographic
    hardware-rooted identity.
    """

    robot_id: str
    identity: str
    model: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "robotId": self.robot_id,
            "identity": self.identity,
            "model": self.model,
        }


@dataclass(frozen=True)
class TelemetryPoint:
    """A single machine telemetry observation."""

    timestamp: str
    step: int
    x: float
    y: float
    distance_from_target: float
    battery: float
    speed: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "step": int(self.step),
            "x": float(self.x),
            "y": float(self.y),
            "distanceFromTarget": float(self.distance_from_target),
            "battery": float(self.battery),
            "speed": float(self.speed),
        }


@dataclass
class MissionRequest:
    """
    Canonical mission request.

    This represents the workload request that a future Konnex-compatible
    transport layer could carry over a network.
    """

    mission_id: str
    task_type: str
    machine: MachineIdentity
    start: MissionTarget
    target: MissionTarget
    requested_at: str = field(default_factory=utc_now)
    protocol: str = PROTOCOL_NAME
    protocol_version: str = PROTOCOL_VERSION
    schema: str = SCHEMA_NAME

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol,
            "protocolVersion": self.protocol_version,
            "schema": self.schema,
            "missionId": self.mission_id,
            "taskType": self.task_type,
            "machine": self.machine.to_dict(),
            "start": self.start.to_dict(),
            "target": self.target.to_dict(),
            "requestedAt": self.requested_at,
        }


@dataclass
class ExecutionEvidence:
    """
    Evidence produced by the miner after executing a mission.

    The evidence describes execution. It does not claim that the
    telemetry is hardware-rooted or blockchain-verified.
    """

    evidence_id: str
    mission_id: str
    machine: MachineIdentity
    task_type: str
    start: MissionTarget
    target: MissionTarget
    telemetry: List[TelemetryPoint]
    status: str
    started_at: str
    completed_at: str
    generated_at: str
    execution_mode: str = "software-simulation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "missionId": self.mission_id,
            "machine": self.machine.to_dict(),
            "robotId": self.machine.robot_id,
            "taskType": self.task_type,
            "start": self.start.to_dict(),
            "target": self.target.to_dict(),
            "telemetry": [
                point.to_dict()
                for point in self.telemetry
            ],
            "telemetryPoints": len(self.telemetry),
            "status": self.status,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "generatedAt": self.generated_at,
            "executionMode": self.execution_mode,
            "hardwareRooted": False,
            "konnexVerified": False,
            "onChainVerified": False,
        }


@dataclass
class ValidationResult:
    """
    Result produced by the ON1 validator.

    The validator checks mission consistency and evidence completeness.
    """

    validator_id: str
    checks: Dict[str, bool]
    passed_checks: int
    total_checks: int
    verified: bool
    score: float
    validated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validatorId": self.validator_id,
            "checks": dict(self.checks),
            "passedChecks": int(self.passed_checks),
            "totalChecks": int(self.total_checks),
            "verified": bool(self.verified),
            "score": float(self.score),
            "validatedAt": self.validated_at,
        }


@dataclass
class MissionResponse:
    """
    Complete protocol response after miner execution and validation.
    """

    mission_request: MissionRequest
    evidence: ExecutionEvidence
    validation: ValidationResult
    evidence_fingerprint: str
    powp_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": PROTOCOL_NAME,
            "protocolVersion": PROTOCOL_VERSION,
            "schema": SCHEMA_NAME,
            "missionRequest": self.mission_request.to_dict(),
            "evidence": self.evidence.to_dict(),
            "validation": self.validation.to_dict(),
            "powp": {
                "score": float(self.powp_score),
                "method": "ON1 local validation check ratio",
            },
            "evidenceFingerprint": {
                "algorithm": "SHA-256",
                "value": self.evidence_fingerprint,
                "scope": "local ON1 mission evidence core",
                "konnexVerified": False,
                "onChainVerified": False,
            },
            "integration": {
                "physicalHardware": False,
                "konnexIntegrated": False,
                "konnexVerified": False,
                "onChainVerified": False,
            },
        }


def build_canonical_evidence_payload(
    mission_request: MissionRequest,
    evidence: ExecutionEvidence,
    validation: ValidationResult,
    powp_score: float,
) -> Dict[str, Any]:
    """
    Build the canonical payload used for fingerprinting.

    Mutable transport metadata, timestamps generated outside the core
    evidence model, adapter metadata, and the fingerprint itself are
    deliberately excluded.
    """

    return {
        "schema": SCHEMA_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "mission": {
            "missionId": mission_request.mission_id,
            "taskType": mission_request.task_type,
            "machine": mission_request.machine.to_dict(),
            "start": mission_request.start.to_dict(),
            "target": mission_request.target.to_dict(),
            "status": evidence.status,
        },
        "telemetry": [
            point.to_dict()
            for point in evidence.telemetry
        ],
        "validation": {
            "validatorId": validation.validator_id,
            "checks": dict(validation.checks),
            "passedChecks": validation.passed_checks,
            "totalChecks": validation.total_checks,
            "verified": validation.verified,
            "score": validation.score,
        },
        "powp": {
            "score": float(powp_score),
            "method": "ON1 local validation check ratio",
        },
        "integration": {
            "physicalHardware": False,
            "konnexIntegrated": False,
            "konnexVerified": False,
            "onChainVerified": False,
        },
    }


def fingerprint_mission_response(
    mission_request: MissionRequest,
    evidence: ExecutionEvidence,
    validation: ValidationResult,
    powp_score: float,
) -> str:
    """Calculate the canonical SHA-256 fingerprint for a mission."""
    canonical_payload = build_canonical_evidence_payload(
        mission_request=mission_request,
        evidence=evidence,
        validation=validation,
        powp_score=powp_score,
    )

    return calculate_evidence_fingerprint(canonical_payload)
