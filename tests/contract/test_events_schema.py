"""Every events.jsonl fixture / recorded run must validate against the contract."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))
V = Draft202012Validator(SCHEMA)

LOGS = sorted([*ROOT.glob("ui/fixtures/*.jsonl"), *ROOT.glob("runs/*/events.jsonl"),
               ROOT / "tests/contract/fixtures/events_min.jsonl"])


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", [p for p in LOGS if p.exists()], ids=lambda p: str(p.relative_to(ROOT)))
def test_log_validates(path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        errs = [e.message for e in V.iter_errors(json.loads(line))]
        assert not errs, f"{path.name}:{n}: {errs}"


def test_bad_event_rejected():
    assert list(V.iter_errors({"id": "evt_1", "type": "nope"}))
