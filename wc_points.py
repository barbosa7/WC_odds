"""Scoring rules for the WC prediction game."""

from __future__ import annotations

GROUP_POS_POINTS = {1: 20, 2: 10, 3: 0, 4: 5}
BONUS_GOALS_POINTS = 15


def overall_rank_points(rank: int) -> int:
    """Points from final tournament standing among all 48 teams (1 = champion)."""
    if rank == 1:
        return 90
    if rank == 2:
        return 70
    if rank == 3:
        return 55
    if rank == 4:
        return 40
    if 5 <= rank <= 8:
        return 30
    if 9 <= rank <= 16:
        return 15
    if 17 <= rank <= 32:
        return 5
    if rank == 48:
        return 5
    return 0


def stage_from_rank(rank: int) -> str:
    if rank == 1:
        return "Champion"
    if rank == 2:
        return "Runner-up"
    if rank == 3:
        return "Third place"
    if rank == 4:
        return "Fourth"
    if rank <= 8:
        return "Quarter-finals"
    if rank <= 16:
        return "Round of 16"
    if rank <= 32:
        return "Round of 32"
    if rank == 48:
        return "Group stage (48th)"
    return "Group stage out"


STAGE_ORDER = [
    "Group stage out",
    "Group stage (48th)",
    "Round of 32",
    "Round of 16",
    "Quarter-finals",
    "Fourth",
    "Third place",
    "Runner-up",
    "Champion",
]
