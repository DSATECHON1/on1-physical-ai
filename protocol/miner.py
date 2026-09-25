"""
ON1 Physical AI Miner Protocol.

The miner is responsible for receiving a mission request and producing
execution evidence.

This implementation is deliberately local and deterministic.

It does NOT:
- connect to Konnex
- register a wallet
- submit a transaction
- communicate with a blockchain
- claim physical robot execution

It provides the software-side execution role that can later be connected
to a real Konnex miner runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from .mission import (
    ExecutionEvidence,
    MachineIdentity,
    MissionRequest,
    MissionTarget,
    TelemetryPoint,
    utc_now,
)


MINER_PROTOCOL_ROLE = "miner"


@dataclass
class MinerExecutionResult:
    """Result of local miner execution."""

    mission_request: MissionRequest
    evidence: ExecutionEvidence

    def to_dict(self):
        return {
            "role": MINER_PROTOCOL_ROLE,
            "missionRequest": self.mission_request.to_dict(),
            "evidence": self.evidence.to_dict(),
        }


class Miner:
    """
    Local ON1 mission miner.

    The miner converts a mission request into deterministic simulated
    navigation telemetry and execution evidence.
    """

    def __init__(
        self,
        machine: MachineIdentity,
        miner_id: str = "ON1-MINER-001",
    ) -> None:
        self.machine = machine
        self.miner_id = miner_id

    def execute(
        self,
        mission_request: MissionRequest,
    ) -> MinerExecutionResult:
        """
        Execute a navigation mission locally.

        The simulation moves one coordinate step toward the target on
        each telemetry step. The resulting evidence is passed to the
        validator layer without any network submission.
        """

        self._validate_request(mission_request)

        started_at = utc_now()

        telemetry = self._generate_navigation_telemetry(
            start=mission_request.start,
            target=mission_request.target,
        )

        final_point = telemetry[-1]

        reached_target = (
            math.isclose(
                final_point.x,
                mission_request.target.x,
                abs_tol=1e-9,
            )
            and math.isclose(
                final_point.y,
                mission_request.target.y,
                abs_tol=1e-9,
            )
        )

        status = "COMPLETED" if reached_target else "FAILED"

        completed_at = utc_now()

        evidence = ExecutionEvidence(
            evidence_id=f"EVD-{mission_request.mission_id}",
            mission_id=mission_request.mission_id,
            machine=self.machine,
            task_type=mission_request.task_type,
            start=mission_request.start,
            target=mission_request.target,
            telemetry=telemetry,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            generated_at=completed_at,
            execution_mode="software-simulation",
        )

        return MinerExecutionResult(
            mission_request=mission_request,
            evidence=evidence,
        )

    def _validate_request(
        self,
        mission_request: MissionRequest,
    ) -> None:
        if not mission_request.mission_id:
            raise ValueError("Mission request requires mission_id.")

        if not mission_request.task_type:
            raise ValueError("Mission request requires task_type.")

        if mission_request.machine != self.machine:
            raise ValueError(
                "Mission machine identity does not match this miner."
            )

        coordinates = (
            mission_request.start,
            mission_request.target,
        )

        for coordinate in coordinates:
            if not math.isfinite(float(coordinate.x)):
                raise ValueError("Mission x coordinate must be finite.")

            if not math.isfinite(float(coordinate.y)):
                raise ValueError("Mission y coordinate must be finite.")

    def _generate_navigation_telemetry(
        self,
        start: MissionTarget,
        target: MissionTarget,
    ) -> List[TelemetryPoint]:
        """
        Generate deterministic navigation telemetry.

        For normal integer-style navigation such as (0,0) -> (10,10),
        this produces one telemetry observation per movement step.
        """

        x = float(start.x)
        y = float(start.y)

        target_x = float(target.x)
        target_y = float(target.y)

        telemetry: List[TelemetryPoint] = []

        max_steps = max(
            abs(int(round(target_x - x))),
            abs(int(round(target_y - y))),
            1,
        )

        for step in range(1, max_steps + 1):
            remaining_steps = max_steps - step + 1

            dx = target_x - x
            dy = target_y - y

            if remaining_steps > 1:
                x += dx / remaining_steps
                y += dy / remaining_steps
            else:
                x = target_x
                y = target_y

            distance = math.sqrt(
                ((target_x - x) ** 2)
                + ((target_y - y) ** 2)
            )

            speed = math.sqrt(
                ((dx / max(remaining_steps, 1)) ** 2)
                + ((dy / max(remaining_steps, 1)) ** 2)
            )

            battery = max(
                0.0,
                100.0 - (step * 2.0),
            )

            telemetry.append(
                TelemetryPoint(
                    timestamp=utc_now(),
                    step=step,
                    x=round(x, 6),
                    y=round(y, 6),
                    distance_from_target=round(distance, 6),
                    battery=round(battery, 2),
                    speed=round(speed, 6),
                )
            )

        return telemetry
