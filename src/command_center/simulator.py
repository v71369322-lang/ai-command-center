"""Phone-independent synthetic CLI; talks ONLY to a loopback F1 API."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--identity-file", required=True)
    parser.add_argument("--role", choices=["owner", "operator", "agent"], default="operator")
    parser.add_argument("--key", default="synthetic-demo-1")
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only loopback F1 API allowed")
    token = json.loads(Path(args.identity_file).read_text())[args.role]
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": args.key}
    with httpx.Client(base_url=args.url, timeout=5, trust_env=False) as client:
        response = client.post("/api/simulator/commands", headers=headers,
                               json={"kind": "render", "values": {"message": "synthetic only"}})
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
