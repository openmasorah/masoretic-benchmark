# Release sign-off

Every `benchmark-v*` tag requires an entry here for that exact version, plus a
`### Governance` subsection in `CHANGELOG.md` under the same version's heading.
Both are enforced by `scripts/check_release_signoff.py`, which the release-tag
workflow runs before anything is published.

**Why this file exists.** This project's decision model is that the maintainer
is the sole decision authority and collaborators are consultants, never approval
gates. The previous release gate required an approving review from a named
scholarly reviewer, which contradicted that model — and went permanently red
when the project did what it had decided to do. The requirement now sits where
the authority actually is, with a public disclosure attached so it cannot be
satisfied quietly.

**Scholarly review is advisory.** When a review exists it is recorded, and the
release-tag workflow logs it. It is never required, and its absence never blocks
a tag. What *is* required is saying so in public, in the CHANGELOG, for the
version being tagged.

## What an entry must contain

| Field | Meaning |
|---|---|
| **Version** | The exact tag, e.g. `benchmark-v0.1.1`. An entry for another version authorizes nothing. |
| **Signed off** | Date the authorization was given. |
| **Authorized by** | The person exercising decision authority. |
| **Authorization** | *How* that authorization was given, specifically enough to audit. |

**On provenance, stated plainly.** Every commit in this repository is made
through the same local git identity, so git authorship does **not** establish
who wrote an entry here. That is why the `Authorization` field is mandatory: it
records how the decision reached the tree, so a reader can evaluate the claim
instead of inferring it from a signature that does not exist. The stronger form,
for a future release, is the maintainer committing — ideally GPG-signing — the
entry directly. Until then, an entry is a recorded claim of authorization, not
cryptographic proof of it, and this file does not pretend otherwise.

---

<!-- Entries below, newest first. -->
