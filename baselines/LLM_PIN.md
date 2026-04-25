# LLM Pin Log

Append-only. Every change to BL-01's LLM source set or model versions
writes a new row here with date + reason (D-09 / Phase 2 D-09 carry-forward).
Newest first.

| Date       | Claude model     | Anthropic SDK | Gemini model      | google-genai SDK | Reason                                                                                                              |
|------------|------------------|---------------|-------------------|------------------|---------------------------------------------------------------------------------------------------------------------|
| 2026-04-25 | claude-opus-4-7  | 0.97.0        | gemini-2.5-pro    | 1.73.1           | Initial pin (Phase 3 BL-01 launch). Per A-2: AbbyyFR dropped; two-source vision-only best-of-two.                   |

## Notes

- **Pin formula**: no derived hash here — the replay log (D-10) IS the reproducibility
  contract. `run_meta.pins.llm_pin_md_hash` carries the sha256 of THIS file's bytes,
  so any uncommitted edit to LLM_PIN.md changes the hash and surfaces in the next run.
- **Determinism**: `temperature=0`, `seed=0` set for both models. Anthropic doesn't
  support seed; Gemini's seed is best-effort and known non-deterministic on gemini-2.5-pro.
  The replay log is the contract; provider-side non-determinism is documented in the
  BL-01 docstring + paper methodology delta (`paper/methodology_delta_BL-01_AbbyyFR_drop.md`
  in baalshem).
- **Tie-break**: alphabetical, Claude < Gemini, so Claude wins ties. WHOLE-LINE WINNER —
  NO tier-mixing across sources within a line (D-07). Disclosed explicitly in paper.
- **AbbyyFR (dropped)**: Engine SDK contamination risk (Hebrew Bible mode trained on
  unknown corpus) + Cloud SDK reproducibility profile (rotating endpoint, no version
  header, same DICTA-style non-reproducible signature) — both fail the paper-defensible
  bar. Reframed as LLM-best-of-two per Phase 3 Adjudication A-2.
- **Cost cap**: $5/folio + $25/run (configured in `llm_vision.config.yaml`). Provider
  price changes = re-pin event in this file + the YAML, captured into the next run's
  `run_meta.budget.rate_table_snapshot`.
- **API keys**: read via `os.environ["ANTHROPIC_API_KEY"]` / `os.environ["GOOGLE_API_KEY"]`
  with NO `.get()` fallback (Phase 1 B-4 carry-forward). Missing env var -> KeyError ->
  non-zero exit; this is intentional, not a bug.
