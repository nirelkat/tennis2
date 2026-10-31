"""Domain models: Match, Group, Knockout, Tournament."""
from __future__ import annotations

import string
from dataclasses import dataclass, field

from .ranking import StandingRow, compute_standings
from .scheduling import round_robin
from .scoring import MatchFormat, Score, parse_score


class TournamentError(Exception):
    pass


@dataclass
class Match:
    id: str
    p1: str | None
    p2: str | None
    round: int = 0
    score: Score | None = None

    @property
    def is_ready(self) -> bool:
        return self.p1 is not None and self.p2 is not None

    @property
    def is_played(self) -> bool:
        return self.score is not None

    @property
    def winner(self) -> str | None:
        if not self.score:
            return None
        return self.p1 if self.score.p1_won else self.p2

    @property
    def loser(self) -> str | None:
        if not self.score:
            return None
        return self.p2 if self.score.p1_won else self.p1

    def to_dict(self) -> dict:
        return {"id": self.id, "p1": self.p1, "p2": self.p2, "round": self.round,
                "score": self.score.to_dict() if self.score else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Match":
        sc = d.get("score")
        return cls(d["id"], d["p1"], d["p2"], d.get("round", 0),
                   Score.from_dict(sc) if sc else None)


@dataclass
class Group:
    name: str
    players: list[str]
    matches: list[Match] = field(default_factory=list)
    resting: dict[int, list[str]] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, players: list[str], prefix: str) -> "Group":
        g = cls(name, list(players))
        for rnd in round_robin(len(players)):
            for k, (a, b) in enumerate(rnd.pairs, 1):
                g.matches.append(Match(f"{prefix}R{rnd.number}M{k}", players[a], players[b], rnd.number))
            g.resting[rnd.number] = [players[i] for i in rnd.resting]
        return g

    @property
    def rounds(self) -> list[int]:
        return sorted({m.round for m in self.matches})

    def matches_in_round(self, r: int) -> list[Match]:
        return [m for m in self.matches if m.round == r]

    @property
    def is_complete(self) -> bool:
        return all(m.is_played for m in self.matches)

    def standings(self) -> list[StandingRow]:
        return compute_standings(self.players, self.matches)

    def to_dict(self) -> dict:
        return {"name": self.name, "players": self.players,
                "matches": [m.to_dict() for m in self.matches],
                "resting": {str(k): v for k, v in self.resting.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Group":
        return cls(d["name"], d["players"], [Match.from_dict(m) for m in d["matches"]],
                   {int(k): v for k, v in d.get("resting", {}).items()})


@dataclass
class Knockout:
    """Four-player bracket: SF1, SF2 -> Final and 3rd-place match."""
    matches: dict[str, Match]

    LABELS = {"SF1": "Semi-Final 1", "SF2": "Semi-Final 2",
              "3P": "3rd Place Match", "F": "Grand Final"}

    @classmethod
    def create(cls, seeds: list[tuple[str, str]]) -> "Knockout":
        (a, b), (c, d) = seeds
        return cls({"SF1": Match("SF1", a, b), "SF2": Match("SF2", c, d),
                    "3P": Match("3P", None, None), "F": Match("F", None, None)})

    def refresh(self) -> None:
        """Propagate semi-final results; drop results whose participants changed."""
        sf1, sf2 = self.matches["SF1"], self.matches["SF2"]
        for mid, attr in (("F", "winner"), ("3P", "loser")):
            m = self.matches[mid]
            new = (getattr(sf1, attr), getattr(sf2, attr))
            if (m.p1, m.p2) != new:
                m.p1, m.p2, m.score = *new, None

    @property
    def podium(self) -> tuple[str, str, str] | None:
        f, t = self.matches["F"], self.matches["3P"]
        if f.is_played and t.is_played:
            return f.winner, f.loser, t.winner
        return None

    def to_dict(self) -> dict:
        return {k: m.to_dict() for k, m in self.matches.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "Knockout":
        return cls({k: Match.from_dict(m) for k, m in d.items()})


@dataclass
class Tournament:
    name: str
    fmt: MatchFormat
    groups: list[Group]
    knockout: Knockout | None = None

    MIN_GROUP, MAX_GROUP = 3, 8

    @classmethod
    def create(cls, name: str, groups: dict[str, list[str]], fmt: MatchFormat | None = None):
        if len(groups) not in (1, 2, 4):
            raise TournamentError("Use 1, 2 or 4 groups (so exactly 4 players reach the playoffs)")
        seen: set[str] = set()
        built = []
        for i, (gname, players) in enumerate(groups.items()):
            players = [p.strip() for p in players if p.strip()]
            if not gname.strip():
                raise TournamentError("Every group needs a name")
            if not cls.MIN_GROUP <= len(players) <= cls.MAX_GROUP:
                raise TournamentError(f"{gname}: groups need {cls.MIN_GROUP}-{cls.MAX_GROUP} players")
            dupes = {p for p in players if p.lower() in seen or players.count(p) > 1}
            if dupes:
                raise TournamentError(f"Duplicate player name(s): {', '.join(sorted(dupes))}")
            seen.update(p.lower() for p in players)
            built.append(Group.create(gname.strip(), players, string.ascii_uppercase[i]))
        return cls(name or "Tournament", fmt or MatchFormat(), built)

    # ---- lookups / commands -------------------------------------------------
    def all_matches(self) -> list[Match]:
        ms = [m for g in self.groups for m in g.matches]
        if self.knockout:
            ms += list(self.knockout.matches.values())
        return ms

    def find_match(self, match_id: str) -> Match:
        for m in self.all_matches():
            if m.id == match_id:
                return m
        raise KeyError(match_id)

    def record_score(self, match_id: str, text: str) -> Match:
        """Validate and store a score. Empty text clears the result."""
        m = self.find_match(match_id)
        if not m.is_ready:
            raise TournamentError("Players for this match are not known yet")
        if self.knockout and match_id not in self.knockout.matches:
            raise TournamentError("Group stage is locked once playoffs start")
        m.score = parse_score(text, self.fmt) if text.strip() else None
        if self.knockout:
            self.knockout.refresh()
        return m

    @property
    def group_stage_complete(self) -> bool:
        return all(g.is_complete for g in self.groups)

    def playoff_seeds(self) -> list[tuple[str, str]]:
        st = [[r.player for r in g.standings()] for g in self.groups]
        if len(st) == 1:
            s = st[0]
            return [(s[0], s[3]), (s[1], s[2])]
        if len(st) == 2:
            a, b = st
            return [(a[0], b[1]), (b[0], a[1])]
        return [(st[0][0], st[3][0]), (st[1][0], st[2][0])]

    def start_playoffs(self) -> Knockout:
        if not self.group_stage_complete:
            raise TournamentError("Finish all group matches first")
        if self.knockout is None:
            self.knockout = Knockout.create(self.playoff_seeds())
        return self.knockout

    def reopen_group_stage(self) -> None:
        self.knockout = None

    # ---- serialization ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {"version": 1, "name": self.name, "format": self.fmt.to_dict(),
                "groups": [g.to_dict() for g in self.groups],
                "knockout": self.knockout.to_dict() if self.knockout else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Tournament":
        ko = d.get("knockout")
        return cls(d["name"], MatchFormat.from_dict(d["format"]),
                   [Group.from_dict(g) for g in d["groups"]],
                   Knockout.from_dict(ko) if ko else None)
