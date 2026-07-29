# UXLC Pin Log

Append-only. Pins the UXLC (Unicode/XML Leningrad Codex) source used to
regenerate the tier-4 UXLC-frame IAA figures. Every change writes a new row here
with date + reason. Newest first.

| Date | Source | Version | File | Size | sha256 | Reason |
|---|---|---|---|---|---|---|
| 2026-07-29 | https://tanach.us | UXLC 2.5 | `Deuteronomy.xml` | 518,374 bytes (~506 KiB) | `55fd384d757453f1b8f6672ea75d9ef58c015a0093c9eee92905fd1f70e9ce07` | Initial pin (v0.1.1 reproducibility close-out). |

- 2026-07-29 — sha256 verified against the local cache at
  `baselines/tests/fixtures/_uxlc_cache/Deuteronomy.xml`; matches this row.

## What depends on this pin

Only the **tier-4 UXLC-frame** figures (F1 / Krippendorff α measured against the
UXLC 2.5 projection) are regenerated from this file, via
`scripts/regenerate_paper_iaa_results.py`. The published tier-1/2/3 CER figures do
**not** depend on it — they recompute from the three committed projection JSONs
alone (see `iaa_report.json` `_note` and the CHANGELOG).

## Fetch + verify

The file is a direct download from tanach.us, cached at
`baselines/tests/fixtures/_uxlc_cache/Deuteronomy.xml` (gitignored; never
committed). To reproduce and verify against this pin:

```bash
curl -sSL https://tanach.us/Books/Deuteronomy.xml \
  -o baselines/tests/fixtures/_uxlc_cache/Deuteronomy.xml
shasum -a 256 baselines/tests/fixtures/_uxlc_cache/Deuteronomy.xml
# expected: 55fd384d757453f1b8f6672ea75d9ef58c015a0093c9eee92905fd1f70e9ce07
```

A mismatch means either the local fetch drifted (UXLC published a new revision) or
the pin is stale — stop and reconcile before regenerating any figure; never
silently re-pin.

## Notes

- **Version distinction**: `UXLC 2.5` is the tanach.us edition label. tanach.us
  does not attach a content hash to its downloads, so this file's sha256 is the
  reproducibility anchor.
- **Append-only**: a new source revision writes a NEW row above; historical rows
  are never edited. A new row implies re-verifying every figure that depends on
  the pin.
