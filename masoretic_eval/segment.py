"""UAX #29 grapheme cluster segmentation."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import grapheme


def segment_clusters(text: str) -> Iterator[str]:
    """Yield UAX #29 extended grapheme clusters from `text`.

    Uses the `grapheme` package (pure Python, UAX #29 compliant).
    For Hebrew: base consonant + nikkud + trop + combining marks form one cluster.
    """
    yield from grapheme.graphemes(text)


def cluster_codepoints(cluster: str) -> int:
    """Return the number of codepoints in a single grapheme cluster."""
    return len(cluster)


def cluster_count(text: str) -> int:
    """Total grapheme cluster count in `text`."""
    return sum(1 for _ in segment_clusters(text))


def codepoint_count(clusters: Iterable[str]) -> int:
    """Total codepoint count across clusters (for denominators)."""
    return sum(len(c) for c in clusters)
