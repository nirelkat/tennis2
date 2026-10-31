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
    fmt: MatchFormat | None = None      # None = use the tournament's format

    @classmethod
    def create(cls, name: str, players: list[str], prefix: str,
               fmt: MatchFormat | None = None) -> "Group":
        g = cls(name, list(players), fmt=fmt)
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

    @property
    def current_round(self) -> int | None:
        """First round that still has a match without a score (None = all done).
        Rounds are played in order, as in the original script: a round's
        scores can only be entered once every earlier round is complete."""
        for r in self.rounds:
            if not all(m.is_played for m in self.matches_in_round(r)):
                return r
        return None

    def round_is_open(self, r: int) -> bool:
        cur = self.current_round
        return cur is None or r <= cur

    def standings(self) -> list[StandingRow]:
        return compute_standings(self.players, self.matches)

    def to_dict(self) -> dict:
        return {"name": self.name, "players": self.players,
                "format": self.fmt.to_dict() if self.fmt else None,
                "matches": [m.to_dict() for m in self.matches],
                "resting": {str(k): v for k, v in self.resting.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Group":
        f = d.get("format")
        return cls(d["name"], d["players"], [Match.from_dict(m) for m in d["matches"]],
                   {int(k): v for k, v in d.get("resting", {}).items()},
                   MatchFormat.from_dict(f) if f else None)


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

    MIN_GROUP, MAX_GROUP = 3, 5          # as in the original script
    FILE_VERSION = 2

    @classmethod
    def create(cls, name: str, groups: dict[str, list[str]], fmt: MatchFormat | None = None,
               group_formats: dict[str, MatchFormat | None] | None = None):
        """groups: {group name: [player names]}.
        fmt: format for the playoffs and every group without its own.
        group_formats: optional {group name: format} overrides."""
        group_formats = group_formats or {}
        if len(groups) not in (1, 2, 4):
            raise TournamentError("Use 1, 2 or 4 groups (so exactly 4 players reach the playoffs)")
        if len(groups) == 1 and len([p for p in next(iter(groups.values())) if p.strip()]) < 4:
            raise TournamentError("With a single group, 4 or 5 players are needed "
                                  "(the top 4 play the semi-finals)")
        seen: set[str] = set()
        built = []
        for i, (gname, players) in enumerate(groups.items()):
            players = [p.strip() for p in players if p.strip()]
            if not gname.strip():
                raise TournamentError("Every group needs a name")
            if not cls.MIN_GROUP <= len(players) <= cls.MAX_GROUP:
                raise TournamentError(f"{gname}: a group needs 3, 4 or 5 players (has {len(players)})")
            dupes = {p for p in players if p.lower() in seen or players.count(p) > 1}
            if dupes:
                raise TournamentError(f"Duplicate player name(s): {', '.join(sorted(dupes))}")
            seen.update(p.lower() for p in players)
            built.append(Group.create(gname.strip(), players, string.ascii_uppercase[i],
                                      group_formats.get(gname)))
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

    def group_of(self, match_id: str) -> Group | None:
        for g in self.groups:
            if any(m.id == match_id for m in g.matches):
                return g
        return None

    def format_for(self, match_id: str) -> MatchFormat:
        g = self.group_of(match_id)
        return g.fmt if g and g.fmt else self.fmt

    def is_editable(self, match_id: str) -> bool:
        m = self.find_match(match_id)
        if not m.is_ready:
            return False
        g = self.group_of(match_id)
        if g is None:
            return True                      # playoff match
        return self.knockout is None and g.round_is_open(m.round)

    def record_score(self, match_id: str, text: str) -> Match:
        """Validate and store a score. Empty text clears the result (to correct
        a mistake); every match still needs a score before the stage can end."""
        m = self.find_match(match_id)
        if not m.is_ready:
            raise TournamentError("Players for this match are not known yet")
        g = self.group_of(match_id)
        if g is not None:
            if self.knockout:
                raise TournamentError("Group stage is locked once playoffs start")
            if not g.round_is_open(m.round):
                raise TournamentError(f"Finish round {g.current_round} of {g.name} first")
        m.score = parse_score(text, self.format_for(match_id)) if text.strip() else None
        if self.knockout:
            self.knockout.refresh()
        return m

    @property
    def group_stage_complete(self) -> bool:
        return all(g.is_complete for g in self.groups)

    def playoff_seeds(self) -> list[tuple[str, str]]:
        st = [[r.name for r in g.standings()] for g in self.groups]
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
        return {"version": self.FILE_VERSION, "name": self.name, "format": self.fmt.to_dict(),
                "groups": [g.to_dict() for g in self.groups],
                "knockout": self.knockout.to_dict() if self.knockout else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Tournament":
        if d.get("version") != cls.FILE_VERSION:
            raise TournamentError("This file was saved by an older version with a different "
                                  "scoring format and can't be opened")
        ko = d.get("knockout")
        return cls(d["name"], MatchFormat.from_dict(d["format"]),
                   [Group.from_dict(g) for g in d["groups"]],
                   Knockout.from_dict(ko) if ko else None)
