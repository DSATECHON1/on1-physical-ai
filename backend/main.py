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
- Konnex integration boundary
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
import os
import uuid
from copy import deepcopy
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
PROTOTYPE_VERSION = "0.5.1"

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

# Konnex adapter boundary
KONNEX_ADAPTER_VERSION = "0.1.0"
KONNEX_ADAPTER_STATUS = "READY_FOR_KONNEX_REVIEW"

# Evidence fingerprint scope.
#
# IMPORTANT:
# The fingerprint intentionally covers the canonical ON1
# mission evidence core only.
#
# It does NOT include:
# - the fingerprint itself
# - the Konnex adapter payload
# - the exported artifact metadata
#
# This prevents circular hashing while giving the Konnex
# adapter a stable fingerprint to reference.
EVIDENCE_FINGERPRINT_SCOPE = (
    "local ON1 mission evidence core"
)

# GitHub Actions isolated CI mode.
#
# Production Render does NOT set this variable.
#
# When enabled:
# - Firebase credentials are not required
# - no Firestore data is read
# - no Firestore data is written
# - device/memory/mission persistence exists only in memory
#
# This allows GitHub Actions to test the backend mission
# engine without exposing or committing the Render secret.
CI_TEST_MODE = os.getenv("ON1_CI_TEST") == "1"


# ============================================================
# CI IN-MEMORY PERSISTENCE
# ============================================================

_CI_DEVICE_STATE: dict[str, Any] = {
    "name": "ON1 Physical AI Unit 01",
    "connection_status": "online",
    "operational_status": "idle",
    "mission_count": 0,
    "successful_missions": 0,
    "failed_missions": 0,
    "reputation": 50,
}

_CI_MEMORY: dict[str, dict[str, Any]] = {}

_CI_MISSIONS: dict[str, dict[str, Any]] = {}


class _CISnapshot:
    """Minimal Firestore-compatible snapshot for CI tests."""

    def __init__(
        self,
        data: dict[str, Any] | None,
    ) -> None:
        self._data = deepcopy(data)
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        if self._data is None:
            return None

        return deepcopy(self._data)


class _CIDocumentReference:
    """Minimal document reference used only in CI mode."""

    def __init__(
        self,
        collection_name: str,
        document_id: str,
    ) -> None:
        self.collection_name = collection_name
        self.document_id = document_id

    def get(self) -> _CISnapshot:
        if self.collection_name == FIRESTORE_DEVICE_COLLECTION:
            if self.document_id == FIRESTORE_DEVICE_ID:
                return _CISnapshot(
                    _CI_DEVICE_STATE
                )

        if (
            self.collection_name
            == FIRESTORE_MEMORY_COLLECTION
        ):
            memory = _CI_MEMORY.get(
                self.document_id
            )

            return _CISnapshot(memory)

        if (
            self.collection_name
            == FIRESTORE_MISSION_COLLECTION
        ):
            mission = _CI_MISSIONS.get(
                self.document_id
            )

            return _CISnapshot(mission)

        return _CISnapshot(None)

    def set(
        self,
        data: dict[str, Any],
        merge: bool = False,
    ) -> None:
        if self.collection_name == FIRESTORE_DEVICE_COLLECTION:
            if self.document_id != FIRESTORE_DEVICE_ID:
                return

            if merge:
                _CI_DEVICE_STATE.update(
                    deepcopy(data)
                )
            else:
                _CI_DEVICE_STATE.clear()
                _CI_DEVICE_STATE.update(
                    deepcopy(data)
                )

            return

        if self.collection_name == FIRESTORE_MEMORY_COLLECTION:
            existing = _CI_MEMORY.get(
                self.document_id,
                {},
            )

            if merge:
                existing.update(
                    deepcopy(data)
                )
                _CI_MEMORY[
                    self.document_id
                ] = existing
            else:
                _CI_MEMORY[
                    self.document_id
                ] = deepcopy(data)

            return

        if self.collection_name == FIRESTORE_MISSION_COLLECTION:
            existing = _CI_MISSIONS.get(
                self.document_id,
                {},
            )

            if merge:
                existing.update(
                    deepcopy(data)
                )
                _CI_MISSIONS[
                    self.document_id
                ] = existing
            else:
                _CI_MISSIONS[
                    self.document_id
                ] = deepcopy(data)


class _CIQuery:
    """Minimal query implementation for API latest-mission reads."""

    def __init__(
        self,
        collection_name: str,
        order_field: str | None = None,
        descending: bool = False,
    ) -> None:
        self.collection_name = collection_name
        self.order_field = order_field
        self.descending = descending

    def order_by(
        self,
        field: str,
        direction: Any = None,
    ) -> "_CIQuery":
        descending = False

        if direction is not None:
            direction_text = str(
                direction
            ).upper()

            descending = (
                "DESCENDING"
                in direction_text
            )

        return _CIQuery(
            collection_name=self.collection_name,
            order_field=field,
            descending=descending,
        )

    def stream(self):
        if self.collection_name == FIRESTORE_MEMORY_COLLECTION:
            records = list(
                _CI_MEMORY.values()
            )

        elif (
            self.collection_name
            == FIRESTORE_MISSION_COLLECTION
        ):
            records = list(
                _CI_MISSIONS.values()
            )

        else:
            records = []

        if self.order_field:
            records.sort(
                key=lambda record: (
                    record.get(
                        self.order_field,
                        "",
                    )
                    or ""
                ),
                reverse=self.descending,
            )

        for record in records:
            if (
                self.collection_name
                == FIRESTORE_MEMORY_COLLECTION
            ):
                document_id = record.get(
                    "memoryId",
                    "",
                )
            else:
                document_id = record.get(
                    "missionId",
                    "",
                )

            yield _CISnapshot(record)


class _CICollectionReference:
    """Minimal collection reference used only in CI mode."""

    def __init__(
        self,
        collection_name: str,
    ) -> None:
        self.collection_name = collection_name

    def document(
        self,
        document_id: str,
    ) -> _CIDocumentReference:
        return _CIDocumentReference(
            self.collection_name,
            document_id,
        )

    def order_by(
        self,
        field: str,
        direction: Any = None,
    ) -> _CIQuery:
        return _CIQuery(
            collection_name=self.collection_name,
        ).order_by(
            field,
            direction,
        )

    def stream(self):
        return _CIQuery(
            collection_name=self.collection_name
        ).stream()


class _CIDeviceReference:
    """Root device reference with Firestore-like subcollections."""

    def get(self) -> _CISnapshot:
        return _CISnapshot(
            _CI_DEVICE_STATE
        )

    def set(
        self,
        data: dict[str, Any],
        merge: bool = False,
    ) -> None:
        if merge:
            _CI_DEVICE_STATE.update(
                deepcopy(data)
            )
        else:
            _CI_DEVICE_STATE.clear()
            _CI_DEVICE_STATE.update(
                deepcopy(data)
            )

    def collection(
        self,
        collection_name: str,
    ) -> _CICollectionReference:
        return _CICollectionReference(
            collection_name
        )


# ============================================================
# FIREBASE / FIRESTORE
# ============================================================

def initialize_firestore():
    """
    Initialize Firebase Admin SDK using the Render Secret File.

    In CI mode, Firebase is deliberately skipped.
    """

    if CI_TEST_MODE:
        return None

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


if CI_TEST_MODE:
    device_ref = _CIDeviceReference()
else:
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
    ).isoformat().replace(
        "+00:00",
        "Z",
    )


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
    Create a deterministic local SHA-256 fingerprint.

    The package is converted into canonical JSON by:
    - sorting object keys
    - removing insignificant JSON separators
    - encoding as UTF-8

    This is NOT a blockchain hash and does NOT represent
    Konnex verification.
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


def build_fingerprint_package(
    mission: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the canonical ON1 mission evidence core used for
    the SHA-256 fingerprint.

    IMPORTANT:

    The fingerprint package deliberately excludes:
    - evidenceFingerprint
    - Konnex adapter data
    - export artifact metadata
    - generated export timestamps

    This prevents circular hashing and ensures that the
    fingerprint represents the actual mission evidence.

    The resulting scope is:

        local ON1 mission evidence core
    """

    return {
        "project": PROJECT_NAME,

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "machine": {
            "robotId": mission.get(
                "robotId"
            ),

            "identity": ROBOT_IDENTITY,

            "model": ROBOT_MODEL,
        },

        "mission": mission,

        "integration": {
            "physicalHardware": False,

            "konnexVerified": False,

            "onChainVerified": False,
        },
    }


# ============================================================
# KONNEX INTEGRATION BOUNDARY
# ============================================================

class KonnexAdapter:
    """
    Konnex integration boundary.

    This adapter does NOT connect to Konnex.

    Its responsibility at the current prototype stage is
    to transform an ON1 verified mission into a stable,
    machine-readable submission package that a future
    Konnex transport/validator implementation can consume.

    The adapter deliberately contains no:
    - wallet handling
    - private keys
    - chain connection
    - TAO transaction
    - Bittensor dependency
    - network submission

    This keeps the ON1 mission/evidence system independent
    from the future Konnex transport layer.
    """

    def __init__(
        self,
        version: str = KONNEX_ADAPTER_VERSION,
    ) -> None:

        self.version = version

    def build_submission_payload(
        self,
        mission: dict[str, Any],
        fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a Konnex-ready mission submission payload.

        The payload describes the evidence and verification
        already performed by ON1.

        It does NOT claim that Konnex has verified anything.

        The fingerprint is supplied by the canonical ON1
        evidence pipeline before this adapter is persisted.
        """

        validator = mission.get(
            "validatorResult",
            {},
        )

        evidence = mission.get(
            "evidence",
            {},
        )

        payload = {
            "schema": (
                "on1.physical-ai."
                "konnex-mission.v1"
            ),

            "adapter": {
                "name": "ON1 Konnex Adapter",
                "version": self.version,
                "status": (
                    KONNEX_ADAPTER_STATUS
                ),
            },

            "submission": {
                "missionId": mission.get(
                    "missionId"
                ),

                "submissionStatus": (
                    KONNEX_ADAPTER_STATUS
                ),

                "submittedToKonnex": False,

                "konnexVerified": False,

                "onChainVerified": False,
            },

            "machine": {
                "robotId": mission.get(
                    "robotId"
                ),

                "identity": ROBOT_IDENTITY,

                "model": ROBOT_MODEL,
            },

            "mission": {
                "taskType": mission.get(
                    "taskType"
                ),

                "start": mission.get(
                    "start"
                ),

                "target": mission.get(
                    "target"
                ),

                "startedAt": mission.get(
                    "startedAt"
                ),

                "completedAt": mission.get(
                    "completedAt"
                ),

                "status": mission.get(
                    "status"
                ),
            },

            "telemetry": {
                "points": mission.get(
                    "telemetry",
                    [],
                ),

                "count": len(
                    mission.get(
                        "telemetry",
                        [],
                    )
                ),
            },

            "evidence": {
                "evidenceId": evidence.get(
                    "evidenceId"
                ),

                "telemetryPoints": evidence.get(
                    "telemetryPoints"
                ),

                "generatedAt": evidence.get(
                    "generatedAt"
                ),

                "status": evidence.get(
                    "status"
                ),
            },

            "validation": {
                "validatorId": validator.get(
                    "validatorId"
                ),

                "verified": validator.get(
                    "verified",
                    False,
                ),

                "passedChecks": validator.get(
                    "passedChecks",
                    0,
                ),

                "totalChecks": validator.get(
                    "totalChecks",
                    0,
                ),

                "validatedAt": validator.get(
                    "validatedAt"
                ),
            },

            "powp": {
                "score": mission.get(
                    "powpScore",
                    0,
                ),

                "method": (
                    "ON1 local validation "
                    "check ratio"
                ),
            },

            "evidenceFingerprint": {
                "algorithm": "SHA-256",

                "value": fingerprint,

                "scope": (
                    EVIDENCE_FINGERPRINT_SCOPE
                ),
            },

            "integration": {
                "physicalHardware": False,

                "konnexVerified": False,

                "onChainVerified": False,
            },

            "preparedAt": utc_now(),
        }

        return payload


konnex_adapter = KonnexAdapter()


# ============================================================
# FIRESTORE DEVICE STATE
# ============================================================

def load_device_state() -> dict[str, Any]:
    """
    Load the existing device state.

    Production:
        Firestore is the persistent source of truth.

    CI:
        An isolated in-memory device state is used.

    Existing production reputation is never replaced by the
    Python prototype default.
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
    Persist machine state.

    Production writes to Firestore.

    CI writes only to the isolated in-memory test store.
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
    Load persistent machine memory.

    Production reads Firestore.

    CI reads the isolated in-memory store.
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

    Production writes Firestore.

    CI writes only to the isolated in-memory store.
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

    Production writes to:

        devices/{deviceId}/missions/{missionId}

    CI writes to the isolated in-memory mission store.

    Machine memory answers:
        "What has this machine done?"

    Mission evidence answers:
        "What exactly happened during this mission,
         and how was the work validated?"
    """

    mission_id = mission[
        "missionId"
    ]

    fingerprint_data = mission.get(
        "evidenceFingerprint",
        {},
    )

    fingerprint = fingerprint_data.get(
        "value"
    )

    konnex_payload = mission.get(
        "konnexAdapter"
    )

    if konnex_payload is None:

        konnex_payload = (
            konnex_adapter.build_submission_payload(
                mission,
                fingerprint=fingerprint,
            )
        )

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

        "evidenceFingerprint": (
            mission.get(
                "evidenceFingerprint"
            )
        ),

        "konnexAdapter": (
            konnex_payload
        ),

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
    Add evidence-artifact metadata to an already persisted
    mission evidence record.

    The complete Konnex adapter remains untouched.
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
                    EVIDENCE_FINGERPRINT_SCOPE
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

        # Existing production Firestore reputation remains
        # the source of truth.
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

        # ----------------------------------------------------
        # STEP 1 — Generate evidence
        # ----------------------------------------------------

        mission[
            "evidence"
        ] = self.generate_evidence(
            mission
        )

        # ----------------------------------------------------
        # STEP 2 — Validate mission
        # ----------------------------------------------------

        mission[
            "validatorResult"
        ] = self.validate_mission(
            mission
        )

        # ----------------------------------------------------
        # STEP 3 — Calculate PoPW-style score
        # ----------------------------------------------------

        mission[
            "powpScore"
        ] = self.calculate_powp_score(
            mission[
                "validatorResult"
            ]
        )

        # ----------------------------------------------------
        # STEP 4 — Build canonical evidence core
        # ----------------------------------------------------

        fingerprint_package = (
            build_fingerprint_package(
                mission
            )
        )

        # ----------------------------------------------------
        # STEP 5 — Generate ONE canonical fingerprint
        # ----------------------------------------------------

        evidence_fingerprint = (
            calculate_evidence_fingerprint(
                fingerprint_package
            )
        )

        mission[
            "evidenceFingerprint"
        ] = {

            "algorithm": "SHA-256",

            "value": evidence_fingerprint,

            "scope": (
                EVIDENCE_FINGERPRINT_SCOPE
            ),

            "konnexVerified": False,

            "onChainVerified": False,
        }

        # ----------------------------------------------------
        # STEP 6 — Build Konnex adapter using the same
        #          canonical fingerprint
        # ----------------------------------------------------

        mission[
            "konnexAdapter"
        ] = (
            konnex_adapter.build_submission_payload(
                mission,
                fingerprint=evidence_fingerprint,
            )
        )

        # ----------------------------------------------------
        # STEP 7 — Return machine to IDLE
        # ----------------------------------------------------

        verified = mission[
            "validatorResult"
        ]["verified"]

        self.robot.status = "IDLE"

        # ----------------------------------------------------
        # STEP 8 — Update machine reputation
        # ----------------------------------------------------

        self.robot.update_reputation(
            verified
        )

        # ----------------------------------------------------
        # STEP 9 — Persist compact machine memory
        # ----------------------------------------------------

        self.robot.remember(
            mission
        )

        # ----------------------------------------------------
        # STEP 10 — Persist complete mission evidence
        # ----------------------------------------------------

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

        # Expose the canonical fingerprint at the top
        # level for convenient API/frontend consumption.
        "evidenceFingerprint": (
            mission.get(
                "evidenceFingerprint"
            )
        ),

        # Expose the same Konnex-ready adapter package.
        "konnexAdapter": (
            mission.get(
                "konnexAdapter"
            )
        ),
    }

    return result


# ============================================================
# EXPORT EVIDENCE
# ============================================================

def export_evidence(
    result: dict[str, Any],
) -> tuple[Path, str]:
    """
    Export the already-canonical mission evidence package.

    This function does NOT create a second fingerprint.

    The canonical fingerprint was created during mission
    execution before the Konnex adapter was built.

    Therefore:

        mission fingerprint
        =
        Firebase/CI fingerprint
        =
        Konnex adapter fingerprint
        =
        exported evidence fingerprint
    """

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    evidence_fingerprint = (
        result.get(
            "evidenceFingerprint"
        )
    )

    fingerprint = None

    if isinstance(
        evidence_fingerprint,
        dict,
    ):

        fingerprint = (
            evidence_fingerprint.get(
                "value"
            )
        )

    if not fingerprint:

        mission = result.get(
            "mission",
            {},
        )

        mission_fingerprint = (
            mission.get(
                "evidenceFingerprint",
                {},
            )
        )

        if isinstance(
            mission_fingerprint,
            dict,
        ):

            fingerprint = (
                mission_fingerprint.get(
                    "value"
                )
            )

    if not fingerprint:

        raise ValueError(
            "Canonical evidence fingerprint is missing. "
            "The mission must be executed through the "
            "current evidence pipeline before export."
        )

    result[
        "evidenceFingerprint"
    ] = {

        "algorithm": "SHA-256",

        "value": fingerprint,

        "scope": (
            EVIDENCE_FINGERPRINT_SCOPE
        ),

        "konnexVerified": False,

        "onChainVerified": False,
    }

    mission = result.get(
        "mission",
        {},
    )

    mission[
        "evidenceFingerprint"
    ] = result[
        "evidenceFingerprint"
    ]

    if mission.get(
        "konnexAdapter"
    ):

        result[
            "konnexAdapter"
        ] = mission[
            "konnexAdapter"
        ]

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

    if CI_TEST_MODE:
        print(
            "  Persistence: "
            "GitHub Actions isolated CI memory"
        )
    else:
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

    print("KONNEX ADAPTER")

    print(
        f"  Version: "
        f"{KONNEX_ADAPTER_VERSION}"
    )

    print(
        f"  Status: "
        f"{KONNEX_ADAPTER_STATUS}"
    )

    print(
        "  Fingerprint attached: True"
    )

    print(
        "  Submitted: False"
    )

    print(
        "  Konnex verified: False"
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
