"""Standings and tie-breaking.

Order of criteria:
  1. Match wins.
  2. Among the players still tied, a mini-league of only their mutual
     matches: wins, then set difference, then game difference.
     When a criterion splits the tied block, every sub-block that is still tied
     is resolved again from step 2 using only ITS members (so 3-way circular
     ties are handled correctly and stale head-to-head data is never reused).
  3. Overall set difference, overall game difference, sets won.
  4. Alphabetical (deterministic last resort; a coin toss in real life).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass
class StandingRow:
    player: str
    played: int = 0
    wins: int = 0
    losses: int = 0
    sets_won: int = 0
    sets_lost: int = 0
    games_won: int = 0
    games_lost: int = 0
    rank: int = 0

    @property
    def set_diff(self) -> int:
        return self.sets_won - self.sets_lost

    @property
    def game_diff(self) -> int:
        return self.games_won - self.games_lost


def _tally(players: Iterable[str], matches) -> dict[str, StandingRow]:
    rows = {p: StandingRow(p) for p in players}
    for m in matches:
        if not m.is_played or m.p1 not in rows or m.p2 not in rows:
            continue
        s, (g1, g2) = m.score, m.score.games
        for me, other, sw, sl, gw, gl in ((m.p1, m.p2, *s.sets, g1, g2),
                                          (m.p2, m.p1, s.sets[1], s.sets[0], g2, g1)):
            r = rows[me]
            r.played += 1
            r.sets_won += sw; r.sets_lost += sl
            r.games_won += gw; r.games_lost += gl
            if m.winner == me:
                r.wins += 1
            else:
                r.losses += 1
    return rows


def _split(block: list[str], key: Callable[[str], tuple]) -> list[list[str]]:
    ordered = sorted(block, key=key, reverse=True)
    out: list[list[str]] = []
    for p in ordered:
        if out and key(out[-1][0]) == key(p):
            out[-1].append(p)
        else:
            out.append([p])
    return out


def _resolve(block: list[str], matches, overall: dict[str, StandingRow]) -> list[str]:
    if len(block) == 1:
        return block
    mini = _tally(block, matches)
    for key in (lambda p: (mini[p].wins,),
                lambda p: (mini[p].set_diff,),
                lambda p: (mini[p].game_diff,)):
        parts = _split(block, key)
        if len(parts) > 1:
            return [p for part in parts for p in _resolve(part, matches, overall)]
    # head-to-head can't separate them: fall back to overall numbers
    return sorted(block, key=lambda p: (-overall[p].set_diff, -overall[p].game_diff,
                                        -overall[p].sets_won, p.lower()))


def compute_standings(players: list[str], matches) -> list[StandingRow]:
    overall = _tally(players, matches)
    order: list[str] = []
    for block in _split(list(players), lambda p: (overall[p].wins,)):
        order.extend(_resolve(block, matches, overall))
    rows = [overall[p] for p in order]
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows
