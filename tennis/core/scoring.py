"""Single-set match format and score validation.

Every match is ONE set. A score is the number of games each player won,
e.g. "6-4". The rules depend on two settings:

* games_to_win (2, 3 or 6): the target ("first to N").
* tiebreak:
    - off: sudden death. The winner has exactly N games and the loser fewer
      (first to 3 -> 3-0, 3-1, 3-2).
    - on (advantage / deciding game): at (N-1)-(N-1) a player must win by two,
      so (N+1)-(N-1) is a valid result. At N-N one deciding tie-break game is
      played, so (N+1)-N is the closest possible result
      (first to 3 -> 3-0, 3-1, 4-2, 4-3; first to 6 -> 6-0 … 6-4, 7-5, 7-6).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class ScoreError(ValueError):
    """Raised when a score is not a legal result for the match format."""


GAME_TARGETS = (2, 3, 6)


@dataclass(frozen=True)
class MatchFormat:
    games_to_win: int = 6
    tiebreak: bool = True

    def __post_init__(self):
        if self.games_to_win not in GAME_TARGETS:
            raise ValueError(f"games_to_win must be one of {GAME_TARGETS}")

    def valid_results(self) -> list[tuple[int, int]]:
        """Every legal (winner games, loser games) pair, closest score last."""
        n = self.games_to_win
        if not self.tiebreak:
            return [(n, lo) for lo in range(n)]
        return [(n, lo) for lo in range(n - 1)] + [(n + 1, n - 1), (n + 1, n)]

    @property
    def example(self) -> str:
        """A typical valid score for placeholders and hints (6-4, 3-1, 2-0)."""
        n = self.games_to_win
        return f"{n}-{max(n - 2, 0)}"

    def describe(self) -> str:
        return f"First to {self.games_to_win}" + (" · tie-break" if self.tiebreak else "")

    def to_dict(self) -> dict:
        return {"games_to_win": self.games_to_win, "tiebreak": self.tiebreak}

    @classmethod
    def from_dict(cls, d: dict) -> "MatchFormat":
        return cls(int(d["games_to_win"]), bool(d["tiebreak"]))


@dataclass(frozen=True)
class Score:
    """Games won in the single set, from player 1's point of view."""
    p1_games: int
    p2_games: int

    @property
    def games(self) -> tuple[int, int]:
        return (self.p1_games, self.p2_games)

    @property
    def p1_won(self) -> bool:
        return self.p1_games > self.p2_games

    def __str__(self) -> str:
        return f"{self.p1_games}-{self.p2_games}"

    def to_dict(self) -> dict:
        return {"games": [self.p1_games, self.p2_games]}

    @classmethod
    def from_dict(cls, d: dict) -> "Score":
        a, b = d["games"]
        return cls(int(a), int(b))


_SCORE = re.compile(r"^\s*(\d{1,2})\s*[-:/]\s*(\d{1,2})\s*$")


def validate_games(a: int, b: int, fmt: MatchFormat) -> None:
    """Raise ScoreError with a readable reason if a-b is not a legal result."""
    n = fmt.games_to_win
    hi, lo = max(a, b), min(a, b)
    if a == b:
        raise ScoreError("A match can't end level: one player must win")
    if hi < n:
        raise ScoreError(f"Incomplete: a player needs {n} games to win")
    if (hi, lo) in fmt.valid_results():
        return
    if not fmt.tiebreak:
        raise ScoreError(f"First to {n}, no tie-break: the winner has exactly {n} games "
                         f"and the loser fewer (e.g. {n}-{n - 1})")
    if hi == n:   # n-(n-1): play continues at (n-1) all
        raise ScoreError(f"At {n - 1}-{n - 1} a player must win by two: "
                         f"{n + 1}-{n - 1}, or {n + 1}-{n} after the tie-break game")
    if hi == n + 1:
        raise ScoreError(f"The match was already over at {n}-{lo}")
    raise ScoreError(f"Too many games: the most is {n + 1}-{n} (via the tie-break game)")


def parse_score(text: str, fmt: MatchFormat) -> Score:
    """Parse and validate user input such as '6-4' (player 1 first)."""
    m = _SCORE.match(text or "")
    if not m:
        raise ScoreError(f"Enter the games won by each player, e.g. {fmt.example}")
    a, b = int(m.group(1)), int(m.group(2))
    validate_games(a, b, fmt)
    return Score(a, b)
