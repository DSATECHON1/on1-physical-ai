from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import os
import urllib.error
import urllib.request

from firebase_admin import firestore

from main import (
PROJECT_NAME,
PROTOTYPE_VERSION,
robot,
engine,
export_evidence,
device_ref,
FIRESTORE_MISSION_COLLECTION,
)

HOST = os.getenv("ON1_API_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

============================================================

RESPONSE HELPERS

============================================================

def send_json(handler, status_code, payload):
body = json.dumps(
payload,
indent=2,
default=str,
).encode("utf-8")

handler.send_response(status_code)

handler.send_header(
    "Content-Type",
    "application/json; charset=utf-8",
)

handler.send_header(
    "Content-Length",
    str(len(body)),
)

handler.send_header(
    "Access-Control-Allow-Origin",
    "*",
)

handler.send_header(
    "Access-Control-Allow-Methods",
    "GET, POST, OPTIONS",
)

handler.send_header(
    "Access-Control-Allow-Headers",
    "Content-Type",
)

handler.send_header(
    "Cache-Control",
    "no-store",
)

handler.end_headers()

handler.wfile.write(body)

def read_json_body(handler):
content_length = int(
handler.headers.get(
"Content-Length",
"0",
)
)

if content_length <= 0:
    return {}

raw_body = handler.rfile.read(
    content_length
)

if not raw_body:
    return {}

try:
    parsed = json.loads(
        raw_body.decode("utf-8")
    )

except (
    json.JSONDecodeError,
    UnicodeDecodeError,
):
    raise ValueError(
        "Request body must contain valid JSON."
    )

if not isinstance(parsed, dict):
    raise ValueError(
        "Request body must be a JSON object."
    )

return parsed

============================================================

FIRESTORE — LATEST MISSION

============================================================

def load_latest_mission():
"""
Read the most recently completed mission evidence
persisted in Firestore.

This function is READ-ONLY.
"""

mission_collection = device_ref.collection(
    FIRESTORE_MISSION_COLLECTION
)

snapshots = (
    mission_collection
    .order_by(
        "completedAt",
        direction=firestore.Query.DESCENDING,
    )
    .limit(1)
    .stream()
)

for snapshot in snapshots:

    mission = snapshot.to_dict()

    if mission:
        return mission

return None

============================================================

DATA NORMALIZATION

============================================================

def get_canonical_fingerprint(
mission,
):
"""
Read the canonical fingerprint using the schema produced
by backend/main.py.

Production schema:

    evidenceFingerprint.value

The fallback to .fingerprint keeps the API compatible with
any older persisted record that may have used that field.
"""

fingerprint_data = mission.get(
    "evidenceFingerprint",
    {},
)

if not isinstance(
    fingerprint_data,
    dict,
):
    return None

value = fingerprint_data.get(
    "value"
)

if value:
    return value

legacy_value = fingerprint_data.get(
    "fingerprint"
)

if legacy_value:
    return legacy_value

return None

def get_konnex_adapter_name(
konnex_adapter,
):
"""
Read the Konnex adapter name from the production schema.
"""

adapter_metadata = konnex_adapter.get(
    "adapter",
    {},
)

if not isinstance(
    adapter_metadata,
    dict,
):
    return None

return adapter_metadata.get(
    "name"
)

def get_konnex_adapter_version(
konnex_adapter,
):
"""
Read the Konnex adapter version from the production schema.
"""

adapter_metadata = konnex_adapter.get(
    "adapter",
    {},
)

if not isinstance(
    adapter_metadata,
    dict,
):
    return None

return adapter_metadata.get(
    "version"
)

def get_konnex_adapter_status(
konnex_adapter,
):
"""
Read the Konnex adapter readiness status from the
production schema.

Production schema:

    konnexAdapter.adapter.status

Legacy fallback:

    konnexAdapter.status
"""

adapter_metadata = konnex_adapter.get(
    "adapter",
    {},
)

if isinstance(
    adapter_metadata,
    dict,
):

    status = adapter_metadata.get(
        "status"
    )

    if status:
        return status

return konnex_adapter.get(
    "status"
)

def get_konnex_submission_flag(
konnex_adapter,
):
"""
Read submittedToKonnex from the production Konnex
adapter schema.

Production schema:

    konnexAdapter.submission.submittedToKonnex

Legacy fallback:

    konnexAdapter.submittedToKonnex
"""

submission = konnex_adapter.get(
    "submission",
    {},
)

if isinstance(
    submission,
    dict,
):

    value = submission.get(
        "submittedToKonnex"
    )

    if value is not None:
        return value

return konnex_adapter.get(
    "submittedToKonnex",
    False,
)

def get_konnex_verified_flag(
konnex_adapter,
):
"""
Read Konnex verification state.
"""

submission = konnex_adapter.get(
    "submission",
    {},
)

if isinstance(
    submission,
    dict,
):

    value = submission.get(
        "konnexVerified"
    )

    if value is not None:
        return value

return konnex_adapter.get(
    "konnexVerified",
    False,
)

def get_on_chain_verified_flag(
konnex_adapter,
):
"""
Read on-chain verification state.
"""

submission = konnex_adapter.get(
    "submission",
    {},
)

if isinstance(
    submission,
    dict,
):

    value = submission.get(
        "onChainVerified"
    )

    if value is not None:
        return value

return konnex_adapter.get(
    "onChainVerified",
    False,
)

============================================================

BUILD RESTORED MISSION RESULT

============================================================

def build_latest_mission_result(mission):
"""
Convert the persisted Firestore mission evidence record
into the result structure consumed by the frontend.

This does not execute or mutate anything.
"""

if not mission:
    return None

fingerprint = mission.get(
    "evidenceFingerprint",
    {},
)

konnex_adapter = mission.get(
    "konnexAdapter",
    {},
)

evidence_artifact = mission.get(
    "evidenceArtifact",
    {},
)

return {
    "project": PROJECT_NAME,

    "prototypeVersion": PROTOTYPE_VERSION,

    "simulation": {
        "browser": False,
        "backend": True,
        "restored": True,
    },

    "integration": {
        "physicalHardware": False,
        "konnex": False,
        "onChain": False,
    },

    "generatedAt": mission.get(
        "persistedAt"
    ),

    "robot": robot.to_dict(),

    "mission": mission,

    "evidenceFingerprint": fingerprint,

    "konnexAdapter": konnex_adapter,

    "evidenceArtifact": evidence_artifact,
}

============================================================

KONNEX SUBMISSION READINESS

============================================================

def build_konnex_submission_package(mission):
"""
Build a READ-ONLY Konnex submission package from the
latest persisted and verified mission.

This function does NOT:
- submit anything to Konnex
- contact a Konnex API
- modify Firebase
- modify the mission
- change Konnex verification status
- change on-chain status
- change physical hardware status
"""

if not mission:

    return {
        "ready": False,
        "reason": (
            "No persisted mission evidence was found."
        ),
    }

mission_status = mission.get(
    "status"
)

validator = mission.get(
    "validatorResult",
    {},
)

fingerprint_data = mission.get(
    "evidenceFingerprint",
    {},
)

konnex_adapter = mission.get(
    "konnexAdapter",
    {},
)

evidence_artifact = mission.get(
    "evidenceArtifact",
    {},
)

canonical_fingerprint = (
    get_canonical_fingerprint(
        mission
    )
)

adapter_status = (
    get_konnex_adapter_status(
        konnex_adapter
    )
)

submitted_to_konnex = (
    get_konnex_submission_flag(
        konnex_adapter
    )
)

konnex_verified = (
    get_konnex_verified_flag(
        konnex_adapter
    )
)

on_chain_verified = (
    get_on_chain_verified_flag(
        konnex_adapter
    )
)

checks = {}

checks["missionExists"] = True

checks["missionCompleted"] = (
    mission_status == "COMPLETED"
)

checks["missionVerified"] = (
    validator.get(
        "verified"
    ) is True
)

checks["validationComplete"] = (
    validator.get(
        "passedChecks"
    ) == 6
    and
    validator.get(
        "totalChecks"
    ) == 6
)

checks["powpScorePresent"] = (
    mission.get(
        "powpScore"
    ) is not None
)

checks["evidenceFingerprintPresent"] = (
    bool(
        fingerprint_data
    )
    and
    bool(
        canonical_fingerprint
    )
)

checks["canonicalFingerprintPresent"] = (
    bool(
        canonical_fingerprint
    )
)

checks["konnexAdapterPresent"] = (
    bool(
        konnex_adapter
    )
)

checks["konnexAdapterReady"] = (
    adapter_status
    == "READY_FOR_KONNEX_REVIEW"
)

checks["notSubmittedToKonnex"] = (
    submitted_to_konnex
    is False
)

checks["notKonnexVerified"] = (
    konnex_verified
    is False
)

checks["notOnChainVerified"] = (
    on_chain_verified
    is False
)

checks["physicalHardwareNotClaimed"] = (
    konnex_adapter.get(
        "integration",
        {},
    ).get(
        "physicalHardware",
        False,
    )
    is False
)

checks["evidenceArtifactPresent"] = (
    bool(
        evidence_artifact
    )
)

artifact_sha256 = (
    evidence_artifact.get(
        "sha256"
    )
)

checks[
    "evidenceArtifactFingerprintMatches"
] = (
    bool(
        artifact_sha256
    )
    and
    bool(
        canonical_fingerprint
    )
    and
    artifact_sha256
    == canonical_fingerprint
)

ready = all(
    checks.values()
)

failed_checks = [
    name
    for name, passed
    in checks.items()
    if not passed
]

return {
    "ready": ready,

    "status": (
        "READY_FOR_KONNEX_SUBMISSION"
        if ready
        else
        "NOT_READY_FOR_KONNEX_SUBMISSION"
    ),

    "submission": {
        "submitted": False,

        "submittedToKonnex": (
            submitted_to_konnex
        ),

        "konnexVerified": (
            konnex_verified
        ),

        "onChainVerified": (
            on_chain_verified
        ),

        "physicalHardware": (
            konnex_adapter.get(
                "integration",
                {},
            ).get(
                "physicalHardware",
                False,
            )
        ),
    },

    "project": PROJECT_NAME,

    "prototypeVersion": PROTOTYPE_VERSION,

    "adapter": {
        "schema": konnex_adapter.get(
            "schema"
        ),

        "name": (
            get_konnex_adapter_name(
                konnex_adapter
            )
        ),

        "version": (
            get_konnex_adapter_version(
                konnex_adapter
            )
        ),

        "status": adapter_status,
    },

    "mission": {
        "missionId": mission.get(
            "missionId"
        ),

        "robotId": mission.get(
            "robotId"
        ),

        "taskType": mission.get(
            "taskType"
        ),

        "status": mission_status,

        "powpScore": mission.get(
            "powpScore"
        ),
    },

    "evidence": {
        "evidenceId": (
            mission.get(
                "evidence",
                {},
            ).get(
                "evidenceId"
            )
        ),

        "fingerprint": (
            canonical_fingerprint
        ),

        "algorithm": (
            fingerprint_data.get(
                "algorithm",
                "SHA-256",
            )
        ),

        "artifactSha256": (
            artifact_sha256
        ),
    },

    "validation": {
        "verified": validator.get(
            "verified"
        ),

        "passedChecks": validator.get(
            "passedChecks"
        ),

        "totalChecks": validator.get(
            "totalChecks"
        ),
    },

    "checks": checks,

    "failedChecks": failed_checks,

    "source": {
        "type": "firebase",

        "readOnly": True,

        "firebaseMutation": False,
    },

    "integration": {
        "physicalHardware": False,

        "konnex": False,

        "onChain": False,
    },

    "note": (
        "This is a local ON1 submission-readiness package. "
        "It does not submit data to Konnex and does not "
        "represent a live Konnex or on-chain transaction."
    ),
}

============================================================

API HANDLER

============================================================

class ON1APIHandler(BaseHTTPRequestHandler):

server_version = "ON1PhysicalAI/0.5.3"

def log_message(
    self,
    format_string,
    *args,
):
    print(
        "[ON1 API] "
        + format_string % args,
        flush=True,
    )

# --------------------------------------------------------
# OPTIONS
# --------------------------------------------------------

def do_OPTIONS(self):

    self.send_response(204)

    self.send_header(
        "Access-Control-Allow-Origin",
        "*",
    )

    self.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, OPTIONS",
    )

    self.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type",
    )

    self.send_header(
        "Access-Control-Max-Age",
        "86400",
    )

    self.end_headers()

# --------------------------------------------------------
# GET
# --------------------------------------------------------

def do_GET(self):

    path = self.path.split(
        "?",
        1,
    )[0]

    try:

        if path == "/":
            handle_root(self)

        elif path == "/health":
            handle_health(self)

        elif path == "/robot":
            handle_robot(self)

        elif path == "/missions/latest":
            handle_latest_mission(self)

        elif path == "/konnex/submission/latest":
            handle_konnex_submission_latest(self)

        else:

            send_json(
                self,
                404,
                {
                    "error": (
                        "Endpoint not found."
                    ),

                    "path": path,

                    "availableEndpoints": [
                        "GET /",
                        "GET /health",
                        "GET /robot",
                        "GET /missions/latest",
                        "GET /konnex/submission/latest",
                        "POST /missions",
                    ],
                },
            )

    except Exception as exc:

        print(
            f"[ON1 API] GET {path} error: {exc}",
            flush=True,
        )

        send_json(
            self,
            500,
            {
                "error": (
                    "Internal server error."
                ),

                "message": str(exc),
            },
        )

# --------------------------------------------------------
# POST
# --------------------------------------------------------

def do_POST(self):

    path = self.path.split(
        "?",
        1,
    )[0]

    try:

        if path == "/missions":

            handle_create_mission(
                self
            )

        else:

            send_json(
                self,
                404,
                {
                    "error": (
                        "Endpoint not found."
                    ),

                    "path": path,

                    "availableEndpoints": [
                        "GET /",
                        "GET /health",
                        "GET /robot",
                        "GET /missions/latest",
                        "GET /konnex/submission/latest",
                        "POST /missions",
                    ],
                },
            )

    except ValueError as exc:

        print(
            f"[ON1 API] POST {path} validation error: {exc}",
            flush=True,
        )

        send_json(
            self,
            400,
            {
                "error": str(exc),
            },
        )

    except Exception as exc:

        print(
            f"[ON1 API] POST {path} error: {exc}",
            flush=True,
        )

        send_json(
            self,
            500,
            {
                "error": (
                    "Internal server error."
                ),

                "message": str(exc),
            },
        )

============================================================

GET /

============================================================

def handle_root(handler):

send_json(
    handler,
    200,
    {
        "project": PROJECT_NAME,

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "service": (
            "ON1 Physical AI API"
        ),

        "status": "online",

        "apiVersion": "0.4",

        "endpoints": {
            "health": "GET /health",

            "robot": "GET /robot",

            "latestMission": (
                "GET /missions/latest"
            ),

            "konnexSubmissionReadiness": (
                "GET /konnex/submission/latest"
            ),

            "missions": "POST /missions",
        },

        "integration": {
            "physicalHardware": False,

            "konnex": False,

            "onChain": False,
        },

        "simulation": {
            "browser": False,

            "backend": True,
        },
    },
)

============================================================

GET /health

============================================================

def handle_health(handler):

send_json(
    handler,
    200,
    {
        "status": "online",

        "project": PROJECT_NAME,

        "prototypeVersion": (
            PROTOTYPE_VERSION
        ),

        "integration": {
            "physicalHardware": False,

            "konnex": False,

            "onChain": False,
        },
    },
)

============================================================

GET /robot

============================================================

def handle_robot(handler):

send_json(
    handler,
    200,
    {
        "robot": robot.to_dict(),

        "integration": {
            "physicalHardware": False,

            "konnex": False,

            "onChain": False,
        },
    },
)

============================================================

GET /missions/latest

============================================================

def handle_latest_mission(handler):

mission = load_latest_mission()

if mission is None:

    send_json(
        handler,
        404,
        {
            "found": False,

            "message": (
                "No persisted mission evidence "
                "was found."
            ),
        },
    )

    return

result = build_latest_mission_result(
    mission
)

send_json(
    handler,
    200,
    {
        "found": True,

        **result,
    },
)

============================================================

GET /konnex/submission/latest

============================================================

def handle_konnex_submission_latest(handler):

"""
Read-only endpoint exposing the current ON1 Konnex
submission-readiness package.

No Firebase mutation occurs.
No Konnex submission occurs.
"""

mission = load_latest_mission()

if mission is None:

    send_json(
        handler,
        404,
        {
            "found": False,

            "ready": False,

            "status": (
                "NOT_READY_FOR_KONNEX_SUBMISSION"
            ),

            "message": (
                "No persisted mission evidence "
                "was found."
            ),

            "submission": {
                "submitted": False,

                "submittedToKonnex": False,

                "konnexVerified": False,

                "onChainVerified": False,

                "physicalHardware": False,
            },
        },
    )

    return

package = build_konnex_submission_package(
    mission
)

send_json(
    handler,
    200,
    {
        "found": True,

        **package,
    },
)

============================================================

POST /missions

============================================================

def handle_create_mission(handler):

payload = read_json_body(
    handler
)

start = payload.get(
    "start",
    [0, 0],
)

target = payload.get(
    "target",
    [10, 10],
)

if (
    not isinstance(
        start,
        (list, tuple),
    )
    or len(start) != 2
):

    raise ValueError(
        "start must be an array containing exactly two coordinates."
    )

if (
    not isinstance(
        target,
        (list, tuple),
    )
    or len(target) != 2
):

    raise ValueError(
        "target must be an array containing exactly two coordinates."
    )

try:

    start_x = int(
        start[0]
    )

    start_y = int(
        start[1]
    )

    target_x = int(
        target[0]
    )

    target_y = int(
        target[1]
    )

except (
    TypeError,
    ValueError,
):

    raise ValueError(
        "start and target coordinates must be integers."
    )

mission = engine.execute_navigation(
    start=(
        start_x,
        start_y,
    ),

    target=(
        target_x,
        target_y,
    ),
)

result = {

    "project": PROJECT_NAME,

    "prototypeVersion": (
        PROTOTYPE_VERSION
    ),

    "simulation": {
        "browser": False,

        "backend": True,
    },

    "integration": {
        "physicalHardware": False,

        "konnex": False,

        "onChain": False,
    },

    "robot": robot.to_dict(),

    "mission": mission,
}

output_path, fingerprint = (
    export_evidence(
        result
    )
)

result[
    "evidenceFingerprint"
] = mission.get(
    "evidenceFingerprint"
)

result[
    "konnexAdapter"
] = mission.get(
    "konnexAdapter"
)

result[
    "evidenceArtifact"
] = {

    "path": str(
        output_path
    ),

    "sha256": fingerprint,

    "algorithm": "SHA-256",

    "konnexVerified": False,

    "onChainVerified": False,
}

send_json(
    handler,
    200,
    result,
)

============================================================

SERVER

============================================================

def run_server():

server = ThreadingHTTPServer(
    (
        HOST,
        PORT,
    ),
    ON1APIHandler,
)

print(
    "============================================================",
    flush=True,
)

print(
    "ON1 Physical AI API",
    flush=True,
)

print(
    f"Project: {PROJECT_NAME}",
    flush=True,
)

print(
    f"Prototype Version: {PROTOTYPE_VERSION}",
    flush=True,
)

print(
    f"Listening on {HOST}:{PORT}",
    flush=True,
)

print(
    "Endpoints:",
    flush=True,
)

print(
    "  GET  /",
    flush=True,
)

print(
    "  GET  /health",
    flush=True,
)

print(
    "  GET  /robot",
    flush=True,
)

print(
    "  GET  /missions/latest",
    flush=True,
)

print(
    "  GET  /konnex/submission/latest",
    flush=True,
)

print(
    "  POST /missions",
    flush=True,
)

print(
    "============================================================",
    flush=True,
)

try:

    server.serve_forever()

except KeyboardInterrupt:

    print(
        "\n[ON1 API] Shutdown requested.",
        flush=True,
    )

finally:

    server.server_close()

    print(
        "[ON1 API] Server stopped.",
        flush=True,
    )

============================================================

NON-DESTRUCTIVE SELF-TEST DOUBLES

============================================================

class SelfTestRobot:

def to_dict(self):

    return {

        "robotId": "ON1-SELF-TEST",

        "identity": (
            "ON1-SELF-TEST-MACHINE"
        ),

        "model": (
            "ON1 Self-Test Navigator"
        ),

        "status": "IDLE",

        "missionCount": 0,

        "successfulMissions": 0,

        "failedMissions": 0,

        "reputation": 100,

        "memoryCount": 0,
    }

class SelfTestEngine:

def execute_navigation(
    self,
    start,
    target,
):

    return {

        "missionId": (
            "MSN-SELF-TEST-001"
        ),

        "robotId": (
            "ON1-SELF-TEST"
        ),

        "taskType": "Navigation",

        "start": {
            "x": start[0],
            "y": start[1],
        },

        "target": {
            "x": target[0],
            "y": target[1],
        },

        "startedAt": (
            "2026-01-01T00:00:00+00:00"
        ),

        "completedAt": (
            "2026-01-01T00:00:01+00:00"
        ),

        "telemetry": [

            {
                "step": 0,

                "position": {
                    "x": start[0],
                    "y": start[1],
                },

                "battery": 100,
            },

            {
                "step": 10,

                "position": {
                    "x": target[0],
                    "y": target[1],
                },

                "battery": 90,
            },
        ],

        "status": "COMPLETED",

        "evidence": {

            "evidenceId": (
                "EVD-SELF-TEST-001"
            ),

            "missionId": (
                "MSN-SELF-TEST-001"
            ),

            "robotId": (
                "ON1-SELF-TEST"
            ),

            "taskType": "Navigation",

            "status": "COMPLETED",
        },

        "validatorResult": {

            "validatorId": (
                "ON1-SELF-TEST-VALIDATOR"
            ),

            "validatedAt": (
                "2026-01-01T00:00:01+00:00"
            ),

            "checks": {

                "missionStarted": True,

                "missionCompleted": True,

                "telemetryPresent": True,

                "targetReached": True,

                "robotIdentityPresent": True,

                "evidenceGenerated": True,
            },

            "passedChecks": 6,

            "totalChecks": 6,

            "verified": True,
        },

        "powpScore": 100,

        "evidenceFingerprint": {

            "fingerprint": (
                "self-test-canonical-fingerprint"
            ),

            "value": (
                "self-test-canonical-fingerprint"
            ),

            "algorithm": "SHA-256",

        },

        "konnexAdapter": {

            "schema": (
                "on1.physical-ai.konnex-mission.v1"
            ),

            "adapter": {

                "name": (
                    "ON1 Konnex Adapter"
                ),

                "version": "0.1.0",

                "status": (
                    "READY_FOR_KONNEX_REVIEW"
                ),
            },

            "submission": {

                "submittedToKonnex": False,

                "konnexVerified": False,

                "onChainVerified": False,
            },

            "integration": {

                "physicalHardware": False,

                "konnexVerified": False,

                "onChainVerified": False,
            },
        },

        "evidenceArtifact": {

            "sha256": (
                "self-test-canonical-fingerprint"
            ),

            "algorithm": "SHA-256",

        },
    }

def self_test_export_evidence(
result,
):

return (
    Path(
        "SELF_TEST_ONLY/"
        "mission-result.json"
    ),

    "self-test-canonical-fingerprint",
)

============================================================

SELF-TEST HTTP CLIENT

============================================================

def api_request(
base_url,
method="GET",
path="/",
payload=None,
):

url = (
    f"{base_url}{path}"
)

data = None

if payload is not None:

    data = json.dumps(
        payload
    ).encode(
        "utf-8"
    )

request = urllib.request.Request(
    url=url,

    data=data,

    method=method,

    headers={
        "Content-Type":
            "application/json",
    },
)

try:

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:

        raw = (
            response
            .read()
            .decode(
                "utf-8"
            )
        )

        parsed = (
            json.loads(raw)
            if raw
            else {}
        )

        return (
            response.status,
            parsed,
        )

except urllib.error.HTTPError as exc:

    raw = (
        exc
        .read()
        .decode(
            "utf-8"
        )
    )

    try:

        parsed = json.loads(
            raw
        )

    except json.JSONDecodeError:

        parsed = {
            "error": raw,
        }

    return (
        exc.code,
        parsed,
    )

============================================================

SELF-TEST ASSERTION

============================================================

def assert_condition(
condition,
message,
):

if not condition:

    raise RuntimeError(
        f"SELF-TEST FAILED: {message}"
    )

============================================================

NON-DESTRUCTIVE API SELF-TEST

============================================================

def run_self_test():

global robot
global engine
global export_evidence
global load_latest_mission

original_robot = robot

original_engine = engine

original_export_evidence = (
    export_evidence
)

original_load_latest_mission = (
    load_latest_mission
)

test_server = None

try:

    robot = SelfTestRobot()

    engine = SelfTestEngine()

    export_evidence = (
        self_test_export_evidence
    )

    test_server = ThreadingHTTPServer(
        (
            "127.0.0.1",
            0,
        ),
        ON1APIHandler,
    )

    test_port = (
        test_server
        .server_address[1]
    )

    server_thread = Thread(
        target=(
            test_server
            .serve_forever
        ),
        daemon=True,
    )

    server_thread.start()

    base_url = (
        f"http://127.0.0.1:{test_port}"
    )

    # ----------------------------------------------------
    # GET /
    # ----------------------------------------------------

    status, data = api_request(
        base_url,
        "GET",
        "/",
    )

    assert_condition(
        status == 200,
        "GET / must return HTTP 200.",
    )

    assert_condition(
        data.get(
            "status"
        ) == "online",
        "GET / must report online status.",
    )

    assert_condition(
        data.get(
            "project"
        ) == PROJECT_NAME,
        "GET / must report the correct project.",
    )

    assert_condition(
        data.get(
            "apiVersion"
        ) == "0.4",
        "GET / must report API version 0.4.",
    )

    # ----------------------------------------------------
    # GET /health
    # ----------------------------------------------------

    status, data = api_request(
        base_url,
        "GET",
        "/health",
    )

    assert_condition(
        status == 200,
        "GET /health must return HTTP 200.",
    )

    assert_condition(
        data.get(
            "status"
        ) == "online",
        "GET /health must report online status.",
    )

    # ----------------------------------------------------
    # GET /robot
    # ----------------------------------------------------

    status, data = api_request(
        base_url,
        "GET",
        "/robot",
    )

    assert_condition(
        status == 200,
        "GET /robot must return HTTP 200.",
    )

    assert_condition(
        "robot" in data,
        "GET /robot must return a robot object.",
    )

    assert_condition(
        data["robot"].get(
            "robotId"
        ) == "ON1-SELF-TEST",
        "GET /robot must return the isolated self-test robot.",
    )

    # ----------------------------------------------------
    # POST /missions
    # ----------------------------------------------------

    status, data = api_request(
        base_url,
        "POST",
        "/missions",
        {
            "start": [
                0,
                0,
            ],

            "target": [
                10,
                10,
            ],
        },
    )

    assert_condition(
        status == 200,
        "POST /missions must return HTTP 200.",
    )

    mission = data.get(
        "mission",
        {},
    )

    assert_condition(
        mission.get(
            "status"
        ) == "COMPLETED",
        "Self-test mission must be COMPLETED.",
    )

    validator = mission.get(
        "validatorResult",
        {},
    )

    assert_condition(
        validator.get(
            "verified"
        ) is True,
        "Mission validator must report verified=True.",
    )

    assert_condition(
        validator.get(
            "passedChecks"
        ) == 6,
        "Validator must pass all 6 checks.",
    )

    assert_condition(
        validator.get(
            "totalChecks"
        ) == 6,
        "Validator must contain 6 total checks.",
    )

    assert_condition(
        mission.get(
            "powpScore"
        ) == 100,
        "PoPW-style score must be 100.",
    )

    evidence_artifact = data.get(
        "evidenceArtifact",
        {},
    )

    assert_condition(
        evidence_artifact.get(
            "sha256"
        )
        == "self-test-canonical-fingerprint",
        "Evidence artifact fingerprint must be returned.",
    )

    # ----------------------------------------------------
    # Prepare isolated latest mission.
    # ----------------------------------------------------

    self_test_latest_mission = dict(
        mission
    )

    self_test_latest_mission[
        "persistedAt"
    ] = (
        "2026-01-01T00:00:02+00:00"
    )

    self_test_latest_mission[
        "evidenceFingerprint"
    ] = {

        "fingerprint": (
            "self-test-canonical-fingerprint"
        ),

        "value": (
            "self-test-canonical-fingerprint"
        ),

        "algorithm": "SHA-256",
    }

    self_test_latest_mission[
        "konnexAdapter"
    ] = {

        "schema": (
            "on1.physical-ai.konnex-mission.v1"
        ),

        "adapter": {

            "name": (
                "ON1 Konnex Adapter"
            ),

            "version": "0.1.0",

            "status": (
                "READY_FOR_KONNEX_REVIEW"
            ),
        },

        "submission": {

            "submittedToKonnex": False,

            "konnexVerified": False,

            "onChainVerified": False,
        },

        "integration": {

            "physicalHardware": False,

            "konnexVerified": False,

            "onChainVerified": False,
        },
    }

    self_test_latest_mission[
        "evidenceArtifact"
    ] = {

        "sha256": (
            "self-test-canonical-fingerprint"
        ),

        "algorithm": "SHA-256",
    }

    def self_test_load_latest_mission():

        return self_test_latest_mission

    load_latest_mission = (
        self_test_load_latest_mission
    )

    # ----------------------------------------------------
    # GET /konnex/submission/latest
    # ----------------------------------------------------

    status, data = api_request(
        base_url,
        "GET",
        "/konnex/submission/latest",
    )

    assert_condition(
        status == 200,
        "GET /konnex/submission/latest must return HTTP 200.",
    )

    assert_condition(
        data.get(
            "found"
        ) is True,
        "Konnex readiness endpoint must find the test mission.",
    )

    assert_condition(
        data.get(
            "ready"
        ) is True,
        "Konnex readiness package must report ready=True.",
    )

    assert_condition(
        data.get(
            "status"
        )
        == "READY_FOR_KONNEX_SUBMISSION",
        "Konnex readiness status must report READY_FOR_KONNEX_SUBMISSION.",
    )

    assert_condition(
        data.get(
            "adapter",
            {},
        ).get(
            "name"
        )
        == "ON1 Konnex Adapter",
        "Konnex adapter name must be exposed.",
    )

    assert_condition(
        data.get(
            "adapter",
            {},
        ).get(
            "version"
        )
        == "0.1.0",
        "Konnex adapter version must be exposed.",
    )

    assert_condition(
        data.get(
            "adapter",
            {},
        ).get(
            "status"
        )
        == "READY_FOR_KONNEX_REVIEW",
        "Konnex adapter must be READY_FOR_KONNEX_REVIEW.",
    )

    assert_condition(
        data.get(
            "evidence",
            {},
        ).get(
            "fingerprint"
        )
        == "self-test-canonical-fingerprint",
        "Konnex package must expose the canonical evidence fingerprint.",
    )

    assert_condition(
        data.get(
            "evidence",
            {},
        ).get(
            "artifactSha256"
        )
        == data.get(
            "evidence",
            {},
        ).get(
            "fingerprint"
        ),
        "Evidence artifact SHA-256 must match the canonical fingerprint.",
    )

    assert_condition(
        data.get(
            "validation",
            {},
        ).get(
            "verified"
        ) is True,
        "Konnex package must require verified=True.",
    )

    assert_condition(
        data.get(
            "validation",
            {},
        ).get(
            "passedChecks"
        ) == 6,
        "Konnex package must require all 6 validation checks.",
    )

    assert_condition(
        data.get(
            "validation",
            {},
        ).get(
            "totalChecks"
        ) == 6,
        "Konnex package must require 6 total validation checks.",
    )

    assert_condition(
        data.get(
            "failedChecks"
        ) == [],
        "Konnex package must contain no failed readiness checks.",
    )

    assert_condition(
        data.get(
            "source",
            {},
        ).get(
            "readOnly"
        ) is True,
        "Konnex readiness endpoint must be read-only.",
    )

    assert_condition(
        data.get(
            "source",
            {},
        ).get(
            "firebaseMutation"
        ) is False,
        "Konnex readiness endpoint must not mutate Firebase.",
    )

    print(
        "",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "ON1 PHYSICAL AI API SELF-TEST PASSED",
        flush=True,
    )

    print(
        "GET /                         PASS",
        flush=True,
    )

    print(
        "GET /health                   PASS",
        flush=True,
    )

    print(
        "GET /robot                    PASS",
        flush=True,
    )

    print(
        "POST /missions                PASS",
        flush=True,
    )

    print(
        "GET /konnex/submission/latest PASS",
        flush=True,
    )

    print(
        "Validation 6/6                PASS",
        flush=True,
    )

    print(
        "PoPW Score 100                PASS",
        flush=True,
    )

    print(
        "Canonical fingerprint         PASS",
        flush=True,
    )

    print(
        "Konnex readiness              PASS",
        flush=True,
    )

    print(
        "Konnex submission             NONE",
        flush=True,
    )

    print(
        "Firebase mutation             NONE",
        flush=True,
    )

    print(
        "Production mission            NONE",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

finally:

    robot = original_robot

    engine = original_engine

    export_evidence = (
        original_export_evidence
    )

    load_latest_mission = (
        original_load_latest_mission
    )

    if test_server is not None:

        test_server.shutdown()

        test_server.server_close()

============================================================

ENTRY POINT

============================================================

if name == "main":

if os.getenv(
    "ON1_API_TEST",
    "0",
) == "1":

    run_self_test()

else:

    run_server()
