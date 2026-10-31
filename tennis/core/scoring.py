"""Match formats and score validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class ScoreError(ValueError):
    """Raised when a score is not a legal tennis result."""


@dataclass(frozen=True)
class MatchFormat:
    best_of: int = 3                     # 3 or 5
    track_games: bool = True             # "6-4 3-6 7-5" vs plain sets "2-1"
    final_set_super_tiebreak: bool = False  # deciding set played as 10-point TB

    def __post_init__(self):
        if self.best_of not in (1, 3, 5):
            raise ValueError("best_of must be 1, 3 or 5")

    @property
    def sets_to_win(self) -> int:
        return self.best_of // 2 + 1

    def to_dict(self) -> dict:
        return {"best_of": self.best_of, "track_games": self.track_games,
                "final_set_super_tiebreak": self.final_set_super_tiebreak}

    @classmethod
    def from_dict(cls, d: dict) -> "MatchFormat":
        return cls(**d)


@dataclass(frozen=True)
class Score:
    """Score from player 1's perspective."""
    sets: tuple[int, int]
    set_scores: tuple[tuple[int, int], ...] | None = field(default=None)

    @property
    def games(self) -> tuple[int, int]:
        if not self.set_scores:
            return (0, 0)
        return (sum(a for a, _ in self.set_scores), sum(b for _, b in self.set_scores))

    @property
    def p1_won(self) -> bool:
        return self.sets[0] > self.sets[1]

    def __str__(self) -> str:
        if self.set_scores:
            return " ".join(f"{a}-{b}" for a, b in self.set_scores)
        return f"{self.sets[0]}-{self.sets[1]}"

    def to_dict(self) -> dict:
        return {"sets": list(self.sets),
                "set_scores": [list(s) for s in self.set_scores] if self.set_scores else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Score":
        ss = d.get("set_scores")
        return cls(tuple(d["sets"]), tuple(tuple(s) for s in ss) if ss else None)


def _valid_regular_set(a: int, b: int) -> bool:
    hi, lo = max(a, b), min(a, b)
    return (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))


def _valid_super_tiebreak(a: int, b: int) -> bool:
    hi, lo = max(a, b), min(a, b)
    return hi >= 10 and hi - lo >= 2 and (hi == 10 or hi - lo == 2)


_PAIR = re.compile(r"(\d+)\s*[-:/]\s*(\d+)")


def parse_score(text: str, fmt: MatchFormat) -> Score:
    """Parse and validate user input such as '6-4 3-6 7-6' or (sets-only) '2-1'."""
    pairs = [(int(a), int(b)) for a, b in _PAIR.findall(text or "")]
    leftover = _PAIR.sub("", text or "").replace(",", " ").strip()
    if not pairs or leftover:
        raise ScoreError("Use the form 6-4 3-6 7-5" if fmt.track_games else "Use the form 2-1")

    need = fmt.sets_to_win
    if not fmt.track_games:
        if len(pairs) != 1:
            raise ScoreError("Enter the sets only, e.g. 2-1")
        s1, s2 = pairs[0]
        if max(s1, s2) != need or min(s1, s2) >= need:
            raise ScoreError(f"Best of {fmt.best_of}: winner needs exactly {need} sets "
                             f"and the loser fewer than {need}")
        return Score((s1, s2))

    won = [0, 0]
    for i, (a, b) in enumerate(pairs, 1):
        if max(won) == need:
            raise ScoreError(f"Match was already decided before set {i}")
        deciding = won[0] == won[1] == need - 1
        if deciding and fmt.final_set_super_tiebreak:
            ok = _valid_super_tiebreak(a, b)
        else:
            ok = _valid_regular_set(a, b)
        if not ok:
            raise ScoreError(f"Set {i} ({a}-{b}) is not a valid set score")
        won[0 if a > b else 1] += 1
    if max(won) != need:
        raise ScoreError(f"Incomplete match: someone must win {need} sets")
    return Score((won[0], won[1]), tuple(pairs))
