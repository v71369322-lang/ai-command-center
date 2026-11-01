"""Trusted verifier: deliberately does not import executor rendering code."""
import hashlib
import json


def verify(payload: dict, envelope: str) -> tuple[str, str]:
    if len(envelope.encode()) > 65536:
        raise ValueError("oversized_result")
    result = json.loads(envelope)
    if set(result) != {"operation_id", "fence", "markdown"}:
        raise ValueError("invalid_manifest")
    # Only JSON string values are admitted by the task contract.
    expected_lines = ["# Synthetic result", ""]
    for key in sorted(payload["values"]):
        expected_lines.append(f"- {key}: {payload['values'][key]}")
    expected = "\n".join(expected_lines) + "\n"
    if result["markdown"] != expected:
        raise ValueError("incorrect_result")
    return expected, hashlib.sha256(expected.encode()).hexdigest()
