"""
ON1 Physical AI
Backend HTTP API

Provides a lightweight HTTP interface for the ON1 Physical AI
mission engine.

Endpoints:

GET  /health
GET  /robot
POST /missions

This is a software prototype.

It does NOT represent:
- live Konnex verification
- blockchain verification
- an on-chain transaction
- physical robot hardware
"""

from __future__ import annotations

import json
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from typing import Any
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

HOST = "0.0.0.0"
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

    handler.end_headers()

    handler.wfile.write(
        body
    )


def read_json_body(
    handler: BaseHTTPRequestHandler,
) -> dict[str, Any]:

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
        "ON1PhysicalAI/0.1"
    )

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    def do_OPTIONS(
        self,
    ) -> None:

        self.send_response(
            204
        )

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

        self.end_headers()

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(
        self,
    ) -> None:

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path.rstrip(
            "/"
        )

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

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(
        self,
    ) -> None:

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path.rstrip(
            "/"
        )

        if path == "":
            path = "/"

        if path == "/missions":
            self.handle_create_mission()
            return

        self.handle_not_found()

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    def handle_health(
        self,
    ) -> None:

        send_json(
            self,
            200,
            {
                "project": PROJECT_NAME,

                "prototypeVersion": (
                    PROTOTYPE_VERSION
                ),

                "status": "online",

                "service": (
                    "ON1 Physical AI "
                    "Mission API"
                ),

                "hardwareConnected": False,

                "konnexIntegrated": False,

                "onChainVerified": False,
            },
        )

    # --------------------------------------------------------
    # ROBOT
    # --------------------------------------------------------

    def handle_robot(
        self,
    ) -> None:

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

    # --------------------------------------------------------
    # ROOT
    # --------------------------------------------------------

    def handle_root(
        self,
    ) -> None:

        send_json(
            self,
            200,
            {
                "project": PROJECT_NAME,

                "prototypeVersion": (
                    PROTOTYPE_VERSION
                ),

                "service": (
                    "ON1 Physical AI "
                    "Mission API"
                ),

                "status": "online",

                "endpoints": {
                    "health": (
                        "GET /health"
                    ),
                    "robot": (
                        "GET /robot"
                    ),
                    "missions": (
                        "POST /missions"
                    ),
                },

                "simulation": {
                    "type": "backend-api",
                    "hardwareConnected": False,
                    "konnexIntegrated": False,
                    "onChainVerified": False,
                },
            },
        )

    # --------------------------------------------------------
    # CREATE MISSION
    # --------------------------------------------------------

    def handle_create_mission(
        self,
    ) -> None:

        request_data = (
            read_json_body(
                self
            )
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
                        "Invalid mission "
                        "coordinates."
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

                "project": (
                    PROJECT_NAME
                ),

                "prototypeVersion": (
                    PROTOTYPE_VERSION
                ),

                "simulation": {
                    "type": "backend-api",
                    "hardwareConnected": False,
                    "konnexIntegrated": False,
                    "onChainVerified": False,
                },

                "robot": (
                    robot.to_dict()
                ),

                "mission": mission,
            }

            output_path, fingerprint = (
                export_evidence(
                    result
                )
            )

            result[
                "evidenceArtifact"
            ] = {

                "path": str(
                    output_path
                ),

                "sha256": fingerprint,

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
                        "Mission execution "
                        "failed."
                    ),

                    "details": str(
                        error
                    ),
                },
            )

    # --------------------------------------------------------
    # NOT FOUND
    # --------------------------------------------------------

    def handle_not_found(
        self,
    ) -> None:

        send_json(
            self,
            404,
            {
                "error": "Endpoint not found",

                "availableEndpoints": [
                    "GET /",
                    "GET /health",
                    "GET /robot",
                    "POST /missions",
                ],
            },
        )

    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    def log_message(
        self,
        format_string: str,
        *args: Any,
    ) -> None:

        print(
            f"[ON1 API] {format_string % args}"
        )


# ============================================================
# SERVER
# ============================================================

def create_server() -> (
    ThreadingHTTPServer
):

    return ThreadingHTTPServer(
        (
            HOST,
            PORT,
        ),
        ON1PhysicalAIHandler,
    )


def run_server() -> None:

    server = create_server()

    print()
    print("=" * 60)
    print(
        "ON1 PHYSICAL AI — HTTP API"
    )
    print("=" * 60)

    print()
    print(
        f"Server: "
        f"http://{HOST}:{PORT}"
    )

    print()
    print("Endpoints:")

    print(
        "  GET  /health"
    )

    print(
        "  GET  /robot"
    )

    print(
        "  POST /missions"
    )

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
# MAIN
# ============================================================

if __name__ == "__main__":

    run_server()
