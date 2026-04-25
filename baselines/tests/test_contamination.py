"""D-05 contamination boundary enforcement (D-10 + D-11 corollary).

Greps every results/.../llm_calls.jsonl AND every committed
baselines/tests/fixtures/llm_calls/*.jsonl for any UXLC fragment in
request.prompt. A single match fails the test, naming the matched
fragment + the file path.

Substrate: BL-01's replay log (D-10) is the durable record of every
prompt sent. The contamination boundary (D-05) prohibits UXLC text from
reaching the prompt; this test makes the prohibition mechanically
checkable. Plan 03-08, Phase 3 Wave 4.

The detection logic is factored into `_scan_for_contamination(roots)` so
the production gate AND the self-test invoke the SAME function — a
regression in the scan logic surfaces as the self-test failing, not as
silent under-detection in production.
"""

from __future__ import annotations

import json
from pathlib import Path

# .../baselines/tests/test_contamination.py
#   parents[0] = baselines/tests/
#   parents[1] = baselines/
#   parents[2] = masoretic-benchmark/   <-- sibling repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "baselines" / "tests" / "fixtures" / "uxlc_fragments.json"


def _fragments() -> list[str]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["fragments"]


def _scan_for_contamination(scan_roots: list[Path]) -> list[tuple[str, str, str]]:
    """Walk every llm_calls.jsonl reachable from scan_roots and return offenders.

    Returns a list of (fragment, "<path>:<line_no>", prompt_preview) tuples.
    Empty list = clean.

    Inspects (per root):
      - <root>/results/llm_vision/*/llm_calls.jsonl   (production runs)
      - <root>/baselines/tests/fixtures/llm_calls/*.jsonl  (committed fixtures)
      - <root>/baselines/tests/fixtures/llm_calls/*.replay.jsonl  (replay fixtures)
      - <root>/*.jsonl                                (planted self-test logs)
    """
    offenders: list[tuple[str, str, str]] = []
    fragments = _fragments()
    log_paths: list[Path] = []
    for root in scan_roots:
        results = root / "results"
        if results.exists():
            log_paths.extend(results.glob("llm_vision/*/llm_calls.jsonl"))
        fixtures = root / "baselines" / "tests" / "fixtures" / "llm_calls"
        if fixtures.exists():
            log_paths.extend(fixtures.glob("*.jsonl"))
            log_paths.extend(fixtures.glob("*.replay.jsonl"))
        # Also scan any *.jsonl directly under the root (used by the self-test
        # which writes a planted log at tmp_path / "llm_calls.jsonl").
        log_paths.extend(root.glob("*.jsonl"))
    # Deduplicate: a *.replay.jsonl matches both .glob("*.jsonl") and
    # .glob("*.replay.jsonl") under the same fixtures dir.
    seen: set[Path] = set()
    for log_path in log_paths:
        rp = log_path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        with open(log_path, encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                prompt = (rec.get("request") or {}).get("prompt") or ""
                for frag in fragments:
                    if frag in prompt:
                        offenders.append((frag, f"{log_path}:{i}", prompt[:80]))
    return offenders


def test_no_uxlc_fragment_in_any_prompt():
    """Production gate: scan REPO_ROOT — fail on any UXLC fragment in any prompt."""
    offenders = _scan_for_contamination([REPO_ROOT])
    assert not offenders, (
        "D-05 contamination boundary breached: UXLC fragments found in LLM prompts:\n"
        + "\n".join(
            f"  fragment={f!r} location={loc} prompt_preview={p!r}..." for f, loc, p in offenders
        )
    )


def test_contamination_self_test_finds_planted_fragment(tmp_path):
    """Self-test: invoke the SAME scan function (not an inline copy) against a
    tmp_path tree containing a deliberately-contaminated log. Asserts the
    production scan would have caught it. This guarantees future regressions
    in `_scan_for_contamination` are caught — if someone refactors the scanner
    and breaks fragment detection, this test fails."""
    log = tmp_path / "llm_calls.jsonl"
    with open(log, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "prompt_hash": "x",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "request": {"prompt": "Translate this: שְׁמַ֖ע יִשְׂרָאֵ֑ל"},
                    "response": "...",
                }
            )
            + "\n"
        )
    offenders = _scan_for_contamination([tmp_path])
    assert offenders, (
        "self-test of contamination detector failed: planted UXLC fragment "
        "was NOT detected, meaning the production test would miss real contamination."
    )
    # Sanity: the matched fragment is one of the fixture fragments.
    matched_fragments = {f for f, _loc, _prev in offenders}
    assert matched_fragments & set(_fragments()), (
        f"matched fragments {matched_fragments!r} not in fixture; detector logic regressed"
    )


def test_uxlc_fragments_fixture_has_canonical_shape():
    """Sanity-check the fixture file: fragments list is non-empty + all entries
    are non-empty Hebrew strings. Catches accidental clobbering."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "fragments" in payload, "fixture missing 'fragments' key"
    fragments = payload["fragments"]
    assert isinstance(fragments, list) and fragments, "fragments must be a non-empty list"
    for frag in fragments:
        assert isinstance(frag, str) and frag.strip(), (
            f"fragment must be non-empty string; got {frag!r}"
        )
        # Sanity: each fragment contains at least one Hebrew letter (U+05D0..U+05EA)
        assert any("א" <= ch <= "ת" for ch in frag), (
            f"fragment {frag!r} contains no Hebrew letters; not a UXLC sample"
        )
