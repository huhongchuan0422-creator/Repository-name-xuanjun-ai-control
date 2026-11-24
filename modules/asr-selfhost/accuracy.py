"""Score real ground-truth transcripts against model output (scripts alone are not tests)."""
import argparse
import json
from pathlib import Path
import unicodedata

def normalized(text):
    # Strip punctuation and whitespace only; do not convert amounts, digits,
    # homophones, or simplified/traditional variants into a falsely correct answer.
    return "".join(ch for ch in unicodedata.normalize("NFC", text)
                   if not ch.isspace() and not unicodedata.category(ch).startswith("P"))

def distance(expected, actual):
    row = list(range(len(actual) + 1))
    for i, left in enumerate(expected, 1):
        nxt = [i]
        for j, right in enumerate(actual, 1):
            nxt.append(min(row[j] + 1, nxt[-1] + 1, row[j-1] + (left != right)))
        row = nxt
    return row[-1]

def compare(cases, predictions):
    if not cases:
        raise ValueError("No reference samples")
    if set(predictions) != {c["id"] for c in cases}:
        raise ValueError("Prediction IDs must exactly match this corpus")
    results = []
    for c in cases:
        output = predictions[c["id"]]
        expected = c["reference"]
        exact = output == expected
        chars = len(normalized(expected))
        edits = distance(normalized(expected), normalized(output))
        # Strict per-sample score remains authoritative for sensitive names and amounts.
        expected_atoms = c.get("critical_clauses", [])
        missing = [a for a in expected_atoms if a not in output]
        results.append({"id": c["id"], "exact": exact, "reference_chars": chars,
                        "character_edits": edits, "missing_critical_clauses": missing})
    edits = sum(c["character_edits"] for c in results)
    chars = sum(c["reference_chars"] for c in results)
    return {"samples": len(results), "exact_samples": sum(c["exact"] for c in results),
            "character_edits": edits, "reference_chars": chars,
            "cer": edits / chars if chars else None, "zero_strict_errors": all(c["exact"] for c in results),
            "results": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references", type=Path)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(json.loads(args.references.read_text()), json.loads(args.predictions.read_text())),
                     indent=2, ensure_ascii=False))
