"""
ON1 Physical AI — Fetch Policy Compatibility Tests

These tests verify the software interface required by the
ON1 Fetch control policy prototype.

They do NOT claim:
- physical robot compatibility
- trained-policy performance
- Konnex approval
- live Konnex connectivity
- on-chain verification
"""

import torch

from fetch_policy import (
    ACTION_DIM,
    ACTION_MAX,
    ACTION_MIN,
    CONTROL_MODE,
    OBSERVATION_MODE,
    create_fetch_model,
    get_model_metadata,
    preprocess_observation,
    validate_action,
    validate_model,
)


def test_model_creation():
    """The Fetch model should initialize successfully."""

    model = create_fetch_model(state_dim=30)

    assert model.state_dim == 30
    assert model.action_dim == ACTION_DIM
    assert model.action_dim == 13


def test_tensor_observation_preprocessing():
    """A 30-dimensional tensor should become a batched tensor."""

    observation = torch.zeros(
        30,
        dtype=torch.float32,
    )

    processed = preprocess_observation(
        observation,
        state_dim=30,
    )

    assert processed.shape == (1, 30)
    assert processed.dtype == torch.float32


def test_batched_observation_preprocessing():
    """A batch of observations should retain its batch dimension."""

    observation = torch.zeros(
        (4, 30),
        dtype=torch.float32,
    )

    processed = preprocess_observation(
        observation,
        state_dim=30,
    )

    assert processed.shape == (4, 30)
    assert processed.dtype == torch.float32


def test_model_outputs_13_actions():
    """The model must output exactly 13 actions."""

    model = create_fetch_model(
        state_dim=30,
    )

    observation = torch.zeros(
        30,
        dtype=torch.float32,
    )

    with torch.no_grad():
        action = model(observation)

    assert action.shape == (1, 13)
    assert action.dtype == torch.float32


def test_model_outputs_valid_action_range():
    """All actions must remain inside [-1, 1]."""

    model = create_fetch_model(
        state_dim=30,
    )

    observation = torch.randn(
        8,
        30,
        dtype=torch.float32,
    )

    with torch.no_grad():
        action = model(observation)

    assert torch.all(
        action >= ACTION_MIN
    )

    assert torch.all(
        action <= ACTION_MAX
    )


def test_model_output_contains_no_nan_or_infinity():
    """The policy must never produce NaN or infinite values."""

    model = create_fetch_model(
        state_dim=30,
    )

    observation = torch.randn(
        16,
        30,
        dtype=torch.float32,
    )

    with torch.no_grad():
        action = model(observation)

    assert torch.isfinite(action).all()


def test_validate_action():
    """The action validator should accept a valid 13-dimensional action."""

    action = torch.zeros(
        13,
        dtype=torch.float32,
    )

    valid, message = validate_action(action)

    assert valid is True
    assert "compatible" in message.lower()


def test_invalid_action_dimension_is_rejected():
    """An action with the wrong dimension must be rejected."""

    action = torch.zeros(
        12,
        dtype=torch.float32,
    )

    valid, _ = validate_action(action)

    assert valid is False


def test_invalid_action_range_is_rejected():
    """Actions outside [-1, 1] must be rejected."""

    action = torch.zeros(
        13,
        dtype=torch.float32,
    )

    action[0] = 2.0

    valid, _ = validate_action(action)

    assert valid is False


def test_model_compatibility_report():
    """The model compatibility report should pass."""

    model = create_fetch_model(
        state_dim=30,
    )

    result = validate_model(model)

    assert result["compatible"] is True
    assert result["action_dimension"] == 13
    assert result["state_dimension"] == 30
    assert result["hardware_tested"] is False
    assert result["konnex_verified"] is False


def test_model_metadata():
    """Metadata should accurately describe the prototype."""

    metadata = get_model_metadata(
        state_dim=30,
    )

    assert metadata["robot"] == "Fetch"
    assert metadata["observation_mode"] == OBSERVATION_MODE
    assert metadata["control_mode"] == CONTROL_MODE

    assert metadata["input_dtype"] == "float32"
    assert metadata["output_dtype"] == "float32"

    assert metadata["output_dimension"] == 13
    assert metadata["action_dimension"] == 13

    assert metadata["action_min"] == -1.0
    assert metadata["action_max"] == 1.0

    # Important: these must remain false until actually verified.
    assert metadata["trained"] is False
    assert metadata["hardware_connected"] is False
    assert metadata["konnex_verified"] is False


def test_batch_inference():
    """The model should support multiple observations in one call."""

    model = create_fetch_model(
        state_dim=30,
    )

    observation = torch.randn(
        32,
        30,
        dtype=torch.float32,
    )

    with torch.no_grad():
        action = model(observation)

    assert action.shape == (32, 13)
    assert action.dtype == torch.float32

    assert torch.isfinite(action).all()
    assert torch.all(action >= -1.0)
    assert torch.all(action <= 1.0)
