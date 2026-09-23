from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import os
import urllib.error
import urllib.request

from main import (
    PROJECT_NAME,
    PROTOTYPE_VERSION,
    robot,
    engine,
    export_evidence,
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
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))

    # CORS
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, OPTIONS",
    )
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type",
    )

    # Prevent stale API responses in browser/PWA
    handler.send_header("Cache-Control", "no-store")

    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler):
    content_length = int(handler.headers.get("Content-Length", "0"))

    if content_length <= 0:
        return {}

    raw_body = handler.rfile.read(content_length)

    if not raw_body:
        return {}

    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Request body must contain valid JSON.")

    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object.")

    return parsed


# ============================================================
# API HANDLER
# ============================================================

class ON1APIHandler(BaseHTTPRequestHandler):

    server_version = "ON1PhysicalAI/0.5.0"

    def log_message(self, format_string, *args):
        """
        Keep standard HTTP logging while making it easy to identify
        ON1 Physical AI API requests in Render logs.
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

        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )
        self.send_header("Access-Control-Max-Age", "86400")

        self.end_headers()

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        try:

            if path == "/":
                handle_root(self)

            elif path == "/health":
                handle_health(self)

            elif path == "/robot":
                handle_robot(self)

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
        path = self.path.split("?", 1)[0]

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
            "prototypeVersion": PROTOTYPE_VERSION,
            "service": "ON1 Physical AI API",
            "status": "online",
            "apiVersion": "0.2",
            "endpoints": {
                "health": "GET /health",
                "robot": "GET /robot",
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
            "prototypeVersion": PROTOTYPE_VERSION,
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
# POST /missions
# ============================================================

def handle_create_mission(handler):
    payload = read_json_body(handler)

    start = payload.get("start", [0, 0])
    target = payload.get("target", [10, 10])

    if not isinstance(start, (list, tuple)) or len(start) != 2:
        raise ValueError(
            "start must be an array containing exactly two coordinates."
        )

    if not isinstance(target, (list, tuple)) or len(target) != 2:
        raise ValueError(
            "target must be an array containing exactly two coordinates."
        )

    try:
        start_x = int(start[0])
        start_y = int(start[1])
        target_x = int(target[0])
        target_y = int(target[1])
    except (TypeError, ValueError):
        raise ValueError(
            "start and target coordinates must be integers."
        )

    mission = engine.execute_navigation(
        start=(start_x, start_y),
        target=(target_x, target_y),
    )

    result = {
        "project": PROJECT_NAME,
        "prototypeVersion": PROTOTYPE_VERSION,
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

    output_path, fingerprint = export_evidence(result)

    result["evidenceArtifact"] = {
        "path": str(output_path),
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
        (HOST, PORT),
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
            "identity": "ON1-SELF-TEST-MACHINE",
            "model": "ON1 Self-Test Navigator",
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

    This produces the same essential API contract expected from
    the production MissionEngine without touching Firebase.
    """

    def execute_navigation(self, start, target):
        return {
            "missionId": "MSN-SELF-TEST-001",
            "robotId": "ON1-SELF-TEST",
            "taskType": "Navigation",
            "start": {
                "x": start[0],
                "y": start[1],
            },
            "target": {
                "x": target[0],
                "y": target[1],
            },
            "startedAt": "2026-01-01T00:00:00+00:00",
            "completedAt": "2026-01-01T00:00:01+00:00",
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
                "evidenceId": "EVD-SELF-TEST-001",
                "missionId": "MSN-SELF-TEST-001",
                "robotId": "ON1-SELF-TEST",
                "taskType": "Navigation",
                "status": "COMPLETED",
            },
            "validatorResult": {
                "validatorId": "ON1-SELF-TEST-VALIDATOR",
                "validatedAt": "2026-01-01T00:00:01+00:00",
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
        }


def self_test_export_evidence(result):
    """
    In-memory replacement for export_evidence() during self-test.

    No production backend_output file is created.
    No Firebase state is changed.
    """

    return (
        Path("SELF_TEST_ONLY/mission-result.json"),
        "self-test-sha256-fingerprint",
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
    url = f"{base_url}{path}"

    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            raw = response.read().decode("utf-8")

            if raw:
                parsed = json.loads(raw)
            else:
                parsed = {}

            return response.status, parsed

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "error": raw,
            }

        return exc.code, parsed


# ============================================================
# SELF-TEST ASSERTION
# ============================================================

def assert_condition(condition, message):
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
    It therefore cannot increment mission_count, reputation,
    successful_missions, failed_missions, or create memory
    records in production Firebase.
    """

    global robot
    global engine
    global export_evidence

    original_robot = robot
    original_engine = engine
    original_export_evidence = export_evidence

    test_server = None

    try:

        # ----------------------------------------------------
        # Replace production dependencies with isolated
        # in-memory test doubles.
        # ----------------------------------------------------

        robot = SelfTestRobot()
        engine = SelfTestEngine()
        export_evidence = self_test_export_evidence

        # ----------------------------------------------------
        # Start temporary API server on an OS-assigned port.
        # ----------------------------------------------------

        test_server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            ON1APIHandler,
        )

        test_port = test_server.server_address[1]

        server_thread = Thread(
            target=test_server.serve_forever,
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
            data.get("status") == "online",
            "GET / must report online status.",
        )

        assert_condition(
            data.get("project") == PROJECT_NAME,
            "GET / must report the correct project.",
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
            data.get("status") == "online",
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
            data["robot"].get("robotId") == "ON1-SELF-TEST",
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
                "start": [0, 0],
                "target": [10, 10],
            },
        )

        assert_condition(
            status == 200,
            "POST /missions must return HTTP 200.",
        )

        mission = data.get("mission", {})

        assert_condition(
            mission.get("status") == "COMPLETED",
            "Self-test mission must be COMPLETED.",
        )

        assert_condition(
            isinstance(
                mission.get("telemetry"),
                list,
            )
            and len(mission["telemetry"]) > 0,
            "Mission must contain telemetry.",
        )

        validator = mission.get(
            "validatorResult",
            {},
        )

        assert_condition(
            validator.get("verified") is True,
            "Mission validator must report verified=True.",
        )

        assert_condition(
            validator.get("passedChecks") == 6,
            "Validator must pass all 6 checks.",
        )

        assert_condition(
            validator.get("totalChecks") == 6,
            "Validator must contain 6 total checks.",
        )

        assert_condition(
            mission.get("powpScore") == 100,
            "PoPW-style score must be 100.",
        )

        evidence_artifact = data.get(
            "evidenceArtifact",
            {},
        )

        assert_condition(
            evidence_artifact.get("sha256")
            == "self-test-sha256-fingerprint",
            "Evidence artifact fingerprint must be returned.",
        )

        assert_condition(
            evidence_artifact.get("konnexVerified") is False,
            "Self-test must report Konnex verification as false.",
        )

        assert_condition(
            evidence_artifact.get("onChainVerified") is False,
            "Self-test must report on-chain verification as false.",
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
            "GET /              PASS",
            flush=True,
        )
        print(
            "GET /health        PASS",
            flush=True,
        )
        print(
            "GET /robot         PASS",
            flush=True,
        )
        print(
            "POST /missions     PASS",
            flush=True,
        )
        print(
            "Validation 6/6     PASS",
            flush=True,
        )
        print(
            "PoPW Score 100     PASS",
            flush=True,
        )
        print(
            "Firebase mutation  NONE",
            flush=True,
        )
        print(
            "Production mission NONE",
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
        export_evidence = original_export_evidence

        if test_server is not None:
            test_server.shutdown()
            test_server.server_close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    if os.getenv("ON1_API_TEST", "0") == "1":
        run_self_test()

    else:
        run_server()
