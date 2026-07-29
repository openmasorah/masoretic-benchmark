# License

Open Masorah v0.1 is a multi-component dataset; each component has a distinct
rights status. When you use a component, the terms below govern it. This file is
the authoritative statement of rights for the dataset. (The scorer *code* is
separately licensed — see below.)

## Public Domain

**Consonantal text** (Tier 1, all four folios) — public domain. It is the text
of the Leningrad Codex (ca. 1008 CE); no copyright is claimed by Open Masorah,
and none exists. The sources of the transcription are credited in
[`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md).

## CC0-1.0 (Public Domain Dedication)

**Annotation data** (Tiers 2–4: nikkud, cantillation, and meta-mark positions
and labels) — dedicated to the public domain under
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/). These are factual
observations about the manuscript and may be used without restriction or
attribution obligation.

## CC-BY-4.0 (Attribution Required)

The original scholarly contributions are licensed under
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/):

- the positional-encoding JSON schema;
- the two-annotator adjudication protocol and its metadata;
- the error taxonomy and annotation guidelines;
- the four-folio benchmark compilation (the selection and its integrated structure).

**Required attribution when you use these components:**

> Lamm, B., Ginsberg, Y., Moster, D. Z., & Finkelstein, A. (2026). *Open Masorah v0.1: a 4-tier
> CER benchmark for medieval Tiberian Hebrew.* [URL/DOI]

## Scorer code

The evaluation scorer (`masoretic_eval/`) is licensed under the **Apache License
2.0** — see [`LICENSE`](LICENSE) for the full text.

## Manuscript images

No manuscript images are distributed. The dataset references images by IIIF URL
only. The Leningrad Codex photographs are the work of the West Semitic Research
Project (WSRP), which asserts rights over them; see
[`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md).

## A note on the per-file `license` field

Each ground-truth JSON file carries an embedded `"license": "CC-BY-4.0"` field.
That field describes the file **as a compiled projection — the CC-BY-4.0
compilation layer above**. It does *not* assert any right over the public-domain
consonantal text or the CC0 annotation data contained in the file, which remain
public domain and CC0-1.0 respectively, as stated above. This document is the
authoritative statement of rights.
