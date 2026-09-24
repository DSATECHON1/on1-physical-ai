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


# ============================================================
# RESPONSE HELPERS
# ============================================================

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

    # CORS
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

    # Prevent stale API responses in browser/PWA
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


# ============================================================
# FIRESTORE — LATEST MISSION
# ============================================================

def load_latest_mission():
    """
    Read the most recently completed mission evidence
    persisted in Firestore.

    This function is READ-ONLY.

    It does NOT:
    - execute a mission
    - update reputation
    - create memory
    - modify mission data
    - modify Konnex status
    - create a new evidence record

    Firestore path:

        devices/{deviceId}/missions/{missionId}
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


# ============================================================
# BUILD RESTORED MISSION RESULT
# ============================================================

def build_latest_mission_result(mission):
    """
    Convert the persisted Firestore mission evidence record
    into the same general result structure consumed by the
    frontend.

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


# ============================================================
# KONNEX SUBMISSION READINESS
# ============================================================

def build_konnex_submission_package(mission):
    """
    Build a READ-ONLY Konnex submission package from the
    latest persisted and verified mission.

    IMPORTANT:

    This function does NOT:
    - submit anything to Konnex
    - contact a Konnex API
    - modify Firebase
    - modify the mission
    - change Konnex verification status
    - change on-chain status
    - change physical hardware status

    It only verifies whether the persisted evidence currently
    satisfies the local ON1 requirements for a future Konnex
    submission.

    Readiness requires:

    1. Mission exists.
    2. Mission status is COMPLETED.
    3. Validator reports verified=True.
    4. All six validation checks passed.
    5. PoPW-style score exists.
    6. Canonical evidence fingerprint exists.
    7. Konnex adapter exists.
    8. Konnex adapter status is READY_FOR_KONNEX_REVIEW.
    9. submittedToKonnex remains False.
    10. konnexVerified remains False.
    11. onChainVerified remains False.
    12. physicalHardware remains False.
    """

    if not mission:
        return {
            "ready": False,
            "reason": "No persisted mission evidence was found.",
        }

    mission_status = mission.get(
        "status"
    )

    validator = mission.get(
        "validatorResult",
        {},
    )

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

    checks = {}

    checks["missionExists"] = True

    checks["missionCompleted"] = (
        mission_status == "COMPLETED"
    )

    checks["missionVerified"] = (
        validator.get("verified") is True
    )

    checks["validationComplete"] = (
        validator.get("passedChecks") == 6
        and validator.get("totalChecks") == 6
    )

    checks["powpScorePresent"] = (
        mission.get("powpScore") is not None
    )

    checks["evidenceFingerprintPresent"] = (
        bool(
            fingerprint
        )
    )

    checks["canonicalFingerprintPresent"] = (
        bool(
            fingerprint.get(
                "fingerprint"
            )
        )
    )

    checks["konnexAdapterPresent"] = (
        bool(
            konnex_adapter
        )
    )

    checks["konnexAdapterReady"] = (
        konnex_adapter.get(
            "status"
        )
        == "READY_FOR_KONNEX_REVIEW"
    )

    checks["notSubmittedToKonnex"] = (
        konnex_adapter.get(
            "submittedToKonnex",
            False,
        )
        is False
    )

    checks["notKonnexVerified"] = (
        konnex_adapter.get(
            "konnexVerified",
            False,
        )
        is False
    )

    checks["notOnChainVerified"] = (
        konnex_adapter.get(
            "onChainVerified",
            False,
        )
        is False
    )

    checks["physicalHardwareNotClaimed"] = (
        konnex_adapter.get(
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

    checks["evidenceArtifactFingerprintMatches"] = (
        bool(
            evidence_artifact.get(
                "sha256"
            )
        )
        and evidence_artifact.get(
            "sha256"
        )
        == fingerprint.get(
            "fingerprint"
        )
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
            else "NOT_READY_FOR_KONNEX_SUBMISSION"
        ),

        "submission": {
            "submitted": False,
            "submittedToKonnex": False,
            "konnexVerified": False,
            "onChainVerified": False,
            "physicalHardware": False,
        },

        "project": PROJECT_NAME,

        "prototypeVersion": PROTOTYPE_VERSION,

        "adapter": {
            "schema": konnex_adapter.get(
                "schema"
            ),
            "name": konnex_adapter.get(
                "name"
            ),
            "version": konnex_adapter.get(
                "version"
            ),
            "status": konnex_adapter.get(
                "status"
            ),
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
            "fingerprint": fingerprint.get(
                "fingerprint"
            ),
            "algorithm": fingerprint.get(
                "algorithm",
                "SHA-256",
            ),
            "artifactSha256": (
                evidence_artifact.get(
                    "sha256"
                )
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


# ============================================================
# API HANDLER
# ============================================================

class ON1APIHandler(BaseHTTPRequestHandler):

    server_version = "ON1PhysicalAI/0.5.2"

    def log_message(self, format_string, *args):
        """
        Keep standard HTTP logging while making it easy to
        identify ON1 Physical AI API requests in Render logs.
        """

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
                        "error": "Endpoint not found.",
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
                    "error": "Internal server error.",
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
                handle_create_mission(self)

            else:

                send_json(
                    self,
                    404,
                    {
                        "error": "Endpoint not found.",
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
                    "error": "Internal server error.",
                    "message": str(exc),
                },
            )


# ============================================================
# GET /
# ============================================================

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


# ============================================================
# GET /health
# ============================================================

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


# ============================================================
# GET /robot
# ============================================================

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


# ============================================================
# GET /missions/latest
# ============================================================

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


# ============================================================
# GET /konnex/submission/latest
# ============================================================

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


# ============================================================
# POST /missions
# ============================================================

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

    if not isinstance(
        start,
        (list, tuple),
    ) or len(start) != 2:

        raise ValueError(
            "start must be an array containing exactly two coordinates."
        )

    if not isinstance(
        target,
        (list, tuple),
    ) or len(target) != 2:

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


# ============================================================
# SERVER
# ============================================================

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


# ============================================================
# NON-DESTRUCTIVE SELF-TEST DOUBLES
# ============================================================

class SelfTestRobot:

    """
    In-memory robot used only by the API self-test.

    It deliberately does not connect to Firebase and does not
    modify production machine state.
    """

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

    """
    In-memory mission engine used only by the API self-test.

    This produces the same essential API contract expected
    from the production MissionEngine without touching Firebase.
    """

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

                "algorithm": "SHA-256",

            },

            "konnexAdapter": {

                "schema": (
                    "on1.physical-ai.konnex-mission.v1"
                ),

                "name": (
                    "ON1 Konnex Adapter"
                ),

                "version": "0.1.0",

                "status": (
                    "READY_FOR_KONNEX_REVIEW"
                ),

                "submittedToKonnex": False,

                "konnexVerified": False,

                "onChainVerified": False,

                "physicalHardware": False,
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

    """
    In-memory replacement for export_evidence() during self-test.

    No production backend_output file is created.
    No Firebase state is changed.
    """

    return (
        Path(
            "SELF_TEST_ONLY/"
            "mission-result.json"
        ),

        "self-test-canonical-fingerprint",
    )


# ============================================================
# SELF-TEST HTTP CLIENT
# ============================================================

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

            if raw:

                parsed = json.loads(
                    raw
                )

            else:

                parsed = {}

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


# ============================================================
# SELF-TEST ASSERTION
# ============================================================

def assert_condition(
    condition,
    message,
):

    if not condition:

        raise RuntimeError(
            f"SELF-TEST FAILED: {message}"
        )


# ============================================================
# NON-DESTRUCTIVE API SELF-TEST
# ============================================================

def run_self_test():

    """
    Runs the API contract test against isolated in-memory
    components.

    IMPORTANT:

    This test does NOT execute a real Firebase-backed mission.

    It therefore cannot increment:
    - mission_count
    - reputation
    - successful_missions
    - failed_missions

    and cannot create production memory records.
    """

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

        # ----------------------------------------------------
        # Replace production dependencies with isolated
        # in-memory test doubles.
        # ----------------------------------------------------

        robot = SelfTestRobot()

        engine = SelfTestEngine()

        export_evidence = (
            self_test_export_evidence
        )

        # ----------------------------------------------------
        # Start temporary API server on an OS-assigned port.
        # ----------------------------------------------------

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

        assert_condition(
            data.get(
                "endpoints",
                {},
            ).get(
                "konnexSubmissionReadiness"
            )
            == "GET /konnex/submission/latest",
            "GET / must expose the Konnex readiness endpoint.",
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

        assert_condition(
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
            ) > 0,
            "Mission must contain telemetry.",
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

        assert_condition(
            evidence_artifact.get(
                "konnexVerified"
            ) is False,
            "Self-test must report Konnex verification as false.",
        )

        assert_condition(
            evidence_artifact.get(
                "onChainVerified"
            ) is False,
            "Self-test must report on-chain verification as false.",
        )

        # ----------------------------------------------------
        # Prepare isolated latest mission for the new
        # read-only Konnex readiness endpoint.
        # ----------------------------------------------------

        self_test_latest_mission = dict(
            mission
        )

        self_test_latest_mission[
            "persistedAt"
        ] = (
            "2026-01-01T00:00:02+00:00"
        )

        # Ensure the self-test evidence fingerprint and
        # artifact use the exact same canonical value.
        self_test_latest_mission[
            "evidenceFingerprint"
        ] = {
            "fingerprint": (
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
            "name": (
                "ON1 Konnex Adapter"
            ),
            "version": "0.1.0",
            "status": (
                "READY_FOR_KONNEX_REVIEW"
            ),
            "submittedToKonnex": False,
            "konnexVerified": False,
            "onChainVerified": False,
            "physicalHardware": False,
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
                "submission",
                {},
            ).get(
                "submittedToKonnex"
            ) is False,
            "Konnex readiness must never claim submission occurred.",
        )

        assert_condition(
            data.get(
                "submission",
                {},
            ).get(
                "konnexVerified"
            ) is False,
            "Konnex verification must remain false.",
        )

        assert_condition(
            data.get(
                "submission",
                {},
            ).get(
                "onChainVerified"
            ) is False,
            "On-chain verification must remain false.",
        )

        assert_condition(
            data.get(
                "submission",
                {},
            ).get(
                "physicalHardware"
            ) is False,
            "Physical hardware integration must remain false.",
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

        # ----------------------------------------------------
        # Verify production objects were not used.
        # ----------------------------------------------------

        assert_condition(
            robot is not original_robot,
            "Self-test robot isolation must be active.",
        )

        assert_condition(
            engine is not original_engine,
            "Self-test engine isolation must be active.",
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

        # ----------------------------------------------------
        # Always restore production objects.
        # ----------------------------------------------------

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


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    if os.getenv(
        "ON1_API_TEST",
        "0",
    ) == "1":

        run_self_test()

    else:

        run_server()
