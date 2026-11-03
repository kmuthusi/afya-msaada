import argparse
import json

from . import core


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("import")
    subs.add_parser("sources")
    subs.add_parser("index")
    subs.add_parser("restore-demo-approvals")
    for name in ("approve", "revoke"):
        cmd = subs.add_parser(name)
        cmd.add_argument("filename")
        cmd.add_argument("--reviewer", required=True)
        cmd.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.command == "import":
        result = core.ingest()
    elif args.command == "sources":
        result = core.sources()
    elif args.command == "index":
        result = {"embedded_passages": core.index_embeddings()}
    elif args.command == "restore-demo-approvals":
        known = core.manifest()
        result = []
        for source in core.sources():
            previous = known[source["filename"]]
            legacy = previous.get("legacy_approval") or {}
            if (source["status"] == "staged" and source["sha256"] == previous.get("legacy_sha256")
                    and legacy.get("note") and legacy.get("reviewed_by")):
                result.append(core.change_status(source["filename"], "approve", legacy["reviewed_by"],
                                                 "Carried over user reported 2026-11-02 approval for identical PDF hash; local demo only"))
    else:
        result = core.change_status(args.filename, args.command, args.reviewer, args.note)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
