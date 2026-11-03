"""Internal build preflight and strict release check."""
import argparse
import json

from apps.api.afya import core
from evals.readiness import check as release_check


def check(release: bool = False) -> dict:
    approved = [source for source in core.sources() if source["status"] == "approved"]
    failures = []
    if not approved:
        failures.append("No approved sources")
    index = core.index_status()
    if index["status"] != "ready":
        failures.append("Embedding index is missing or stale")
    if release:
        failures.extend(release_check()["failures"])
    return {"ready": not failures, "mode": "release" if release else "internal",
            "approved_sources": len(approved), "index": index, "failures": list(dict.fromkeys(failures))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    result = check(parser.parse_args().release)
    print(json.dumps(result, indent=2))
    if not result["ready"]:
        raise SystemExit(1)
