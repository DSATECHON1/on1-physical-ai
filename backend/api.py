"""
ON1 Physical AI
Deployment-Ready Backend HTTP API

Endpoints:

GET  /
GET  /health
GET  /robot
POST /missions

Environment:

PORT
    Port supplied by the deployment platform.
    Defaults to 8000 for local development.

ON1_API_TEST=1
    Runs the automated API self-test and exits.

This is a software prototype.

It does NOT represent:
- live Konnex verification
- blockchain verification
- an on-chain transaction
- physical robot hardware
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from typing import Any
from urllib.error import HTTPError
from urllib.request import (
    Request,
    urlopen,
)
from urllib.parse import urlparse

from main import (
    PROJECT_NAME,
    PROTOTYPE_VERSION,
    robot,
    engine,
    export_evidence,
)


# ============================================================
# CONFIGURATION
# ============================================================

HOST = os.environ.get(
    "HOST",
    "0.0.0.0",
)

try:
    PORT = int(
        os.environ.get(
            "PORT",
            "8000",
        )
    )
except ValueError:
    PORT = 8000


# ============================================================
# RESPONSE HELPERS
# ============================================================

def send_json(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    data: dict[str, Any],
) -> None:
    """Send a JSON HTTP response."""

    body = json.dumps(
        data,
        indent=2,
    ).encode("utf-8")

    handler.send_response(
        status_code
    )

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

    handler.wfile.write(
        body
    )


def read_json_body(
    handler: BaseHTTPRequestHandler,
) -> dict[str, Any]:
    """Read and decode a JSON request body."""

    content_length = handler.headers.get(
        "Content-Length"
    )

    if not content_length:
        return {}

    try:
        length = int(
            content_length
        )
    except ValueError:
        return {}

    if length <= 0:
        return {}

    raw_body = handler.rfile.read(
        length
    )

    try:
        decoded = raw_body.decode(
            "utf-8"
        )

        parsed = json.loads(
            decoded
        )

        if isinstance(
            parsed,
            dict,
        ):
            return parsed

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        pass

    return {}


# ============================================================
# API HANDLER
# ============================================================

class ON1PhysicalAIHandler(
    BaseHTTPRequestHandler
):

    server_version = (
        "ON1PhysicalAI/0.2"
    )

    def do_OPTIONS(self) -> None:
        """Handle browser CORS preflight requests."""

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

    def do_GET(self) -> None:
        """Handle GET requests."""

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path.rstrip("/")

        if path == "":
            path = "/"

        if path == "/health":
            self.handle_health()
            return

        if path == "/robot":
            self.handle_robot()
            return

        if path == "/":
            self.handle_root()
            return

        self.handle_not_found()

    def do_POST(self) -> None:
        """Handle POST requests."""

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path.rstrip("/")

        if path == "":
            path = "/"

        if path == "/missions":
            self.handle_create_mission()
            return

        self.handle_not_found()

    # ========================================================
    # GET /
    # ========================================================

    def handle_root(self) -> None:
        """Return API information."""

        send_json(
            self,
            200,
            {
                "project": PROJECT_NAME,
                "prototypeVersion": PROTOTYPE_VERSION,
                "service": (
                    "ON1 Physical AI Mission API"
                ),
                "status": "online",
                "apiVersion": "0.2",
                "endpoints": {
                    "root": "GET /",
                    "health": "GET /health",
                    "robot": "GET /robot",
                    "missions": "POST /missions",
                },
                "simulation": {
                    "type": "backend-api",
                    "hardwareConnected": False,
                    "konnexIntegrated": False,
                    "onChainVerified": False,
                },
            },
        )

    # ========================================================
    # GET /health
    # ========================================================

    def handle_health(self) -> None:
        """Return service health information."""

        send_json(
            self,
            200,
            {
                "project": PROJECT_NAME,
                "prototypeVersion": PROTOTYPE_VERSION,
                "apiVersion": "0.2",
                "status": "online",
                "service": (
                    "ON1 Physical AI Mission API"
                ),
                "hardwareConnected": False,
                "konnexIntegrated": False,
                "onChainVerified": False,
            },
        )

    # ========================================================
    # GET /robot
    # ========================================================

    def handle_robot(self) -> None:
        """Return current virtual robot state."""

        send_json(
            self,
            200,
            {
                "project": PROJECT_NAME,
                "robot": robot.to_dict(),
                "hardwareConnected": False,
                "konnexIntegrated": False,
                "onChainVerified": False,
            },
        )

    # ========================================================
    # POST /missions
    # ========================================================

    def handle_create_mission(self) -> None:
        """Create and execute a navigation mission."""

        request_data = read_json_body(
            self
        )

        start = request_data.get(
            "start",
            {
                "x": 0,
                "y": 0,
            },
        )

        target = request_data.get(
            "target",
            {
                "x": 10,
                "y": 10,
            },
        )

        if not isinstance(
            start,
            dict,
        ):
            send_json(
                self,
                400,
                {
                    "error": (
                        "Invalid start coordinates."
                    )
                },
            )
            return

        if not isinstance(
            target,
            dict,
        ):
            send_json(
                self,
                400,
                {
                    "error": (
                        "Invalid target coordinates."
                    )
                },
            )
            return

        try:
            start_x = int(
                start.get(
                    "x",
                    0,
                )
            )

            start_y = int(
                start.get(
                    "y",
                    0,
                )
            )

            target_x = int(
                target.get(
                    "x",
                    10,
                )
            )

            target_y = int(
                target.get(
                    "y",
                    10,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            send_json(
                self,
                400,
                {
                    "error": (
                        "Invalid mission coordinates."
                    )
                },
            )
            return

        try:
            mission = (
                engine.execute_navigation(
                    start=(
                        start_x,
                        start_y,
                    ),
                    target=(
                        target_x,
                        target_y,
                    ),
                )
            )

            result = {
                "project": PROJECT_NAME,
                "prototypeVersion": PROTOTYPE_VERSION,
                "simulation": {
                    "type": "backend-api",
                    "hardwareConnected": False,
                    "konnexIntegrated": False,
                    "onChainVerified": False,
                },
                "robot": robot.to_dict(),
                "mission": mission,
            }

            output_path, fingerprint = (
                export_evidence(
                    result
                )
            )

            result["evidenceArtifact"] = {
                "path": str(
                    output_path
                ),
                "sha256": fingerprint,
                "algorithm": "SHA-256",
                "konnexVerified": False,
                "onChainVerified": False,
            }

            send_json(
                self,
                200,
                result,
            )

        except Exception as error:
            send_json(
                self,
                500,
                {
                    "error": (
                        "Mission execution failed."
                    ),
                    "details": str(
                        error
                    ),
                },
            )

    # ========================================================
    # 404
    # ========================================================

    def handle_not_found(self) -> None:
        """Return a structured 404 response."""

        send_json(
            self,
            404,
            {
                "error": (
                    "Endpoint not found"
                ),
                "availableEndpoints": [
                    "GET /",
                    "GET /health",
                    "GET /robot",
                    "POST /missions",
                ],
            },
        )

    # ========================================================
    # LOGGING
    # ========================================================

    def log_message(
        self,
        format_string: str,
        *args: Any,
    ) -> None:
        """Use a compact API log format."""

        print(
            f"[ON1 API] "
            f"{format_string % args}"
        )


# ============================================================
# SERVER
# ============================================================

def create_server(
    host: str = HOST,
    port: int = PORT,
) -> ThreadingHTTPServer:
    """Create the HTTP server."""

    return ThreadingHTTPServer(
        (
            host,
            port,
        ),
        ON1PhysicalAIHandler,
    )


def run_server() -> None:
    """Start the deployment-ready API server."""

    server = create_server()

    actual_host = server.server_address[0]
    actual_port = server.server_address[1]

    print()
    print("=" * 60)
    print(
        "ON1 PHYSICAL AI — HTTP API"
    )
    print("=" * 60)
    print()
    print(
        f"Server: http://{actual_host}:{actual_port}"
    )
    print()
    print("Endpoints:")
    print("  GET  /")
    print("  GET  /health")
    print("  GET  /robot")
    print("  POST /missions")
    print()
    print(
        "Hardware connected: False"
    )
    print(
        "Konnex integrated: False"
    )
    print(
        "On-chain verified: False"
    )
    print()
    print(
        "Press Ctrl+C to stop."
    )
    print()
    print("=" * 60)

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print()
        print(
            "ON1 Physical AI API stopped."
        )

    finally:
        server.server_close()


# ============================================================
# TEST HELPERS
# ============================================================

def api_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Send an HTTP request to the local test server."""

    data = None

    headers = {
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(
            payload
        ).encode("utf-8")

        headers[
            "Content-Type"
        ] = "application/json"

    request = Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(
            request,
            timeout=10,
        ) as response:

            status_code = (
                response.status
            )

            body = (
                response.read()
                .decode("utf-8")
            )

    except HTTPError as error:
        status_code = error.code

        body = (
            error.read()
            .decode("utf-8")
        )

    parsed = json.loads(
        body
    )

    return (
        status_code,
        parsed,
    )


def assert_condition(
    condition: bool,
    message: str,
) -> None:
    """Fail the self-test when a condition is false."""

    if not condition:
        raise RuntimeError(
            f"API self-test failed: {message}"
        )


# ============================================================
# API SELF-TEST
# ============================================================

def run_self_test() -> None:
    """
    Start a temporary local API server,
    verify all public endpoints,
    then stop it.
    """

    print()
    print("=" * 60)
    print(
        "ON1 PHYSICAL AI — API SELF-TEST"
    )
    print("=" * 60)
    print()

    server = create_server(
        host="127.0.0.1",
        port=0,
    )

    actual_port = (
        server.server_address[1]
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    server_thread.start()

    base_url = (
        f"http://127.0.0.1:{actual_port}"
    )

    try:
        time.sleep(0.1)

        # ----------------------------------------------------
        # TEST 1 — ROOT
        # ----------------------------------------------------

        print(
            "1. Testing GET / ..."
        )

        root_status, root = (
            api_request(
                "GET",
                f"{base_url}/",
            )
        )

        assert_condition(
            root_status == 200,
            "GET / did not return HTTP 200.",
        )

        assert_condition(
            root.get("status")
            == "online",
            "Root API status is not online.",
        )

        print(
            "   PASS — /"
        )

        # ----------------------------------------------------
        # TEST 2 — HEALTH
        # ----------------------------------------------------

        print(
            "2. Testing GET /health ..."
        )

        health_status, health = (
            api_request(
                "GET",
                f"{base_url}/health",
            )
        )

        assert_condition(
            health_status == 200,
            "GET /health did not return HTTP 200.",
        )

        assert_condition(
            health.get("status")
            == "online",
            "Health status is not online.",
        )

        assert_condition(
            health.get(
                "konnexIntegrated"
            )
            is False,
            "Konnex integration must remain false.",
        )

        assert_condition(
            health.get(
                "onChainVerified"
            )
            is False,
            "On-chain verification must remain false.",
        )

        print(
            "   PASS — /health"
        )

        # ----------------------------------------------------
        # TEST 3 — ROBOT
        # ----------------------------------------------------

        print(
            "3. Testing GET /robot ..."
        )

        robot_status, robot_data = (
            api_request(
                "GET",
                f"{base_url}/robot",
            )
        )

        assert_condition(
            robot_status == 200,
            "GET /robot did not return HTTP 200.",
        )

        api_robot = robot_data.get(
            "robot",
            {},
        )

        assert_condition(
            api_robot.get("robotId")
            == "ON1-R001",
            "Robot ID is incorrect.",
        )

        assert_condition(
            api_robot.get("identity")
            == "ON1-MACHINE-001",
            "Robot identity is incorrect.",
        )

        assert_condition(
            api_robot.get("model")
            == "ON1 Virtual Navigator",
            "Robot model is incorrect.",
        )

        print(
            "   PASS — /robot"
        )

        # ----------------------------------------------------
        # TEST 4 — CREATE MISSION
        # ----------------------------------------------------

        print(
            "4. Testing POST /missions ..."
        )

        mission_status, mission_data = (
            api_request(
                "POST",
                f"{base_url}/missions",
                {
                    "start": {
                        "x": 0,
                        "y": 0,
                    },
                    "target": {
                        "x": 10,
                        "y": 10,
                    },
                },
            )
        )

        assert_condition(
            mission_status == 200,
            "POST /missions did not return HTTP 200.",
        )

        mission = mission_data.get(
            "mission",
            {},
        )

        assert_condition(
            mission.get(
                "status"
            )
            == "COMPLETED",
            "Mission was not completed.",
        )

        telemetry = mission.get(
            "telemetry",
            [],
        )

        assert_condition(
            len(telemetry) > 0,
            "Mission telemetry is missing.",
        )

        validator_result = (
            mission.get(
                "validatorResult",
                {},
            )
        )

        assert_condition(
            validator_result.get(
                "verified"
            )
            is True,
            "Mission validation did not pass.",
        )

        assert_condition(
            validator_result.get(
                "passedChecks"
            )
            == validator_result.get(
                "totalChecks"
            ),
            "Not all validation checks passed.",
        )

        assert_condition(
            mission.get(
                "powpScore"
            )
            == 100,
            "PoPW-style score is not 100.",
        )

        evidence_artifact = (
            mission_data.get(
                "evidenceArtifact",
                {},
            )
        )

        assert_condition(
            bool(
                evidence_artifact.get(
                    "sha256"
                )
            ),
            "Evidence SHA-256 fingerprint is missing.",
        )

        print(
            "   PASS — /missions"
        )

        # ----------------------------------------------------
        # FINAL RESULT
        # ----------------------------------------------------

        print()
        print(
            "API SELF-TEST PASSED"
        )
        print()
        print(
            "Verified:"
        )
        print(
            "  GET  /health        ✓"
        )
        print(
            "  GET  /robot         ✓"
        )
        print(
            "  POST /missions      ✓"
        )
        print(
            "  Mission telemetry   ✓"
        )
        print(
            "  Evidence generation ✓"
        )
        print(
            "  Local validation    ✓"
        )
        print(
            "  PoPW-style score    ✓"
        )
        print(
            "  SHA-256 fingerprint ✓"
        )
        print()
        print(
            "Konnex integrated: False"
        )
        print(
            "On-chain verified: False"
        )
        print()
        print("=" * 60)

    finally:
        server.shutdown()
        server.server_close()

        server_thread.join(
            timeout=5
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    if os.environ.get(
        "ON1_API_TEST"
    ) == "1":

        run_self_test()

    else:

        run_server()
