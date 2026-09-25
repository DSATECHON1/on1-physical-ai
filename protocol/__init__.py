"""
ON1 Physical AI Protocol Layer.

This package defines the local protocol boundary between:

    Mission Request
        ↓
    ON1 Miner
        ↓
    Execution Evidence
        ↓
    ON1 Validator
        ↓
    Validation / PoPW Score
        ↓
    Canonical Evidence Fingerprint

This is a software-first local protocol implementation.

It does NOT:
- connect to Konnex
- submit transactions
- use blockchain wallets
- claim on-chain verification
- claim physical hardware verification

Those integrations belong to a later runtime/network layer.
"""

from .mission import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    MissionRequest,
    MissionResponse,
    MissionTarget,
    MachineIdentity,
    TelemetryPoint,
    ExecutionEvidence,
    ValidationResult,
    calculate_distance,
    calculate_evidence_fingerprint,
)

from .miner import (
    MINER_PROTOCOL_ROLE,
    Miner,
    MinerExecutionResult,
)

from .validator import (
    VALIDATOR_PROTOCOL_ROLE,
    Validator,
    ValidatorResult,
)

__all__ = [
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "MissionRequest",
    "MissionResponse",
    "MissionTarget",
    "MachineIdentity",
    "TelemetryPoint",
    "ExecutionEvidence",
    "ValidationResult",
    "calculate_distance",
    "calculate_evidence_fingerprint",
    "MINER_PROTOCOL_ROLE",
    "Miner",
    "MinerExecutionResult",
    "VALIDATOR_PROTOCOL_ROLE",
    "Validator",
    "ValidatorResult",
]
