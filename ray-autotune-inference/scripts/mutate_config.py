#!/usr/bin/env python3
"""Replace existing configuration values using explicit JSON pointers, offline."""
import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ray_control import Error, ray, validate_candidate


def mutate(source, patches, app_name):
    candidate = copy.deepcopy(source)
    if not isinstance(patches, dict) or not patches:
        raise Error("Changes must be a nonempty object of JSON pointers to values.")
    for pointer, value in patches.items():
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise Error("Every change needs an absolute JSON pointer.")
        parts = pointer[1:].split("/")
        if any("~" in part.replace("~0", "").replace("~1", "") for part in parts):
            raise Error("Invalid JSON pointer escape.")
        parts = [part.replace("~1", "/").replace("~0", "~") for part in parts]
        if len(parts) < 4 or parts[0] != "applications" or parts[2] not in ("args", "deployments"):
            raise Error("Changes must address existing application args or deployment fields.")
        parent = candidate
        try:
            for part in parts[:-1]:
                if isinstance(parent, list):
                    if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                        raise ValueError()
                    parent = parent[int(part)]
                else:
                    parent = parent[part]
            key = parts[-1]
            if not isinstance(parent, dict) or key not in parent:
                raise ValueError()
            parent[key] = value
        except (IndexError, KeyError, TypeError, ValueError):
            raise Error("Pointer must reference an existing object field.") from None
    validate_candidate(source, candidate, app_name)
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--changes", required=True, help="JSON object: pointer -> replacement value")
    parser.add_argument("--app", required=True)
    parser.add_argument("--output", required=True, help="New private candidate JSON file")
    args = parser.parse_args()
    try:
        candidate = mutate(ray.load_json(args.source), ray.load_json(args.changes), args.app)
        ray.private_json(args.output, candidate)
    except (Error, OSError, TypeError, ValueError):
        print("Config edit failed; check paths, app scope, and a fresh output filename.", file=sys.stderr)
        return 1
    print("Private candidate written; no network calls or deployment changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
