"""Parse the OCR workflow YAML and syntax-check every embedded run: block."""
import subprocess
import sys
from pathlib import Path
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ocr-engine-tests.yml"

def walk(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "run":
                if not isinstance(item, str) or not item.strip():
                    raise SystemExit("WORKFLOW_RUN_BLOCK_INVALID")
                found.append(item)
            else:
                walk(item, found)
    elif isinstance(value, list):
        for item in value:
            walk(item, found)

def main():
    text = WORKFLOW.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print("WORKFLOW_YAML_PARSE_FAILED:" + str(exc))
        return 2
    if not isinstance(parsed, dict) or "jobs" not in parsed:
        print("WORKFLOW_ROOT_OR_JOBS_INVALID")
        return 2
    blocks = []
    walk(parsed, blocks)
    if not blocks:
        print("NO_RUN_BLOCKS_FOUND")
        return 2
    for index, block in enumerate(blocks, 1):
        result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
        if result.returncode:
            print("BASH_SYNTAX_FAILED_BLOCK_" + str(index))
            print(result.stderr)
            return 2
    print("WORKFLOW_YAML_PARSE=PASS")
    print("WORKFLOW_RUN_BLOCKS_BASH_N=" + str(len(blocks)) + ":PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
