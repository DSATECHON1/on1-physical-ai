"""
ON1 Physical AI — Fetch Policy Interface
========================================

Software-first Fetch control policy interface for ON1 Physical AI.

This module is designed around the Konnex-compatible Fetch model interface
described for the testnet simulator:

    Input:
        - state observation
        - float32
        - shape: (state_dim,) or (batch_size, state_dim)

    Output:
        - 13-dimensional action vector
        - float32
        - normalized range [-1.0, 1.0]
        - pd_joint_delta_pos control convention

Important:
    This is an interface-compatible prototype policy.
    It is NOT presented as a trained production robotics model,
    hardware-connected controller, or Konnex-approved model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# ON1 model metadata
# ---------------------------------------------------------------------------

MODEL_NAME = "ON1 Fetch Control Policy"
MODEL_ID = "ON1-FETCH-POLICY-001"
MODEL_VERSION = "0.1.0"

ROBOT_NAME = "Fetch"
CONTROL_MODE = "pd_joint_delta_pos"
OBSERVATION_MODE = "state"

INPUT_DTYPE = "float32"
OUTPUT_DTYPE = "float32"

ACTION_DIM = 13
ACTION_MIN = -1.0
ACTION_MAX = 1.0


@dataclass(frozen=True)
class FetchModelMetadata:
    """
    Metadata describing the model interface.

    These fields describe compatibility requirements. They do not claim
    that the prototype has been trained or approved for live deployment.
    """

    model_name: str = MODEL_NAME
    model_id: str = MODEL_ID
    version: str = MODEL_VERSION

    robot: str = ROBOT_NAME

    observation_mode: str = OBSERVATION_MODE
    control_mode: str = CONTROL_MODE

    input_dtype: str = INPUT_DTYPE
    output_dtype: str = OUTPUT_DTYPE

    output_dimension: int = ACTION_DIM
    action_min: float = ACTION_MIN
    action_max: float = ACTION_MAX

    status: str = "prototype"
    trained: bool = False
    hardware_connected: bool = False
    konnex_verified: bool = False


# ---------------------------------------------------------------------------
# Observation utilities
# ---------------------------------------------------------------------------


def _flatten_tensor(value: Any) -> torch.Tensor:
    """
    Convert a supported observation value into a float32 tensor.
    """

    if isinstance(value, torch.Tensor):
        tensor = value
    else:
        tensor = torch.as_tensor(value)

    return tensor.to(dtype=torch.float32)


def preprocess_observation(
    observation: Any,
    state_dim: Optional[int] = None,
) -> torch.Tensor:
    """
    Convert supported Fetch observations into a batched float32 tensor.

    Supported forms:

        Tensor:
            [state_dim]
            [batch_size, state_dim]

        Dictionary:
            {
                "agent": ...,
                ...
            }

    For dictionary observations, the preferred source is:

        observation["agent"]

    If "agent" is itself a dictionary, common robot-state fields such as
    qpos and qvel are collected in deterministic order.

    The function does not silently invent missing observation values.
    """

    # ---------------------------------------------------------------
    # Tensor / array observation
    # ---------------------------------------------------------------

    if not isinstance(observation, dict):

        state = _flatten_tensor(observation)

        if state.ndim == 1:
            state = state.unsqueeze(0)

        if state.ndim != 2:
            raise ValueError(
                "Fetch observation must have shape "
                "(state_dim,) or (batch_size, state_dim). "
                f"Received shape: {tuple(state.shape)}"
            )

        if state_dim is not None and state.shape[-1] != state_dim:
            raise ValueError(
                f"Expected observation dimension {state_dim}, "
                f"received {state.shape[-1]}."
            )

        return state

    # ---------------------------------------------------------------
    # Dictionary observation
    # ---------------------------------------------------------------

    if "agent" in observation:
        agent = observation["agent"]

        if isinstance(agent, dict):

            parts = []

            # Keep the most common Fetch state components first.
            for key in ("qpos", "qvel"):
                if key in agent:
                    parts.append(_flatten_tensor(agent[key]).flatten())

            # Include remaining agent fields deterministically.
            for key in sorted(agent.keys()):
                if key in ("qpos", "qvel"):
                    continue

                value = agent[key]

                if isinstance(value, dict):
                    continue

                parts.append(_flatten_tensor(value).flatten())

            if not parts:
                raise ValueError(
                    "The 'agent' observation dictionary contains no "
                    "supported numeric state values."
                )

            state = torch.cat(parts, dim=0)

        else:
            state = _flatten_tensor(agent)

    else:
        # Fallback for dictionary observations without "agent".
        parts = []

        for key in sorted(observation.keys()):
            value = observation[key]

            if isinstance(value, dict):
                continue

            try:
                parts.append(_flatten_tensor(value).flatten())
            except (TypeError, ValueError, RuntimeError):
                continue

        if not parts:
            raise ValueError(
                "Unable to extract a numeric state observation."
            )

        state = torch.cat(parts, dim=0)

    if state.ndim == 1:
        state = state.unsqueeze(0)

    if state.ndim != 2:
        raise ValueError(
            "Processed Fetch observation must have shape "
            "(state_dim,) or (batch_size, state_dim). "
            f"Received shape: {tuple(state.shape)}"
        )

    if state_dim is not None and state.shape[-1] != state_dim:
        raise ValueError(
            f"Expected observation dimension {state_dim}, "
            f"received {state.shape[-1]}."
        )

    return state


# ---------------------------------------------------------------------------
# Fetch policy network
# ---------------------------------------------------------------------------


class FetchControlModel(nn.Module):
    """
    Minimal ON1 Fetch control policy.

    Architecture:
        state -> MLP -> 13 actions -> tanh

    The model is intentionally lightweight so the interface can be tested
    before introducing a trained robotics policy.
    """

    def __init__(
        self,
        state_dim: int = 30,
        hidden_dim: int = 256,
        action_dim: int = ACTION_DIM,
    ) -> None:

        super().__init__()

        if state_dim <= 0:
            raise ValueError("state_dim must be greater than zero.")

        if hidden_dim <= 0:
            raise ValueError("hidden_dim must be greater than zero.")

        if action_dim != ACTION_DIM:
            raise ValueError(
                f"Fetch control requires exactly {ACTION_DIM} actions."
            )

        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.action_dim = action_dim

        self.network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),

            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),

            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),

            nn.Linear(hidden_dim, action_dim),
            nn.Tanh(),
        )

    def forward(self, observation: Any) -> torch.Tensor:
        """
        Run one or more Fetch observations through the policy.

        Returns:
            Tensor with shape (batch_size, 13).
        """

        state = preprocess_observation(
            observation,
            state_dim=self.state_dim,
        )

        action = self.network(state)

        # Defensive clamp to guarantee the documented action range.
        action = torch.clamp(
            action,
            min=ACTION_MIN,
            max=ACTION_MAX,
        )

        return action.to(dtype=torch.float32)


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------


def create_fetch_model(
    state_dim: int = 30,
    hidden_dim: int = 256,
) -> FetchControlModel:
    """
    Create the ON1 Fetch prototype policy.

    Default state dimension:
        30

    This matches the example ReplicaCAD_SceneManipulation-v1 interface
    described by the Konnex Fetch model specification.
    """

    model = FetchControlModel(
        state_dim=state_dim,
        hidden_dim=hidden_dim,
        action_dim=ACTION_DIM,
    )

    return model


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def get_model_metadata(
    state_dim: int = 30,
) -> Dict[str, Any]:
    """
    Return machine-readable metadata for the model interface.
    """

    metadata = FetchModelMetadata()

    result = asdict(metadata)

    result.update(
        {
            "input_dimension": state_dim,
            "action_dimension": ACTION_DIM,
            "action_shape": [ACTION_DIM],
            "supported_model_formats": [
                "pytorch",
                "onnx",
                "keras",
            ],
            "training_status": "not_trained",
            "deployment_status": "prototype_only",
            "hardware_rooted_evidence": False,
        }
    )

    return result


# ---------------------------------------------------------------------------
# Compatibility validation
# ---------------------------------------------------------------------------


def validate_action(action: torch.Tensor) -> Tuple[bool, str]:
    """
    Validate a model action against the Fetch interface.
    """

    if not isinstance(action, torch.Tensor):
        return False, "Action must be a torch.Tensor."

    if action.dtype != torch.float32:
        return False, (
            f"Action dtype must be torch.float32, "
            f"received {action.dtype}."
        )

    if action.ndim not in (1, 2):
        return False, (
            "Action must have shape (13,) or "
            "(batch_size, 13)."
        )

    if action.shape[-1] != ACTION_DIM:
        return False, (
            f"Action must have {ACTION_DIM} dimensions, "
            f"received {action.shape[-1]}."
        )

    if not torch.isfinite(action).all():
        return False, "Action contains NaN or infinite values."

    if torch.any(action < ACTION_MIN) or torch.any(action > ACTION_MAX):
        return False, (
            f"Action values must remain in "
            f"[{ACTION_MIN}, {ACTION_MAX}]."
        )

    return True, "Fetch action is interface-compatible."


def validate_model(
    model: FetchControlModel,
) -> Dict[str, Any]:
    """
    Perform a local compatibility test without requiring a robot.

    This verifies the model interface only.
    It does not verify physical robot performance.
    """

    model.eval()

    dummy_observation = torch.zeros(
        model.state_dim,
        dtype=torch.float32,
    )

    with torch.no_grad():
        action = model(dummy_observation)

    valid, message = validate_action(action)

    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "robot": ROBOT_NAME,
        "control_mode": CONTROL_MODE,
        "observation_mode": OBSERVATION_MODE,
        "state_dimension": model.state_dim,
        "action_dimension": ACTION_DIM,
        "action_shape": list(action.shape),
        "action_dtype": str(action.dtype),
        "action_min": float(action.min().item()),
        "action_max": float(action.max().item()),
        "compatible": valid,
        "message": message,
        "hardware_tested": False,
        "konnex_verified": False,
    }


# ---------------------------------------------------------------------------
# ON1 model manifest
# ---------------------------------------------------------------------------


def build_model_manifest(
    state_dim: int = 30,
) -> Dict[str, Any]:
    """
    Build a manifest suitable for future model packaging.
    """

    return {
        "model": get_model_metadata(state_dim=state_dim),
        "interface": {
            "robot": "Fetch",
            "observation": {
                "mode": "state",
                "dtype": "float32",
                "shape": [state_dim],
            },
            "action": {
                "dtype": "float32",
                "shape": [ACTION_DIM],
                "range": [-1.0, 1.0],
                "control_mode": "pd_joint_delta_pos",
            },
        },
        "on1": {
            "project": "ON1 Physical AI",
            "organization": "DSATECHON1",
            "software_first": True,
            "hardware_connected": False,
            "konnex_verified": False,
            "on_chain_verified": False,
        },
    }


# ---------------------------------------------------------------------------
# Local execution
# ---------------------------------------------------------------------------


if __name__ == "__main__":

    model = create_fetch_model(state_dim=30)

    compatibility = validate_model(model)

    print("ON1 Physical AI — Fetch Policy")
    print("--------------------------------")
    print(f"Model ID:       {MODEL_ID}")
    print(f"Version:        {MODEL_VERSION}")
    print(f"Robot:          {ROBOT_NAME}")
    print(f"Control mode:   {CONTROL_MODE}")
    print(f"State dim:      {model.state_dim}")
    print(f"Action dim:     {model.action_dim}")
    print()
    print("Compatibility test:")
    print(f"  Compatible:   {compatibility['compatible']}")
    print(f"  Shape:        {compatibility['action_shape']}")
    print(f"  Dtype:        {compatibility['action_dtype']}")
    print(
        f"  Range:        "
        f"{compatibility['action_min']:.4f} to "
        f"{compatibility['action_max']:.4f}"
    )
    print(f"  Message:      {compatibility['message']}")
    print()
    print("Status:")
    print("  Trained:      False")
    print("  Hardware:     False")
    print("  Konnex:       False")
    print("  On-chain:     False")
