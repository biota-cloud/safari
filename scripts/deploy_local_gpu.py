#!/usr/bin/env python3
"""
Deploy worker scripts to a local GPU machine.

This is the SSH equivalent of `modal deploy` — run once after code changes,
then all subsequent inference/training calls use the deployed code.

Usage:
    python scripts/deploy_local_gpu.py --user-id <UUID> --machine <name>
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ssh_client import deploy_to_local_gpu


def main():
    parser = argparse.ArgumentParser(
        description="Deploy worker scripts to a local GPU machine"
    )
    parser.add_argument(
        "--user-id", required=True, help="User UUID from Supabase"
    )
    parser.add_argument(
        "--machine", required=True, help="Machine name (as configured in settings)"
    )
    args = parser.parse_args()

    try:
        result = deploy_to_local_gpu(args.user_id, args.machine)
        sys.exit(0 if not result.get("errors") else 1)
    except Exception as e:
        print(f"\n❌ Deploy failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
