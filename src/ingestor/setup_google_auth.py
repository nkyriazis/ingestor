from __future__ import annotations

import sys
from pathlib import Path

from ingestor.google_auth import run_consent_flow


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "usage: python -m ingestor.setup_google_auth <client_secrets.json> <token.json>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    client_secrets_path, token_path = Path(sys.argv[1]), Path(sys.argv[2])
    run_consent_flow(client_secrets_path, token_path)
    print(f"Wrote {token_path}")


if __name__ == "__main__":
    main()
