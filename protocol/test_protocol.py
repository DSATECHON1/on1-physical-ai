"""
ON1 Physical AI Protocol Integration Test.

This test verifies the complete local protocol pipeline:

    Mission Request
        ↓
    ON1 Miner
        ↓
    Execution Evidence
        ↓
    ON1 Validator
        ↓
    6/6 Validation
        ↓
    PoPW Score
        ↓
    Canonical SHA-256 Fingerprint

This test is intentionally local.

It does NOT:
- contact Konnex
- use blockchain credentials
- submit transactions
- require Firebase
- claim physical hardware verification
- claim on-chain verification
"""

from __future__ import annotations

import unittest

from protocol import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    MachineIdentity,
    Miner,
    MissionRequest,
    MissionTarget,
    Validator,
)
from protocol.mission import fingerprint_mission_response


class TestON1ProtocolIntegration(unittest.TestCase):
    """End-to-end integration tests for the ON1 protocol layer."""

    def setUp(self) -> None:
        self.machine = MachineIdentity(
            robot_id="ON1-R001",
            identity="ON1-MACHINE-001",
            model="ON1 Virtual Navigator",
        )

        self.mission_request = MissionRequest(
            mission_id="MSN-PROTOCOL-TEST-001",
            task_type="Navigation",
            machine=self.machine,
            start=MissionTarget(
                x=0,
                y=0,
            ),
            target=MissionTarget(
                x=10,
                y=10,
            ),
        )

        self.miner = Miner(
            machine=self.machine,
            miner_id="ON1-MINER-TEST-001",
        )

        self.validator = Validator(
            validator_id="ON1-PROTOCOL-VALIDATOR-TEST-001",
        )

    def test_complete_protocol_pipeline(self) -> None:
        """Verify Mission → Miner → Evidence → Validator → PoPW → Fingerprint."""

        # ---------------------------------------------------------
        # 1. Mission request
        # ---------------------------------------------------------
        request = self.mission_request

        self.assertEqual(
            request.protocol,
            PROTOCOL_NAME,
        )

        self.assertEqual(
            request.protocol_version,
            PROTOCOL_VERSION,
        )

        self.assertEqual(
            request.schema,
            "on1.physical-ai.mission.v1",
        )

        self.assertEqual(
            request.mission_id,
            "MSN-PROTOCOL-TEST-001",
        )

        # ---------------------------------------------------------
        # 2. Miner execution
        # ---------------------------------------------------------
        miner_result = self.miner.execute(request)

        evidence = miner_result.evidence

        self.assertEqual(
            miner_result.mission_request.mission_id,
            request.mission_id,
        )

        self.assertEqual(
            evidence.mission_id,
            request.mission_id,
        )

        self.assertEqual(
            evidence.status,
            "COMPLETED",
        )

        self.assertEqual(
            evidence.execution_mode,
            "software-simulation",
        )

        self.assertFalse(
            evidence.to_dict()["hardwareRooted"]
        )

        self.assertFalse(
            evidence.to_dict()["konnexVerified"]
        )

        self.assertFalse(
            evidence.to_dict()["onChainVerified"]
        )

        # ---------------------------------------------------------
        # 3. Telemetry verification
        # ---------------------------------------------------------
        self.assertGreater(
            len(evidence.telemetry),
            0,
        )

        final_point = evidence.telemetry[-1]

        self.assertAlmostEqual(
            final_point.x,
            request.target.x,
            places=6,
        )

        self.assertAlmostEqual(
            final_point.y,
            request.target.y,
            places=6,
        )

        self.assertAlmostEqual(
            final_point.distance_from_target,
            0.0,
            places=6,
        )

        # ---------------------------------------------------------
        # 4. Independent validator
        # ---------------------------------------------------------
        validator_result = self.validator.validate(
            mission_request=request,
            evidence=evidence,
        )

        validation = validator_result.validation

        self.assertEqual(
            validation.validator_id,
            "ON1-PROTOCOL-VALIDATOR-TEST-001",
        )

        self.assertEqual(
            validation.total_checks,
            6,
        )

        self.assertEqual(
            validation.passed_checks,
            6,
        )

        self.assertTrue(
            validation.verified
        )

        self.assertEqual(
            validation.score,
            100.0,
        )

        expected_checks = {
            "missionStarted": True,
            "missionCompleted": True,
            "telemetryPresent": True,
            "targetReached": True,
            "robotIdentityPresent": True,
            "evidenceGenerated": True,
        }

        self.assertEqual(
            validation.checks,
            expected_checks,
        )

        # ---------------------------------------------------------
        # 5. PoPW-style score
        # ---------------------------------------------------------
        powp_score = validation.score

        self.assertEqual(
            powp_score,
            100.0,
        )

        # ---------------------------------------------------------
        # 6. Canonical SHA-256 fingerprint
        # ---------------------------------------------------------
        fingerprint = fingerprint_mission_response(
            mission_request=request,
            evidence=evidence,
            validation=validation,
            powp_score=powp_score,
        )

        self.assertIsInstance(
            fingerprint,
            str,
        )

        self.assertEqual(
            len(fingerprint),
            64,
        )

        self.assertRegex(
            fingerprint,
            r"^[0-9a-f]{64}$",
        )

        # ---------------------------------------------------------
        # 7. Fingerprint determinism
        # ---------------------------------------------------------
        #
        # Execution timestamps are deliberately excluded from the
        # canonical evidence payload. Therefore, another execution
        # of the same mission request should produce the same
        # canonical fingerprint.
        #
        second_miner_result = self.miner.execute(request)

        second_validation_result = self.validator.validate(
            mission_request=request,
            evidence=second_miner_result.evidence,
        )

        second_fingerprint = fingerprint_mission_response(
            mission_request=request,
            evidence=second_miner_result.evidence,
            validation=second_validation_result.validation,
            powp_score=second_validation_result.validation.score,
        )

        self.assertEqual(
            fingerprint,
            second_fingerprint,
        )

        # ---------------------------------------------------------
        # 8. Protocol roles
        # ---------------------------------------------------------
        self.assertEqual(
            self.miner.miner_id,
            "ON1-MINER-TEST-001",
        )

        self.assertEqual(
            self.validator.validator_id,
            "ON1-PROTOCOL-VALIDATOR-TEST-001",
        )

    def test_validator_does_not_accept_failed_execution(self) -> None:
        """Verify that the validator rejects incomplete execution evidence."""

        miner_result = self.miner.execute(
            self.mission_request
        )

        evidence = miner_result.evidence

        # Deliberately alter the evidence status.
        evidence.status = "FAILED"

        validator_result = self.validator.validate(
            mission_request=self.mission_request,
            evidence=evidence,
        )

        validation = validator_result.validation

        self.assertFalse(
            validation.verified
        )

        self.assertLess(
            validation.score,
            100.0,
        )

        self.assertFalse(
            validation.checks["missionCompleted"]
        )

        # The other structural checks should still be evaluated.
        self.assertTrue(
            validation.checks["telemetryPresent"]
        )

        self.assertTrue(
            validation.checks["targetReached"]
        )

        self.assertTrue(
            validation.checks["robotIdentityPresent"]
        )

        self.assertTrue(
            validation.checks["evidenceGenerated"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
