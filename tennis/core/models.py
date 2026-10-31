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
    fmt: MatchFormat = field(default_factory=MatchFormat)

    @classmethod
    def create(cls, name: str, players: list[str], prefix: str,
               fmt: MatchFormat | None = None) -> "Group":
        fmt = fmt or MatchFormat()
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
                "format": self.fmt.to_dict(),
                "matches": [m.to_dict() for m in self.matches],
                "resting": {str(k): v for k, v in self.resting.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Group":
        return cls(d["name"], d["players"], [Match.from_dict(m) for m in d["matches"]],
                   {int(k): v for k, v in d.get("resting", {}).items()},
                   MatchFormat.from_dict(d["format"]))


ROUND_NAMES = {16: "Round of 16", 8: "Quarter-Finals", 4: "Semi-Finals", 2: "Final"}
_ROUND_PREFIX = {16: "R16-", 8: "QF", 4: "SF"}
BRACKET_SIZES = (2, 4, 8, 16)


@dataclass
class Knockout:
    """Single-elimination bracket for 2, 4, 8 or 16 players.

    Match ids: R16-1..8, QF1..4, SF1..2, F, and 3P (3rd place). Match j of a
    round is fed by the winners of matches 2j-1 and 2j of the previous round;
    with semi-finals, the 3rd-place match is played by the semi-final losers.

    Single group, Final only (size 2):
      * 4-5 players: the 3rd-place match is seeded directly (3rd v 4th).
      * 3 players: no 3rd-place match; `bronze` holds the group's 3rd-placed
        player, who takes 3rd place on the podium."""
    size: int
    matches: dict[str, Match]
    bronze: str | None = None

    @staticmethod
    def round_ids(size: int) -> list[list[str]]:
        """Match ids per round, first round first (the 3rd-place match excluded)."""
        out, n = [], size
        while n >= 2:
            k = n // 2
            out.append(["F"] if n == 2 else [f"{_ROUND_PREFIX[n]}{j}" for j in range(1, k + 1)])
            n //= 2
        return out

    @classmethod
    def create(cls, pairs: list[tuple[str, str]],
               third_place: tuple[str, str] | None = None,
               bronze: str | None = None) -> "Knockout":
        """pairs: first-round pairs in bracket order. third_place / bronze are
        only used for a Final-only bracket (see class docstring)."""
        size = 2 * len(pairs)
        if size not in BRACKET_SIZES:
            raise TournamentError(f"Unsupported bracket size {size}")
        matches: dict[str, Match] = {}
        for r, ids in enumerate(cls.round_ids(size), 1):
            for j, mid in enumerate(ids):
                p1, p2 = pairs[j] if r == 1 else (None, None)
                matches[mid] = Match(mid, p1, p2, r)
        if size >= 4:
            matches["3P"] = Match("3P", None, None, matches["F"].round)
        elif third_place:
            matches["3P"] = Match("3P", *third_place, matches["F"].round)
        return cls(size, matches, None if third_place else bronze)

    @property
    def participants(self) -> list[str]:
        """Everyone who starts the playoffs (first round + a seeded 3rd-place match)."""
        first = [self.matches[mid] for mid in self.round_ids(self.size)[0]]
        if self.size == 2 and "3P" in self.matches:
            first.append(self.matches["3P"])
        return [p for m in first for p in (m.p1, m.p2) if p]

    @property
    def rounds(self) -> list[tuple[str, list[str]]]:
        """[(round name, [match ids])], e.g. [("Semi-Finals", ["SF1", "SF2"]), ("Final", ["F"])]."""
        return [(ROUND_NAMES[len(ids) * 2], ids) for ids in self.round_ids(self.size)]

    @staticmethod
    def label(mid: str) -> str:
        if mid == "F":
            return "Final"
        if mid == "3P":
            return "3rd Place Match"
        if mid.startswith("R16-"):
            return f"Round of 16 · Match {mid[4:]}"
        return {"QF": "Quarter-Final ", "SF": "Semi-Final "}[mid[:2]] + mid[2:]

    def refresh(self) -> None:
        """Move winners (and semi-final losers) forward, round by round. A
        result is dropped if the players of that match changed."""
        rounds = self.round_ids(self.size)
        for prev, cur in zip(rounds, rounds[1:]):
            for j, mid in enumerate(cur):
                a, b = self.matches[prev[2 * j]], self.matches[prev[2 * j + 1]]
                self._set_players(self.matches[mid], a.winner, b.winner)
        if "3P" in self.matches and "SF1" in self.matches:   # seeded 3P stays as is
            sf1, sf2 = self.matches["SF1"], self.matches["SF2"]
            self._set_players(self.matches["3P"], sf1.loser, sf2.loser)

    @staticmethod
    def _set_players(m: Match, p1: str | None, p2: str | None) -> None:
        if (m.p1, m.p2) != (p1, p2):
            m.p1, m.p2, m.score = p1, p2, None

    @property
    def is_complete(self) -> bool:
        return all(m.is_played for m in self.matches.values())

    @property
    def podium(self) -> tuple[str, str, str | None] | None:
        """(champion, runner-up, 3rd place). 3rd place is the 3rd-place match
        winner, or the group's 3rd-placed player when there is no such match."""
        if not self.is_complete:
            return None
        f, t = self.matches["F"], self.matches.get("3P")
        return f.winner, f.loser, (t.winner if t else self.bronze)

    def to_dict(self) -> dict:
        return {"size": self.size, "bronze": self.bronze,
                "matches": [m.to_dict() for m in self.matches.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "Knockout":
        return cls(d["size"], {m["id"]: Match.from_dict(m) for m in d["matches"]},
                   d.get("bronze"))


def playoff_pairs(standings: list[list[str]], advance: int) -> list[tuple[str, str]]:
    """First-round playoff pairs from each group's final ranking.

    standings: per group, player names in rank order. advance: players per
    group that qualify. Pairs are listed in bracket order (pairs 1+2 meet in
    the next round, 3+4, ...), arranged so players from the same group are in
    different halves and only meet as late as possible."""
    n = len(standings)
    if n == 1:
        g = standings[0]
        if advance == 4:                         # Semi-Finals: 1v4, 2v3
            return [(g[0], g[3]), (g[1], g[2])]
        return [(g[0], g[1])]                    # Final: 1v2
    A, B = standings[0], standings[1]
    if n == 2 and advance == 2:                  # Semi-Finals
        return [(A[0], B[1]), (B[0], A[1])]
    if n == 2 and advance == 4:                  # Quarter-Finals
        return [(A[0], B[3]), (B[1], A[2]),      # -> SF1
                (B[0], A[3]), (A[1], B[2])]      # -> SF2
    C, D = standings[2], standings[3]
    if advance == 2:                             # Quarter-Finals
        return [(A[0], B[1]), (C[0], D[1]),      # -> SF1
                (B[0], A[1]), (D[0], C[1])]      # -> SF2
    return [(A[0], B[3]), (D[1], C[2]),          # Round of 16, quarter 1
            (C[0], D[3]), (B[1], A[2]),          #              quarter 2
            (B[0], A[3]), (C[1], D[2]),          #              quarter 3
            (D[0], C[3]), (A[1], B[2])]          #              quarter 4


@dataclass
class Tournament:
    name: str
    playoff_fmt: MatchFormat
    groups: list[Group]
    advance: int = 2                     # players per group who reach the playoffs
    knockout: Knockout | None = None

    MIN_GROUP, MAX_GROUP = 3, 5          # as in the original script
    FILE_VERSION = 3

    @staticmethod
    def advance_options(group_sizes: list[int]) -> list[int]:
        """Allowed players-per-group to qualify (2 is always the default).
        Top 4 is only offered when every group has exactly 5 players:
        1 group -> Semi-Finals, 2 groups -> Quarter-Finals, 4 groups -> Round of 16."""
        if group_sizes and all(n == 5 for n in group_sizes):
            return [2, 4]
        return [2]

    @staticmethod
    def bracket_size(n_groups: int, advance: int) -> int:
        return n_groups * advance

    @classmethod
    def create(cls, name: str, groups: dict[str, list[str]],
               group_formats: dict[str, MatchFormat] | None = None,
               playoff_fmt: MatchFormat | None = None, advance: int = 2) -> "Tournament":
        """groups: {group name: [player names]}; group_formats: {group name: format}
        (missing groups use the default MatchFormat()); advance: 2 or 4."""
        group_formats = group_formats or {}
        if len(groups) not in (1, 2, 4):
            raise TournamentError("Use 1, 2 or 4 groups")
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
                                      group_formats.get(gname) or MatchFormat()))
        if advance not in cls.advance_options([len(g.players) for g in built]):
            raise TournamentError("Top 4 per group can only advance when every group "
                                  "has exactly 5 players")
        return cls(name or "Tournament", playoff_fmt or MatchFormat(), built, advance)

    @property
    def qualifiers_per_group(self) -> int:
        return self.advance

    @property
    def bronze_ranks(self) -> list[int]:
        """Group ranks that play for (or receive) 3rd place without reaching the
        Final bracket: single group, Final only -> 3rd v 4th, or 3rd with 3 players."""
        if len(self.groups) == 1 and self.advance == 2:
            return [3, 4] if len(self.groups[0].players) >= 4 else [3]
        return []

    @property
    def playoff_size(self) -> int:
        return self.bracket_size(len(self.groups), self.advance)

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
        return g.fmt if g else self.playoff_fmt

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
        return playoff_pairs(st, self.advance)

    def start_playoffs(self) -> Knockout:
        if not self.group_stage_complete:
            raise TournamentError("Finish all group matches first")
        if self.knockout is None:
            third_place, bronze = None, None
            ranks = self.bronze_ranks
            if ranks:
                order = [r.name for r in self.groups[0].standings()]
                if len(ranks) == 2:
                    third_place = (order[2], order[3])     # 3rd v 4th
                else:
                    bronze = order[2]                      # 3 players: bronze by ranking
            self.knockout = Knockout.create(self.playoff_seeds(), third_place, bronze)
        return self.knockout

    def reopen_group_stage(self) -> None:
        self.knockout = None

    # ---- serialization ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {"version": self.FILE_VERSION, "name": self.name,
                "playoff_format": self.playoff_fmt.to_dict(), "advance": self.advance,
                "groups": [g.to_dict() for g in self.groups],
                "knockout": self.knockout.to_dict() if self.knockout else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Tournament":
        if d.get("version") != cls.FILE_VERSION:
            raise TournamentError("This file was saved by an older version of the app "
                                  "and can't be opened")
        ko = d.get("knockout")
        return cls(d["name"], MatchFormat.from_dict(d["playoff_format"]),
                   [Group.from_dict(g) for g in d["groups"]], int(d.get("advance", 2)),
                   Knockout.from_dict(ko) if ko else None)
