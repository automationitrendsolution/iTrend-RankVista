"""Rank-to-visual mapping for the ranking matrix.
Tones are resolved server-side so each cell carries a small stable CSS class."""

from __future__ import annotations

from dataclasses import dataclass

from apps.common.constants import (
    RANK_CHECKING,
    RANK_DISTRIBUTION_BUCKETS,
    RANK_NOT_RANKED,
)

# Ten discrete steps keep the gradient readable and the CSS bounded.
RANK_TONE_STOPS = (
    (3, "r1"),
    (5, "r2"),
    (8, "r3"),
    (10, "r4"),
    (15, "r5"),
    (20, "r6"),
    (30, "r7"),
    (50, "r8"),
    (100, "r9"),
)
RANK_TONE_WORST = "r10"


@dataclass(slots=True, frozen=True)
class RankCell:
    """Everything a single matrix cell needs to render."""

    value: int | None
    tone: str
    label: str
    title: str
    is_amazon_choice: bool = False

    @property
    def css(self) -> str:
        classes = f"rv-cell rv-cell--{self.tone}"
        if self.is_amazon_choice:
            classes += " rv-cell--choice"
        return classes


def rank_tone(rank: int | None) -> str:
    """Map a rank value to a heat tone token.
    None = not tracked, RANK_NOT_RANKED = tracked but absent, RANK_CHECKING = in flight."""
    if rank is None:
        return "untracked"
    if rank == RANK_CHECKING:
        return "checking"
    if rank == RANK_NOT_RANKED or rank <= 0:
        return "unranked"
    for ceiling, tone in RANK_TONE_STOPS:
        if rank <= ceiling:
            return tone
    return RANK_TONE_WORST


def build_cell(
    rank: int | None,
    *,
    is_amazon_choice: bool = False,
    date_label: str = "",
) -> RankCell:
    tone = rank_tone(rank)
    if tone == "untracked":
        label, title = "", f"Not tracked{f' on {date_label}' if date_label else ''}"
    elif tone == "checking":
        label, title = "⋯", "Check in progress"
    elif tone == "unranked":
        label, title = "-", f"Not ranked{f' on {date_label}' if date_label else ''}"
    else:
        label = str(rank)
        title = f"Rank {rank}{f' on {date_label}' if date_label else ''}"
        if is_amazon_choice:
            title += " - Amazon's Choice"
    return RankCell(
        value=rank if isinstance(rank, int) and rank > 0 else None,
        tone=tone,
        label=label,
        title=title,
        is_amazon_choice=is_amazon_choice and tone not in {"untracked", "unranked", "checking"},
    )


def distribution_bucket(rank: int | None) -> str | None:
    """Return the distribution bucket key for a positive rank, else None."""
    if rank is None or rank <= 0:
        return None
    for bucket in RANK_DISTRIBUTION_BUCKETS:
        if bucket["min"] <= rank <= bucket["max"]:
            return bucket["key"]
    return RANK_DISTRIBUTION_BUCKETS[-1]["key"]


def legend() -> list[dict[str, str]]:
    """Legend entries rendered beneath the matrix."""
    return [
        {"tone": "unranked", "label": "Not Ranked", "hint": "Tracked, outside search results"},
        {"tone": "untracked", "label": "Not Tracked", "hint": "No tracking on this date"},
        {"tone": "choice", "label": "Amazon's Choice", "hint": "Badge held on this date"},
        {"tone": "checking", "label": "Checking", "hint": "Rank check in progress"},
    ]
