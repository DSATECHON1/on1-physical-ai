"""
ON1 Physical AI
Virtual Robot Simulator

Software-first physical AI prototype for:
- Machine identity
- Mission execution
- Telemetry
- Verifiable work evidence
- Local validation
- PoPW-style scoring
- Machine memory
- Reputation

This is a simulation.
It does not claim physical hardware or live Konnex integration.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# Configuration
# ============================================================

OUTPUT_DIRECTORY = Path("simulation_output")
OUTPUT_FILE = OUTPUT_DIRECTORY / "mission-result.json"


# ============================================================
# Utility Functions
# ============================================================

def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    """Generate a short unique identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def distance_between(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Calculate Euclidean distance between two positions."""
    return math.sqrt(
        (x2 - x1) ** 2
        + (y2 - y1) ** 2
    )


# ============================================================
# Robot
# ============================================================

@dataclass
class Robot:
    """Represents a virtual machine."""

    robot_id: str
    identity: str
    model: str

    status: str = "IDLE"

    mission_count: int = 0
    successful_missions: int = 0
    failed_missions: int = 0

    reputation_score: float = 50.0

    memory: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = []

    def register(self) -> dict[str, Any]:
        """Create the robot registration record."""

        return {
            "robotId": self.robot_id,
            "identity": self.identity,
            "model": self.model,
            "status": self.status,
            "registeredAt": utc_now(),
            "reputationScore": self.reputation_score,
        }

    def update_reputation(self, successful: bool) -> None:
        """Update reputation after mission completion."""

        if successful:
            self.reputation_score += 5.0
        else:
            self.reputation_score -= 5.0

        self.reputation_score = round(
            max(
                0.0,
                min(100.0, self.reputation_score),
            ),
            2,
        )

    def remember(self, mission: dict[str, Any]) -> None:
        """Store a summary of completed work in machine memory."""

        memory_entry = {
            "missionId": mission["missionId"],
            "taskType": mission["taskType"],
            "target": mission["target"],
            "status": mission["status"],
            "powpScore": mission["powpScore"],
            "verified": mission["validatorResult"]["verified"],
            "completedAt": mission["completedAt"],
        }

        self.memory.append(memory_entry)

        # Keep the latest 20 memories.
        self.memory = self.memory[-20:]


# ============================================================
# Telemetry
# ============================================================

@dataclass
class TelemetryPoint:
    """One simulated robot telemetry observation."""

    timestamp: str
    step: int
    x: float
    y: float
    distance_from_target: float
    battery: float
    speed: float


# ============================================================
# Mission
# ============================================================

class Mission:
    """Represents a navigation mission."""

    def __init__(
        self,
        robot: Robot,
        start: tuple[float, float],
        target: tuple[float, float],
        task_type: str = "NAVIGATION",
    ) -> None:

        self.mission_id = generate_id("MISSION")

        self.robot = robot

        self.start = start
        self.target = target

        self.task_type = task_type

        self.status = "CREATED"

        self.started_at: str | None = None
        self.completed_at: str | None = None

        self.telemetry: list[TelemetryPoint] = []

        self.evidence: dict[str, Any] = {}
        self.validator_result: dict[str, Any] = {}

        self.powp_score = 0.0

    # --------------------------------------------------------
    # Execute Mission
    # --------------------------------------------------------

    def execute(self) -> dict[str, Any]:
        """Execute the simulated navigation mission."""

        self.robot.status = "WORKING"

        self.robot.mission_count += 1

        self.status = "RUNNING"

        self.started_at = utc_now()

        initial_distance = distance_between(
            self.start[0],
            self.start[1],
            self.target[0],
            self.target[1],
        )

        current_x = self.start[0]
        current_y = self.start[1]

        steps = 10

        for step in range(1, steps + 1):

            progress = step / steps

            current_x = (
                self.start[0]
                + (
                    self.target[0]
                    - self.start[0]
                )
                * progress
            )

            current_y = (
                self.start[1]
                + (
                    self.target[1]
                    - self.start[1]
                )
                * progress
            )

            remaining_distance = distance_between(
                current_x,
                current_y,
                self.target[0],
                self.target[1],
            )

            battery = max(
                0.0,
                100.0 - (step * 1.5),
            )

            telemetry_point = TelemetryPoint(
                timestamp=utc_now(),
                step=step,
                x=round(current_x, 3),
                y=round(current_y, 3),
                distance_from_target=round(
                    remaining_distance,
                    3,
                ),
                battery=round(
                    battery,
                    2,
                ),
                speed=1.0,
            )

            self.telemetry.append(
                telemetry_point
            )

            time.sleep(0.05)

        final_distance = distance_between(
            current_x,
            current_y,
            self.target[0],
            self.target[1],
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
            final_distance=final_distance,
        )

        self.validate()

        self.robot.update_reputation(
            successful=success
        )

        result = self.to_dict()

        self.robot.remember(result)

        return result

    # --------------------------------------------------------
    # Evidence
    # --------------------------------------------------------

    def build_evidence(
        self,
        initial_distance: float,
        final_distance: float,
    ) -> None:
        """Create the machine-work evidence bundle."""

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
                3,
            ),

            "finalDistance": round(
                final_distance,
                3,
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
        Perform local evidence validation.

        This is an ON1 Physical AI prototype validator.
        It is not yet a Konnex validator.
        """

        checks = {
            "missionStarted": (
                self.started_at is not None
            ),

            "missionCompleted": (
                self.completed_at is not None
            ),

            "telemetryPresent": (
                len(self.telemetry) >= 2
            ),

            "targetReached": (
                self.evidence.get(
                    "finalDistance",
                    999.0,
                )
                <= 0.01
            ),

            "robotIdentityPresent": bool(
                self.robot.robot_id
            ),

            "evidenceGenerated": bool(
                self.evidence
            ),
        }

        passed_checks = sum(
            1
            for value in checks.values()
            if value
        )

        total_checks = len(checks)

        self.powp_score = round(
            (
                passed_checks
                / total_checks
            )
            * 100,
            2,
        )

        verified = (
            passed_checks == total_checks
            and self.status == "COMPLETED"
        )

        self.validator_result = {
            "validatorId": (
                "ON1-LOCAL-VALIDATOR-001"
            ),

            "validatedAt": utc_now(),

            "checks": checks,

            "passedChecks": passed_checks,

            "totalChecks": total_checks,

            "powpScore": self.powp_score,

            "verified": verified,
        }

    # --------------------------------------------------------
    # Convert to Dictionary
    # --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return the complete mission record."""

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
                {
                    "timestamp": point.timestamp,
                    "step": point.step,
                    "x": point.x,
                    "y": point.y,
                    "distanceFromTarget": (
                        point.distance_from_target
                    ),
                    "battery": point.battery,
                    "speed": point.speed,
                }
                for point in self.telemetry
            ],

            "evidence": self.evidence,

            "validatorResult": (
                self.validator_result
            ),

            "powpScore": self.powp_score,

            "robotReputation": (
                self.robot.reputation_score
            ),
        }


# ============================================================
# Save Evidence Artifact
# ============================================================

def save_result(
    robot: Robot,
    mission_result: dict[str, Any],
) -> Path:
    """Save the complete simulation result as JSON."""

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = {
        "project": "ON1 Physical AI",

        "prototypeVersion": "0.2.0",

        "simulation": {
            "type": "software-only",
            "hardwareConnected": False,
            "konnexIntegrated": False,
        },

        "generatedAt": utc_now(),

        "robot": {
            "robotId": robot.robot_id,
            "identity": robot.identity,
            "model": robot.model,
            "status": robot.status,
            "missionCount": robot.mission_count,
            "successfulMissions": (
                robot.successful_missions
            ),
            "failedMissions": (
                robot.failed_missions
            ),
            "reputationScore": (
                robot.reputation_score
            ),
            "memory": robot.memory,
        },

        "mission": mission_result,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    return OUTPUT_FILE


# ============================================================
# Demo
# ============================================================

def run_demo() -> dict[str, Any]:
    """Run one complete ON1 Physical AI simulation."""

    print("=" * 60)
    print(
        "ON1 PHYSICAL AI — "
        "VIRTUAL ROBOT SIMULATOR"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # Register Robot
    # --------------------------------------------------------

    robot = Robot(
        robot_id="ON1-R001",
        identity="ON1-MACHINE-001",
        model="ON1-VIRTUAL-NAV-01",
    )

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

    # --------------------------------------------------------
    # Create Mission
    # --------------------------------------------------------

    print(
        "\n[2] Creating navigation mission..."
    )

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

    # --------------------------------------------------------
    # Execute
    # --------------------------------------------------------

    print(
        "\n[3] Executing mission..."
    )

    result = mission.execute()

    print(
        f"Mission status: {result['status']}"
    )

    print(
        "Telemetry points: "
        f"{len(result['telemetry'])}"
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    print(
        "\n[4] Validating machine work..."
    )

    print(
        "PoPW score: "
        f"{result['powpScore']}"
    )

    print(
        "Verified: "
        f"{result['validatorResult']['verified']}"
    )

    print(
        "Validation checks: "
        f"{result['validatorResult']['passedChecks']}"
        "/"
        f"{result['validatorResult']['totalChecks']}"
    )

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

    print(
        "\n[5] Updating machine memory..."
    )

    print(
        "Memory entries: "
        f"{len(robot.memory)}"
    )

    print(
        "Robot reputation: "
        f"{robot.reputation_score}"
    )

    # --------------------------------------------------------
    # Save Evidence
    # --------------------------------------------------------

    print(
        "\n[6] Creating evidence artifact..."
    )

    output_path = save_result(
        robot=robot,
        mission_result=result,
    )

    print(
        f"Evidence saved to: {output_path}"
    )

    print("\n" + "=" * 60)
    print("SIMULATION COMPLETE")
    print("=" * 60)

    return {
        "robot": asdict(robot),
        "mission": result,
        "evidenceFile": str(output_path),
    }


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    run_demo()
