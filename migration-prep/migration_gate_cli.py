"""Safe CLI for rendering/evaluating G1-G5 candidates; never mutates hosts."""
from __future__ import print_function

import argparse
import json
import os
import sys

from archive_binding import verify
from cutover_gate import evaluate_isolation, evaluate_shadow
from gate_common import GateError, load_json, sha256_value
from runner_retirement import command_plan, evaluate as evaluate_runner
from writer_fence import bind_discovery_to_coverage, discover_writer_paths
from yibi_retirement import evaluate as evaluate_yibi, retirement_plan


HERE = os.path.dirname(os.path.abspath(__file__))


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parser():
    root = argparse.ArgumentParser(description="Fail-closed Tokyo/Korea migration gate candidate")
    root.add_argument("--inventory", default=os.path.join(HERE, "gate_inventory.json"))
    # Python 3.6 does not support required=True on add_subparsers.
    commands = root.add_subparsers(dest="command")

    runner = commands.add_parser("runner-plan")
    runner.add_argument("--host", choices=("tokyo", "korea"), required=True)

    commands.add_parser("yibi-plan")

    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--gate", choices=("G1", "G2", "G5_ISOLATION", "G5_SHADOW"), required=True)
    evaluation.add_argument("--input", required=True)
    evaluation.add_argument("--host", choices=("tokyo", "korea"))

    discovery = commands.add_parser("writer-discover")
    discovery.add_argument("--root", action="append", required=True)
    discovery.add_argument("--coverage")

    binding = commands.add_parser("archive-verify")
    binding.add_argument("--statement", required=True)
    binding.add_argument("--binding", required=True)
    binding.add_argument("--public-key", required=True)
    binding.add_argument("--pinned-public-key-sha256", required=True)
    return root


def main(argv=None):
    arguments = parser().parse_args(argv)
    if not arguments.command:
        parser().error("a command is required")
    inventory = load_json(arguments.inventory)
    try:
        if arguments.command == "runner-plan":
            host = inventory["hosts"][arguments.host]
            emit({"gate": "G1", "host": arguments.host,
                  "plan": command_plan(host, host["runner"], inventory["runner_privilege_residue"]),
                  "execution_authorized": False})
        elif arguments.command == "yibi-plan":
            emit({"gate": "G2", "plan": retirement_plan(inventory["yibi"]),
                  "execution_authorized": False, "re_enable_yibi": False})
        elif arguments.command == "evaluate":
            observation = load_json(arguments.input)
            if arguments.gate == "G1":
                if not arguments.host:
                    raise GateError("G1_HOST_REQUIRED")
                result = evaluate_runner(inventory["hosts"][arguments.host], observation)
            elif arguments.gate == "G2":
                result = evaluate_yibi(inventory["yibi"], observation)
            elif arguments.gate == "G5_ISOLATION":
                result = evaluate_isolation(observation)
            else:
                result = evaluate_shadow(observation)
            emit(result)
        elif arguments.command == "writer-discover":
            findings = discover_writer_paths(arguments.root)
            coverage = load_json(arguments.coverage) if arguments.coverage else []
            emit({"gate": "G3", "findings": findings,
                  "findings_sha256": sha256_value(findings),
                  "coverage": bind_discovery_to_coverage(findings, coverage),
                  "production_mutation": False})
        elif arguments.command == "archive-verify":
            emit(verify(load_json(arguments.statement), load_json(arguments.binding),
                        arguments.public_key, arguments.pinned_public_key_sha256))
        else:
            raise GateError("UNKNOWN_COMMAND")
    except (GateError, OSError, ValueError, KeyError) as error:
        emit({"status": "HOLD", "error": str(error), "production_mutation": False})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
