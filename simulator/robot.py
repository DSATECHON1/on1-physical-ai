"""
ON1 Physical AI
Virtual Robot Simulator

This module simulates a physical robot completing a navigation mission.
It generates:
- Robot identity
- Mission execution
- Position telemetry
- Movement evidence
- Mission result
- Basic work verification data

This is a software-only prototype.
No physical hardware or Konnex network integration is claimed here.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any


# ============================================================
# Utility Functions
# ============================================================

def utc_now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    """Generate a short unique identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def distance_between(
    x1: float,
    y1: float,
    x2: float,
    y2: float
) -> float:
    """Calculate straight-line distance between two points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


# ============================================================
# Robot
# ============================================================

@dataclass
class Robot:
    """
    Represents a virtual machine participating in ON1 Physical AI.
    """

    robot_id: str
    identity: str
    model: str
    status: str = "IDLE"
    mission_count: int = 0
    successful_missions: int = 0
    failed_missions: int = 0
    reputation_score: float = 50.0
    memory: List[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = []

    def register(self) -> Dict[str, Any]:
        """Return the robot registration record."""

        return {
            "robotId": self.robot_id,
            "identity": self.identity,
            "model": self.model,
            "status": self.status,
            "registeredAt": utc_now(),
            "reputationScore": self.reputation_score,
        }

    def update_reputation(self, successful: bool) -> None:
        """
        Update robot reputation after a mission.

        Successful missions increase reputation.
        Failed missions decrease reputation.
        """

        if successful:
            self.reputation_score += 5
        else:
            self.reputation_score -= 5

        self.reputation_score = max(
            0.0,
            min(100.0, self.reputation_score)
        )

    def remember(self, mission: Dict[str, Any]) -> None:
        """Store mission information in machine memory."""

        memory_entry = {
            "missionId": mission["missionId"],
            "taskType": mission["taskType"],
            "target": mission["target"],
            "status": mission["status"],
            "powpScore": mission["powpScore"],
            "completedAt": mission["completedAt"],
        }

        self.memory.append(memory_entry)

        # Keep the latest 20 memories in this prototype.
        self.memory = self.memory[-20:]


# ============================================================
# Telemetry
# ============================================================

@dataclass
class TelemetryPoint:
    """A single robot telemetry observation."""

    timestamp: str
    x: float
    y: float
    distanceFromTarget: float
    battery: float
    speed: float


# ============================================================
# Mission
# ============================================================

class Mission:
    """
    Represents a navigation mission assigned to a virtual robot.
    """

    def __init__(
        self,
        robot: Robot,
        start: tuple[float, float],
        target: tuple[float, float],
        task_type: str = "NAVIGATION"
    ) -> None:

        self.mission_id = generate_id("MISSION")
        self.robot = robot
        self.start = start
        self.target = target
        self.task_type = task_type

        self.status = "CREATED"
        self.started_at: str | None = None
        self.completed_at: str | None = None

        self.telemetry: List[TelemetryPoint] = []

        self.evidence: Dict[str, Any] = {}
        self.validator_result: Dict[str, Any] = {}

        self.powp_score = 0.0

    # --------------------------------------------------------
    # Mission Execution
    # --------------------------------------------------------

    def execute(self) -> Dict[str, Any]:
        """
        Execute the simulated navigation mission.
        """

        self.robot.status = "WORKING"
        self.robot.mission_count += 1

        self.status = "RUNNING"
        self.started_at = utc_now()

        current_x, current_y = self.start

        target_x, target_y = self.target

        initial_distance = distance_between(
            current_x,
            current_y,
            target_x,
            target_y
        )

        # Simulate movement in 10 steps.
        steps = 10

        for step in range(1, steps + 1):

            progress = step / steps

            current_x = (
                self.start[0]
                + (self.target[0] - self.start[0]) * progress
            )

            current_y = (
                self.start[1]
                + (self.target[1] - self.start[1]) * progress
            )

            remaining_distance = distance_between(
                current_x,
                current_y,
                target_x,
                target_y
            )

            battery = max(
                0.0,
                100.0 - (step * 1.5)
            )

            speed = 1.0

            telemetry_point = TelemetryPoint(
                timestamp=utc_now(),
                x=round(current_x, 3),
                y=round(current_y, 3),
                distanceFromTarget=round(
                    remaining_distance,
                    3
                ),
                battery=round(battery, 2),
                speed=speed,
            )

            self.telemetry.append(
                telemetry_point
            )

            # Small delay makes local execution visibly simulate
            # movement without creating a long-running process.
            time.sleep(0.05)

        final_distance = distance_between(
            self.target[0],
            self.target[1],
            current_x,
            current_y
        )

        self.completed_at = utc_now()

        success = final_distance <= 0.01

        if success:
            self.status = "COMPLETED"
            self.robot.successful_missions += 1
        else:
            self.status = "FAILED"
            self.robot.failed_missions += 1

        self.robot.status = "IDLE"

        self.build_evidence(
            initial_distance=initial_distance,
            final_distance=final_distance
        )

        self.validate()

        self.robot.update_reputation(success)

        result = self.to_dict()

        self.robot.remember(result)

        return result

    # --------------------------------------------------------
    # Evidence
    # --------------------------------------------------------

    def build_evidence(
        self,
        initial_distance: float,
        final_distance: float
    ) -> None:
        """
        Build a machine-work evidence bundle.

        This represents the evidence that a future validator
        could inspect.
        """

        self.evidence = {
            "evidenceId": generate_id("EVIDENCE"),
            "missionId": self.mission_id,
            "robotId": self.robot.robot_id,
            "taskType": self.task_type,
            "startPosition": {
                "x": self.start[0],
                "y": self.start[1],
            },
            "targetPosition": {
                "x": self.target[0],
                "y": self.target[1],
            },
            "initialDistance": round(
                initial_distance,
                3
            ),
            "finalDistance": round(
                final_distance,
                3
            ),
            "telemetryPoints": len(
                self.telemetry
            ),
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "status": self.status,
        }

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    def validate(self) -> None:
        """
        Perform basic local validation of the mission evidence.

        This is NOT yet a Konnex validator.
        """

        checks = {
            "missionStarted": self.started_at is not None,
            "missionCompleted": self.completed_at is not None,
            "telemetryPresent": len(self.telemetry) >= 2,
            "targetReached": (
                self.evidence.get("finalDistance", 999)
                <= 0.01
            ),
            "robotIdentityPresent": bool(
                self.robot.robot_id
            ),
        }

        passed_checks = sum(
            1 for value in checks.values()
            if value
        )

        total_checks = len(checks)

        self.powp_score = round(
            (passed_checks / total_checks) * 100,
            2
        )

        verified = (
            passed_checks == total_checks
            and self.status == "COMPLETED"
        )

        self.validator_result = {
            "validatorId": "ON1-LOCAL-VALIDATOR-001",
            "validatedAt": utc_now(),
            "checks": checks,
            "passedChecks": passed_checks,
            "totalChecks": total_checks,
            "powpScore": self.powp_score,
            "verified": verified,
        }

    # --------------------------------------------------------
    # Serialization
    # --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return the complete mission as a JSON-ready dictionary."""

        return {
            "missionId": self.mission_id,
            "robotId": self.robot.robot_id,
            "taskType": self.task_type,

            "start": {
                "x": self.start[0],
                "y": self.start[1],
            },

            "target": {
                "x": self.target[0],
                "y": self.target[1],
            },

            "status": self.status,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,

            "telemetry": [
                asdict(point)
                for point in self.telemetry
            ],

            "evidence": self.evidence,

            "validatorResult": self.validator_result,

            "powpScore": self.powp_score,

            "robotReputation": self.robot.reputation_score,
        }


# ============================================================
# Demonstration
# ============================================================

def run_demo() -> Dict[str, Any]:
    """
    Run one complete ON1 Physical AI simulation.
    """

    robot = Robot(
        robot_id="ON1-R001",
        identity="ON1-MACHINE-001",
        model="ON1-VIRTUAL-NAV-01",
    )

    print("=" * 60)
    print("ON1 PHYSICAL AI — VIRTUAL ROBOT SIMULATOR")
    print("=" * 60)

    print("\n[1] Registering robot...")

    registration = robot.register()

    print(
        f"Robot: {registration['robotId']}"
    )

    print(
        f"Identity: {registration['identity']}"
    )

    print(
        f"Model: {registration['model']}"
    )

    print("\n[2] Creating navigation mission...")

    mission = Mission(
        robot=robot,
        start=(0.0, 0.0),
        target=(10.0, 10.0),
    )

    print(
        f"Mission: {mission.mission_id}"
    )

    print(
        f"Start: {mission.start}"
    )

    print(
        f"Target: {mission.target}"
    )

    print("\n[3] Executing mission...")

    result = mission.execute()

    print(
        f"Mission status: {result['status']}"
    )

    print(
        f"Telemetry points: "
        f"{len(result['telemetry'])}"
    )

    print(
        f"PoPW score: "
        f"{result['powpScore']}"
    )

    print(
        f"Verified: "
        f"{result['validatorResult']['verified']}"
    )

    print(
        f"Robot reputation: "
        f"{result['robotReputation']}"
    )

    print("\n[4] Machine memory updated.")

    print(
        f"Memory entries: "
        f"{len(robot.memory)}"
    )

    print("\n" + "=" * 60)
    print("SIMULATION COMPLETE")
    print("=" * 60)

    return {
        "robot": {
            "robotId": robot.robot_id,
            "identity": robot.identity,
            "model": robot.model,
            "status": robot.status,
            "missionCount": robot.mission_count,
            "successfulMissions": robot.successful_missions,
            "failedMissions": robot.failed_missions,
            "reputationScore": robot.reputation_score,
            "memory": robot.memory,
        },
        "mission": result,
    }


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    run_demo()
