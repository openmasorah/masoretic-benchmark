"""`split_chunks` handles pass-through tokens and `<DR>` differently. Pin both.

The docstring used to say, unqualified, that "editor tokens are replaced with
spaces." `<DR>` is an editor token by shape and is *not* replaced — it carries a
tier-4 double-*rafe* record and has to survive into the chunk for the extractor
to consume it. That sentence is where the `<DR>` incident started, and it was
later quoted back verbatim by two external reviewers who never ran the function.

A comment cannot be tested, so the behaviour it describes is tested instead:
whichever of the two a future reader trusts, they now agree.
"""

from __future__ import annotations

import pytest

from masoretic_eval.iaa.parse import (
    DOUBLE_RAFE_TOKEN,
    PASSTHRU_TAGS,
    SOF_PASUQ,
    split_chunks,
)


@pytest.mark.parametrize("tag", PASSTHRU_TAGS)
def test_passthrough_tokens_are_replaced_with_spaces(tag: str) -> None:
    """They must not survive, and must not glue two verses together."""
    chunks = split_chunks(f"אב{tag}גד{SOF_PASUQ}הו{SOF_PASUQ}")

    assert tag not in "".join(chunks)
    assert chunks == ["אב גד", "הו"]


def test_the_double_rafe_token_SURVIVES_chunking() -> None:
    """The exception the old docstring denied.

    If `<DR>` were replaced here, every double-*rafe* would be silently dropped
    before the tier-4 extractor ever saw it -- annotator B's marks vanishing
    with nothing failing.
    """
    chunks = split_chunks(f"אב{DOUBLE_RAFE_TOKEN}גד{SOF_PASUQ}")

    assert chunks == [f"אב{DOUBLE_RAFE_TOKEN}גד"]
    assert DOUBLE_RAFE_TOKEN in chunks[0]


def test_a_passthrough_token_at_a_verse_boundary_does_not_fuse_verses() -> None:
    """The stated reason the substitution is a space and not the empty string."""
    chunks = split_chunks(f"אב{SOF_PASUQ}{PASSTHRU_TAGS[0]}גד{SOF_PASUQ}")

    assert len(chunks) == 2, chunks
