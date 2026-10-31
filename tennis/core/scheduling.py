"""Round-robin scheduling for any group size (circle / polygon method)."""
from __future__ import annotations

from dataclasses import dataclass

BYE = None


@dataclass
class Round:
    number: int
    pairs: list[tuple[int, int]]   # indices into the player list
    resting: list[int]


def round_robin(n: int) -> list[Round]:
    """Berger-style schedule: n-1 rounds (n even) or n rounds with one bye (n odd)."""
    if n < 2:
        raise ValueError("A group needs at least 2 players")
    slots: list[int | None] = list(range(n)) + ([BYE] if n % 2 else [])
    m = len(slots)
    rounds = []
    for r in range(m - 1):
        pairs, resting = [], []
        for i in range(m // 2):
            a, b = slots[i], slots[m - 1 - i]
            if a is BYE or b is BYE:
                resting.append(a if b is BYE else b)
            else:
                # alternate orientation so the fixed player isn't always "home"
                pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(Round(r + 1, pairs, resting))
        slots = [slots[0], slots[-1]] + slots[1:-1]   # rotate all but the first
    return rounds
