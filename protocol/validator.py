"""
ON1 Physical AI Validator Protocol.

The validator independently evaluates miner-produced mission evidence.

Validation is intentionally deterministic and local.

Current checks:
1. Mission started
2. Mission completed
3. Telemetry present
4. Target reached
5. Machine identity present
6. Evidence generated

PoPW-style score:

    passed checks / total checks * 100

This validator does NOT claim:
- hardware-rooted verification
- Konnex verification
- on-chain verification
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict

from .mission import (
    ExecutionEvidence,
    MissionRequest,
    ValidationResult,
    utc_now,
)


VALIDATOR_PROTOCOL_ROLE = "validator"

VALIDATOR_ID = "ON1-PROTOCOL-VALIDATOR-001"


@dataclass
class ValidatorResult:
    """Validator output containing the validation result."""

    mission_request: MissionRequest
    validation: ValidationResult

    def to_dict(self):
        return {
            "role": VALIDATOR_PROTOCOL_ROLE,
            "missionRequest": self.mission_request.to_dict(),
            "validation": self.validation.to_dict(),
        }


class Validator:
    """
    Local ON1 protocol validator.

    The validator does not trust the miner's declared score. It derives
    its own result from the mission request and execution evidence.
    """

    def __init__(
        self,
        validator_id: str = VALIDATOR_ID,
    ) -> None:
        self.validator_id = validator_id

    def validate(
        self,
        mission_request: MissionRequest,
        evidence: ExecutionEvidence,
    ) -> ValidatorResult:
        """
        Validate miner-produced execution evidence.

        Returns an independent ValidationResult.
        """

        checks: Dict[str, bool] = {
            "missionStarted": self._check_mission_started(
                mission_request,
                evidence,
            ),
            "missionCompleted": self._check_mission_completed(
                evidence,
            ),
            "telemetryPresent": self._check_telemetry_present(
                evidence,
            ),
            "targetReached": self._check_target_reached(
                mission_request,
                evidence,
            ),
            "robotIdentityPresent": self._check_robot_identity(
                mission_request,
                evidence,
            ),
            "evidenceGenerated": self._check_evidence_generated(
                evidence,
            ),
        }

        passed_checks = sum(
            1
            for passed in checks.values()
            if passed
        )

        total_checks = len(checks)

        verified = (
            total_checks > 0
            and passed_checks == total_checks
        )

        score = (
            (passed_checks / total_checks) * 100.0
            if total_checks
            else 0.0
        )

        validation = ValidationResult(
            validator_id=self.validator_id,
            checks=checks,
            passed_checks=passed_checks,
            total_checks=total_checks,
            verified=verified,
            score=round(score, 2),
            validated_at=utc_now(),
        )

        return ValidatorResult(
            mission_request=mission_request,
            validation=validation,
        )

    @staticmethod
    def _check_mission_started(
        mission_request: MissionRequest,
        evidence: ExecutionEvidence,
    ) -> bool:
        return bool(
            mission_request.mission_id
            and evidence.mission_id
            and mission_request.mission_id == evidence.mission_id
            and evidence.started_at
        )

    @staticmethod
    def _check_mission_completed(
        evidence: ExecutionEvidence,
    ) -> bool:
        return (
            evidence.status == "COMPLETED"
            and bool(evidence.completed_at)
        )

    @staticmethod
    def _check_telemetry_present(
        evidence: ExecutionEvidence,
    ) -> bool:
        return (
            isinstance(evidence.telemetry, list)
            and len(evidence.telemetry) > 0
        )

    @staticmethod
    def _check_target_reached(
        mission_request: MissionRequest,
        evidence: ExecutionEvidence,
    ) -> bool:
        if not evidence.telemetry:
            return False

        final_point = evidence.telemetry[-1]

        return (
            math.isclose(
                final_point.x,
                mission_request.target.x,
                abs_tol=1e-6,
            )
            and math.isclose(
                final_point.y,
                mission_request.target.y,
                abs_tol=1e-6,
            )
            and math.isclose(
                final_point.distance_from_target,
                0.0,
                abs_tol=1e-6,
            )
        )

    @staticmethod
    def _check_robot_identity(
        mission_request: MissionRequest,
        evidence: ExecutionEvidence,
    ) -> bool:
        request_machine = mission_request.machine
        evidence_machine = evidence.machine

        return bool(
            request_machine.robot_id
            and request_machine.identity
            and request_machine.model
            and evidence_machine.robot_id
            and evidence_machine.identity
            and evidence_machine.model
            and request_machine.robot_id
            == evidence_machine.robot_id
            and request_machine.identity
            == evidence_machine.identity
        )

    @staticmethod
    def _check_evidence_generated(
        evidence: ExecutionEvidence,
    ) -> bool:
        return bool(
            evidence.evidence_id
            and evidence.mission_id
            and evidence.generated_at
            and evidence.task_type
        )
