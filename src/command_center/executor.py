"""Untrusted deterministic synthetic executor. Reads stdin, emits bounded JSON.
No provider calls, credentials, SQL, shell execution, or host mounts.
"""
import json
from pathlib import Path
import sys


def main():
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192:
        raise ValueError("input_limit")
    job = json.loads(raw)
    content = "# Synthetic result\n\n"
    for k, v in sorted(job["values"].items()):
        content += "- " + k + ": " + v + "\n"
    workspace = Path("/work")
    (workspace / "input.json").write_text(json.dumps(job["values"]))
    (workspace / "result.md").write_text(content)
    print(json.dumps({"operation_id": job["operation_id"], "fence": job["fence"], "markdown": content}))


if __name__ == "__main__":
    main()
