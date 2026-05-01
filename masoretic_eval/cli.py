"""CLI: `masoretic-eval score --gt ... --pred ... --folio-id ... --out ...`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from jsonschema import Draft202012Validator, ValidationError

from masoretic_eval.composite import Scorer
from masoretic_eval.output_schema import serialize
from masoretic_eval.uxlc_loader import MetaMarkRecord

_SCORER_INPUT_SCHEMA_PATH = Path(__file__).parent / "schemas" / "scorer_input.schema.json"
_SCORER_INPUT_VALIDATOR: Draft202012Validator | None = None


def _scorer_input_validator() -> Draft202012Validator:
    global _SCORER_INPUT_VALIDATOR
    if _SCORER_INPUT_VALIDATOR is None:
        schema = json.loads(_SCORER_INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _SCORER_INPUT_VALIDATOR = Draft202012Validator(schema)
    return _SCORER_INPUT_VALIDATOR


def _deserialize_input(path: Path, role: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    try:
        _scorer_input_validator().validate(data)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        suffix = f" at {location}" if location else ""
        raise click.ClickException(
            f"schema validation failed for {role} {path}{suffix}: {exc.message}"
        ) from exc

    # Convert metamarks dicts → MetaMarkRecord dataclass instances.
    meta = data["metamarks"]
    data["metamarks"] = [
        MetaMarkRecord(
            type=m["type"],
            verse_ref=m["verse_ref"],
            ordinal=m["ordinal"],
            codepoints=m.get("codepoints"),
        )
        for m in meta
    ]
    return data


@click.group()
def main() -> None:
    """masoretic-eval: 4-tier CER scorer for medieval Hebrew."""


@main.command()
@click.option("--gt", "gt_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pred", "pred_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--folio-id", required=True, type=str)
@click.option("--gt-version", default="v0.1.0", type=str)
@click.option("--out", "out_path", required=True, type=click.Path(path_type=Path))
@click.option("--nakdimon-disagreement-rate", default=None, type=float)
@click.option("--dicta-disagreement-rate", default=None, type=float)
def score(
    gt_path: Path,
    pred_path: Path,
    folio_id: str,
    gt_version: str,
    out_path: Path,
    nakdimon_disagreement_rate: float | None,
    dicta_disagreement_rate: float | None,
) -> None:
    """Score a prediction against ground truth and write a JSON report."""
    gt = _deserialize_input(gt_path, "--gt")
    pred = _deserialize_input(pred_path, "--pred")
    s = Scorer.from_config("v0.1")
    result = s.score(
        pred=pred,
        ground_truth=gt,
        nakdimon_disagreement_rate=nakdimon_disagreement_rate,
        dicta_disagreement_rate=dicta_disagreement_rate,
    )
    obj = serialize(
        result=result,
        prediction_id=folio_id,
        gt_version=gt_version,
    )
    out_path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"wrote {out_path}")


if __name__ == "__main__":
    main()
