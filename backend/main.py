"""
ON1 Physical AI
Backend Mission Engine

Prototype backend for:
- Machine identity
- Mission execution
- Telemetry
- Evidence generation
- Local validation
- PoPW-style scoring
- Machine reputation
- Machine memory
- Mission evidence persistence
- Evidence artifact export
- Local evidence fingerprint
- Firebase / Firestore persistence

This is a software prototype.

It does NOT represent:
- live Konnex verification
- blockchain verification
- an on-chain transaction
- physical robot hardware
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_NAME = "ON1 Physical AI"
PROTOTYPE_VERSION = "0.5.0"

VALIDATOR_ID = "ON1-BACKEND-VALIDATOR-001"

ROBOT_ID = "ON1-R001"
ROBOT_IDENTITY = "ON1-MACHINE-001"
ROBOT_MODEL = "ON1 Virtual Navigator"

# Firestore device document
FIRESTORE_DEVICE_COLLECTION = "devices"
FIRESTORE_DEVICE_ID = "on1-unit-01"

# Firestore machine memory subcollection
FIRESTORE_MEMORY_COLLECTION = "memory"

# Firestore mission evidence subcollection
FIRESTORE_MISSION_COLLECTION = "missions"

# Render Secret File
FIREBASE_CREDENTIALS_PATH = (
    "/etc/secrets/"
    "on1-physical-ai-firebase-adminsdk-fbsvc-6aad4f0b06.json"
)

OUTPUT_DIRECTORY = Path("backend_output")
OUTPUT_FILE = OUTPUT_DIRECTORY / "mission-result.json"


# ============================================================
# FIREBASE / FIRESTORE
# ============================================================

def initialize_firestore():
    """
    Initialize Firebase Admin SDK using the Render Secret File.

    The credential JSON is never stored in source code.
    """

    if not firebase_admin._apps:

        if not Path(
            FIREBASE_CREDENTIALS_PATH
        ).exists():

            raise FileNotFoundError(
                "Firebase credential file was not found at "
                f"{FIREBASE_CREDENTIALS_PATH}"
            )

        credential = credentials.Certificate(
            FIREBASE_CREDENTIALS_PATH
        )

        firebase_admin.initialize_app(
            credential
        )

    return firestore.client()


db = initialize_firestore()


device_ref = db.collection(
    FIRESTORE_DEVICE_COLLECTION
).document(
    FIRESTORE_DEVICE_ID
)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(
        timezone.utc
    ).isoformat().replace("+00:00", "Z")


def generate_id(prefix: str) -> str:
    """Generate a short prototype identifier."""

    return (
        f"{prefix}-"
        f"{uuid.uuid4().hex[:12].upper()}"
    )


def calculate_distance(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Calculate Euclidean distance between two coordinates."""

    return math.sqrt(
        (x2 - x1) ** 2
        + (y2 - y1) ** 2
    )


def calculate_evidence_fingerprint(
    evidence_package: dict[str, Any],
) -> str:
    """
    Create a local SHA-256 fingerprint of the
    evidence package.

    This is NOT a blockchain hash and does NOT
    represent Konnex verification.
    """

    canonical_json = json.dumps(
        evidence_package,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        canonical_json
    ).hexdigest()


# ============================================================
# FIRESTORE DEVICE STATE
# ============================================================

def load_device_state() -> dict[str, Any]:
    """
    Load the existing device state from Firestore.

    Existing Firestore values are treated as the
    persistent source of truth.

    In particular, an existing reputation value is
    never replaced by the Python prototype default.
    """

    snapshot = device_ref.get()

    if not snapshot.exists:

        initial_state = {
            "name": (
                "ON1 Physical AI Unit 01"
            ),

            "connection_status": "online",

            "operational_status": "idle",

            "mission_count": 0,

            "successful_missions": 0,

            "failed_missions": 0,

            "reputation": 50,
        }

        device_ref.set(
            initial_state
        )

        return initial_state

    return snapshot.to_dict() or {}


def save_device_state(
    robot: "Robot",
) -> None:
    """
    Persist machine state to Firestore.

    Existing device fields not managed by this backend
    are preserved.
    """

    device_ref.set(
        {
            "connection_status": "online",

            "operational_status": (
                robot.status.lower()
            ),

            "mission_count": (
                robot.mission_count
            ),

            "successful_missions": (
                robot.successful_missions
            ),

            "failed_missions": (
                robot.failed_missions
            ),

            "reputation": (
                robot.reputation_score
            ),
        },
        merge=True,
    )


# ============================================================
# FIRESTORE MACHINE MEMORY
# ============================================================

def load_memory() -> list[
    dict[str, Any]
]:
    """
    Load persistent machine memory from Firestore.
    """

    memory_ref = device_ref.collection(
        FIRESTORE_MEMORY_COLLECTION
    )

    snapshots = (
        memory_ref
        .order_by(
            "recordedAt"
        )
        .stream()
    )

    memory = []

    for snapshot in snapshots:

        record = snapshot.to_dict()

        if record:
            memory.append(
                record
            )

    return memory


def save_memory(
    memory: dict[str, Any],
) -> None:
    """
    Persist a compact machine memory record.
    """

    memory_id = memory[
        "memoryId"
    ]

    device_ref.collection(
        FIRESTORE_MEMORY_COLLECTION
    ).document(
        memory_id
    ).set(
        memory
    )


# ============================================================
# FIRESTORE MISSION EVIDENCE
# ============================================================

def save_mission_evidence(
    mission: dict[str, Any],
) -> None:
    """
    Persist the complete verified mission/evidence package.

    This is intentionally separate from the compact machine
    memory record.

    Machine memory answers:
        "What has this machine done?"

    Mission evidence answers:
        "What exactly happened during this mission,
         and how was the work validated?"

    The mission document is stored at:

        devices/{deviceId}/missions/{missionId}
    """

    mission_id = mission[
        "missionId"
    ]

    mission_record = {
        "recordType": "mission_evidence",

        "project": PROJECT_NAME,

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "missionId": mission_id,

        "robotId": mission[
            "robotId"
        ],

        "taskType": mission[
            "taskType"
        ],

        "start": mission[
            "start"
        ],

        "target": mission[
            "target"
        ],

        "startedAt": mission[
            "startedAt"
        ],

        "completedAt": mission[
            "completedAt"
        ],

        "status": mission[
            "status"
        ],

        "telemetry": mission[
            "telemetry"
        ],

        "evidence": mission[
            "evidence"
        ],

        "validatorResult": mission[
            "validatorResult"
        ],

        "powpScore": mission[
            "powpScore"
        ],

        "verification": {
            "verified": mission[
                "validatorResult"
            ][
                "verified"
            ],

            "validatorId": mission[
                "validatorResult"
            ][
                "validatorId"
            ],

            "passedChecks": mission[
                "validatorResult"
            ][
                "passedChecks"
            ],

            "totalChecks": mission[
                "validatorResult"
            ][
                "totalChecks"
            ],
        },

        "integration": {
            "physicalHardware": False,

            "konnexVerified": False,

            "onChainVerified": False,
        },

        "persistedAt": utc_now(),
    }

    device_ref.collection(
        FIRESTORE_MISSION_COLLECTION
    ).document(
        mission_id
    ).set(
        mission_record,
        merge=True,
    )


def update_mission_evidence_artifact(
    mission_id: str,
    output_path: Path,
    fingerprint: str,
) -> None:
    """
    Add evidence-artifact and fingerprint metadata to
    an existing persisted mission evidence record.

    This is performed after the evidence package has been
    exported and fingerprinted.
    """

    mission_ref = (
        device_ref
        .collection(
            FIRESTORE_MISSION_COLLECTION
        )
        .document(
            mission_id
        )
    )

    mission_ref.set(
        {
            "evidenceArtifact": {
                "path": str(
                    output_path
                ),

                "sha256": fingerprint,

                "algorithm": "SHA-256",

                "scope": (
                    "local backend "
                    "evidence package"
                ),
            },

            "integration": {
                "physicalHardware": False,

                "konnexVerified": False,

                "onChainVerified": False,
            },

            "fingerprintedAt": utc_now(),
        },
        merge=True,
    )


# ============================================================
# ROBOT
# ============================================================

class Robot:

    def __init__(
        self,
        robot_id: str = ROBOT_ID,
        identity: str = ROBOT_IDENTITY,
        model: str = ROBOT_MODEL,
    ) -> None:

        self.robot_id = robot_id
        self.identity = identity
        self.model = model

        self.status = "IDLE"

        device_state = load_device_state()

        self.mission_count = int(
            device_state.get(
                "mission_count",
                0,
            )
        )

        self.successful_missions = int(
            device_state.get(
                "successful_missions",
                0,
            )
        )

        self.failed_missions = int(
            device_state.get(
                "failed_missions",
                0,
            )
        )

        # IMPORTANT:
        # Existing Firestore reputation is used.
        #
        # Therefore:
        # devices/on1-unit-01/reputation = 100
        #
        # remains 100 and is NOT replaced by
        # the old Python prototype default of 50.

        self.reputation_score = int(
            device_state.get(
                "reputation",
                50,
            )
        )

        self.memory = load_memory()

    def update_reputation(
        self,
        verified: bool,
    ) -> None:
        """Update reputation after validation."""

        if verified:

            self.successful_missions += 1

            self.reputation_score = min(
                100,
                self.reputation_score + 5,
            )

        else:

            self.failed_missions += 1

            self.reputation_score = max(
                0,
                self.reputation_score - 5,
            )

        save_device_state(
            self
        )

    def remember(
        self,
        mission: dict[str, Any],
    ) -> None:
        """Store a compact persistent mission memory record."""

        memory = {
            "memoryId": generate_id(
                "MEM"
            ),

            "missionId": mission[
                "missionId"
            ],

            "taskType": mission[
                "taskType"
            ],

            "result": (
                "Verified"
                if mission[
                    "validatorResult"
                ]["verified"]
                else "Failed"
            ),

            "powpScore": mission[
                "powpScore"
            ],

            "recordedAt": utc_now(),
        }

        self.memory.append(
            memory
        )

        save_memory(
            memory
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "robotId": self.robot_id,

            "identity": self.identity,

            "model": self.model,

            "status": self.status,

            "missionCount": (
                self.mission_count
            ),

            "successfulMissions": (
                self.successful_missions
            ),

            "failedMissions": (
                self.failed_missions
            ),

            "reputationScore": (
                self.reputation_score
            ),

            "memory": self.memory,
        }


# ============================================================
# MISSION ENGINE
# ============================================================

class MissionEngine:

    def __init__(
        self,
        robot: Robot,
    ) -> None:

        self.robot = robot

    # ========================================================
    # EXECUTE NAVIGATION
    # ========================================================

    def execute_navigation(
        self,
        start: tuple[int, int] = (0, 0),
        target: tuple[int, int] = (10, 10),
    ) -> dict[str, Any]:

        mission_id = generate_id(
            "MSN"
        )

        started_at = utc_now()

        self.robot.status = "EXECUTING"

        self.robot.mission_count += 1

        save_device_state(
            self.robot
        )

        telemetry: list[
            dict[str, Any]
        ] = []

        target_x, target_y = target

        steps = max(
            abs(target_x - start[0]),
            abs(target_y - start[1]),
        )

        if steps == 0:
            steps = 1

        battery = 100

        for step in range(
            1,
            steps + 1,
        ):

            progress = step / steps

            x = (
                start[0]
                + (
                    target_x
                    - start[0]
                )
                * progress
            )

            y = (
                start[1]
                + (
                    target_y
                    - start[1]
                )
                * progress
            )

            x = round(
                x,
                4,
            )

            y = round(
                y,
                4,
            )

            distance = calculate_distance(
                x,
                y,
                target_x,
                target_y,
            )

            battery = max(
                0,
                100 - (step * 2),
            )

            telemetry.append(
                {
                    "timestamp": utc_now(),

                    "step": step,

                    "x": x,

                    "y": y,

                    "distanceFromTarget": (
                        distance
                    ),

                    "battery": battery,

                    "speed": 1,
                }
            )

        completed_at = utc_now()

        final_position = telemetry[-1]

        target_reached = (
            final_position["x"]
            == target_x
            and
            final_position["y"]
            == target_y
        )

        mission = {

            "missionId": mission_id,

            "robotId": (
                self.robot.robot_id
            ),

            "taskType": "Navigation",

            "start": {
                "x": start[0],
                "y": start[1],
            },

            "target": {
                "x": target_x,
                "y": target_y,
            },

            "startedAt": started_at,

            "completedAt": completed_at,

            "telemetry": telemetry,

            "status": (
                "COMPLETED"
                if target_reached
                else "FAILED"
            ),
        }

        mission[
            "evidence"
        ] = self.generate_evidence(
            mission
        )

        mission[
            "validatorResult"
        ] = self.validate_mission(
            mission
        )

        mission[
            "powpScore"
        ] = self.calculate_powp_score(
            mission[
                "validatorResult"
            ]
        )

        verified = mission[
            "validatorResult"
        ]["verified"]

        self.robot.status = "IDLE"

        self.robot.update_reputation(
            verified
        )

        # Persist compact machine memory.
        self.robot.remember(
            mission
        )

        # Persist the complete mission evidence package.
        #
        # This is separate from machine memory so the
        # complete evidence trail remains available.
        save_mission_evidence(
            mission
        )

        return mission

    # ========================================================
    # EVIDENCE
    # ========================================================

    def generate_evidence(
        self,
        mission: dict[str, Any],
    ) -> dict[str, Any]:

        return {

            "evidenceId": generate_id(
                "EVD"
            ),

            "missionId": mission[
                "missionId"
            ],

            "robotId": mission[
                "robotId"
            ],

            "taskType": mission[
                "taskType"
            ],

            "startPosition": mission[
                "start"
            ],

            "targetPosition": mission[
                "target"
            ],

            "telemetryPoints": len(
                mission[
                    "telemetry"
                ]
            ),

            "missionStartedAt": (
                mission[
                    "startedAt"
                ]
            ),

            "missionCompletedAt": (
                mission[
                    "completedAt"
                ]
            ),

            "status": mission[
                "status"
            ],

            "generatedAt": utc_now(),
        }

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate_mission(
        self,
        mission: dict[str, Any],
    ) -> dict[str, Any]:

        telemetry_present = (
            isinstance(
                mission.get(
                    "telemetry"
                ),
                list,
            )
            and len(
                mission[
                    "telemetry"
                ]
            ) > 0
        )

        target = mission[
            "target"
        ]

        final_point = (
            mission[
                "telemetry"
            ][-1]
            if telemetry_present
            else None
        )

        target_reached = (
            final_point is not None
            and final_point["x"]
            == target["x"]
            and final_point["y"]
            == target["y"]
        )

        checks = {

            "missionStarted": bool(
                mission.get(
                    "startedAt"
                )
            ),

            "missionCompleted": (
                mission.get(
                    "status"
                )
                == "COMPLETED"
            ),

            "telemetryPresent": (
                telemetry_present
            ),

            "targetReached": (
                target_reached
            ),

            "robotIdentityPresent": (
                mission.get(
                    "robotId"
                )
                == self.robot.robot_id
            ),

            "evidenceGenerated": bool(
                mission.get(
                    "evidence"
                )
                and mission[
                    "evidence"
                ].get(
                    "evidenceId"
                )
            ),
        }

        passed_checks = sum(
            1
            for result in checks.values()
            if result
        )

        total_checks = len(
            checks
        )

        verified = (
            passed_checks
            == total_checks
            and total_checks > 0
        )

        return {

            "validatorId": (
                VALIDATOR_ID
            ),

            "validatedAt": utc_now(),

            "checks": checks,

            "passedChecks": (
                passed_checks
            ),

            "totalChecks": (
                total_checks
            ),

            "verified": verified,
        }

    # ========================================================
    # PoPW-STYLE SCORE
    # ========================================================

    @staticmethod
    def calculate_powp_score(
        validator_result: dict[str, Any],
    ) -> int:

        total = validator_result[
            "totalChecks"
        ]

        passed = validator_result[
            "passedChecks"
        ]

        if total == 0:
            return 0

        return round(
            (
                passed
                / total
            )
            * 100
        )


# ============================================================
# APPLICATION STATE
# ============================================================

robot = Robot()

engine = MissionEngine(
    robot
)


# ============================================================
# REGISTRATION
# ============================================================

def register_robot() -> dict[str, Any]:

    return {

        "project": (
            PROJECT_NAME
        ),

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "registered": True,

        "registeredAt": utc_now(),

        "robot": robot.to_dict(),
    }


# ============================================================
# RUN MISSION
# ============================================================

def run_mission() -> dict[str, Any]:

    mission = (
        engine.execute_navigation()
    )

    result = {

        "project": (
            PROJECT_NAME
        ),

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "simulation": {

            "type": "backend",

            "hardwareConnected": False,

            "konnexIntegrated": False,

            "onChainVerified": False,
        },

        "generatedAt": utc_now(),

        "robot": robot.to_dict(),

        "mission": mission,
    }

    return result


# ============================================================
# EXPORT EVIDENCE
# ============================================================

def export_evidence(
    result: dict[str, Any],
) -> tuple[Path, str]:

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    fingerprint = (
        calculate_evidence_fingerprint(
            result
        )
    )

    result[
        "evidenceFingerprint"
    ] = {

        "algorithm": "SHA-256",

        "value": fingerprint,

        "scope": (
            "local backend "
            "evidence package"
        ),

        "konnexVerified": False,

        "onChainVerified": False,
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            default=str,
        )

        file.write("\n")

    # Update the already-persisted mission evidence record
    # with its exported artifact and fingerprint.
    mission = result.get(
        "mission",
        {}
    )

    mission_id = mission.get(
        "missionId"
    )

    if mission_id:

        update_mission_evidence_artifact(
            mission_id=mission_id,

            output_path=OUTPUT_FILE,

            fingerprint=fingerprint,
        )

    return (
        OUTPUT_FILE,
        fingerprint,
    )


# ============================================================
# DEMO OUTPUT
# ============================================================

def print_demo(
    result: dict[str, Any],
    output_path: Path,
    fingerprint: str,
) -> None:

    mission = result[
        "mission"
    ]

    validator = mission[
        "validatorResult"
    ]

    print()

    print(
        "=" * 60
    )

    print(
        "ON1 PHYSICAL AI — "
        "BACKEND MISSION ENGINE"
    )

    print(
        "=" * 60
    )

    print()

    print("PROJECT")

    print(
        PROJECT_NAME
    )

    print()

    print(
        "PROTOTYPE VERSION"
    )

    print(
        PROTOTYPE_VERSION
    )

    print()

    print("ROBOT")

    print(
        f"  Robot ID: "
        f"{result['robot']['robotId']}"
    )

    print(
        f"  Identity: "
        f"{result['robot']['identity']}"
    )

    print(
        f"  Model: "
        f"{result['robot']['model']}"
    )

    print()

    print("MISSION")

    print(
        f"  Mission ID: "
        f"{mission['missionId']}"
    )

    print(
        f"  Task: "
        f"{mission['taskType']}"
    )

    print(
        f"  Route: "
        f"({mission['start']['x']}, "
        f"{mission['start']['y']})"
        f" -> "
        f"({mission['target']['x']}, "
        f"{mission['target']['y']})"
    )

    print()

    print("TELEMETRY")

    print(
        f"  Points: "
        f"{len(mission['telemetry'])}"
    )

    print()

    print("EVIDENCE")

    print(
        f"  Evidence ID: "
        f"{mission['evidence']['evidenceId']}"
    )

    print()

    print("VALIDATION")

    print(
        f"  Passed: "
        f"{validator['passedChecks']}/"
        f"{validator['totalChecks']}"
    )

    print(
        f"  Verified: "
        f"{validator['verified']}"
    )

    print()

    print(
        "PoPW-STYLE SCORE"
    )

    print(
        f"  {mission['powpScore']}/100"
    )

    print()

    print("REPUTATION")

    print(
        f"  Score: "
        f"{result['robot']['reputationScore']}/100"
    )

    print()

    print("MEMORY")

    print(
        f"  Records: "
        f"{len(result['robot']['memory'])}"
    )

    print()

    print("MISSION EVIDENCE")

    print(
        "  Firestore: "
        f"devices/{FIRESTORE_DEVICE_ID}/"
        f"{FIRESTORE_MISSION_COLLECTION}/"
        f"{mission['missionId']}"
    )

    print()

    print("EVIDENCE ARTIFACT")

    print(
        f"  {output_path}"
    )

    print()

    print(
        "LOCAL SHA-256 FINGERPRINT"
    )

    print(
        f"  {fingerprint}"
    )

    print()

    print("KONNEX")

    print(
        "  Integrated: False"
    )

    print()

    print("ON-CHAIN")

    print(
        "  Verified: False"
    )

    print()

    print(
        "=" * 60
    )

    print(
        "MISSION COMPLETE"
    )

    print(
        "=" * 60
    )

    print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    registration = (
        register_robot()
    )

    print(
        "Robot registered:",
        registration[
            "robot"
        ][
            "robotId"
        ],
    )

    result = (
        run_mission()
    )

    output_path, fingerprint = (
        export_evidence(
            result
        )
    )

    print_demo(
        result,
        output_path,
        fingerprint,
    )
