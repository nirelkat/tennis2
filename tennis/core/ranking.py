"""Standings and tie-breaking: the algorithm from the original script.

`rank_players()` and `get_h2h_winner_and_loser()` follow the flow of the
functions with the same names in `tennis_group_standings.py`:

  1. Bucket players by number of wins (most wins first).
  2. A bucket of 1 player is placed as is.
  3. A bucket of 2 players is ordered by their head-to-head match.
  4. A bucket of 3+ players is sorted by (game difference, games won),
     then ONE pass is made over neighbouring pairs: when two neighbours
     have the same game difference, they are put in head-to-head order.

Changes from the original, none of which alter the ranking logic:
  * Game difference / games won replace set difference / sets won, because a
    match is now a single set and the totals are counted in games.
  * Guards against crashes: if two tied players have not played each other yet
    (standings are shown live while the group is still in progress), there is
    no head-to-head result. The original raised KeyError there. Now a 2-player
    bucket falls back to (game difference, games won), and in a 3+ bucket the
    neighbours keep the order of the sort.
  * When everything is equal, Python's stable sort keeps registration order,
    exactly as in the original.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

HeadToHead = dict[tuple[str, str], tuple[int, int]]


@dataclass
class StandingRow:
    """A player's line in the table (the original `Player` class, in games)."""
    name: str
    played: int = 0
    wins: int = 0
    losses: int = 0
    games_won: int = 0
    games_lost: int = 0
    rank: int = 0

    @property
    def game_diff(self) -> int:
        return self.games_won - self.games_lost

    def __repr__(self) -> str:
        return self.name


def tally(players: Iterable[str], matches) -> tuple[list[StandingRow], HeadToHead]:
    """Count wins/losses/games from played matches and build the head-to-head
    dictionary, keyed (player1, player2) -> (games player1, games player2),
    the same shape `play_rounds()` returned in the original script."""
    rows = {p: StandingRow(p) for p in players}
    head_to_head: HeadToHead = {}
    for m in matches:
        if not m.is_played or m.p1 not in rows or m.p2 not in rows:
            continue
        g1, g2 = m.score.games
        head_to_head[(m.p1, m.p2)] = (g1, g2)
        p1, p2 = rows[m.p1], rows[m.p2]
        p1.played += 1
        p2.played += 1
        if g1 > g2:
            p1.wins += 1
            p2.losses += 1
        else:
            p1.losses += 1
            p2.wins += 1
        p1.games_won += g1
        p2.games_won += g2
        p1.games_lost += g2
        p2.games_lost += g1
    return list(rows.values()), head_to_head


def get_h2h_winner_and_loser(p1: StandingRow, p2: StandingRow,
                             head_to_head: HeadToHead) -> tuple[StandingRow, StandingRow] | None:
    """Return (winner, loser) of the match between p1 and p2.

    Guard: returns None when they have not played each other (yet) or the
    stored score is level, instead of raising KeyError like the original."""
    if (p1.name, p2.name) in head_to_head:
        score1, score2 = head_to_head[(p1.name, p2.name)]
    elif (p2.name, p1.name) in head_to_head:
        score2, score1 = head_to_head[(p2.name, p1.name)]
    else:
        return None
    if score1 == score2:
        return None
    return (p1, p2) if score1 > score2 else (p2, p1)


def _diff_key(p: StandingRow) -> tuple[int, int]:
    return (p.game_diff, p.games_won)


def rank_players(players_group: list[StandingRow], head_to_head: HeadToHead) -> list[StandingRow]:
    """Sort players by wins and break ties (original algorithm, in games)."""
    tied_win_groups_dic: dict[int, list[StandingRow]] = {}
    for player in players_group:
        current_list = tied_win_groups_dic.get(player.wins, [])
        current_list.append(player)
        tied_win_groups_dic[player.wins] = current_list

    ranked_players: list[StandingRow] = []

    for wins in sorted(tied_win_groups_dic.keys(), reverse=True):
        tied_group = tied_win_groups_dic[wins]

        if len(tied_group) == 0:
            continue

        if len(tied_group) == 1:
            ranked_players.append(tied_group[0])

        elif len(tied_group) == 2:
            result = get_h2h_winner_and_loser(tied_group[0], tied_group[1], head_to_head)
            if result is None:  # guard: they haven't met yet
                result = sorted(tied_group, key=_diff_key, reverse=True)
            winner, loser = result
            ranked_players.extend([winner, loser])

        elif len(tied_group) >= 3:
            tied_group.sort(key=_diff_key, reverse=True)

            for i in range(len(tied_group) - 1):
                p1 = tied_group[i]
                p2 = tied_group[i + 1]
                diff1 = p1.games_won - p1.games_lost
                diff2 = p2.games_won - p2.games_lost

                if diff1 == diff2:
                    result = get_h2h_winner_and_loser(p1, p2, head_to_head)
                    if result is not None:  # guard: they haven't met yet
                        winner, loser = result
                        tied_group[i] = winner
                        tied_group[i + 1] = loser

            ranked_players.extend(tied_group)

    return ranked_players


def compute_standings(players: list[str], matches) -> list[StandingRow]:
    """Tally the played matches, rank, and number the rows 1..n."""
    rows, head_to_head = tally(players, matches)
    ranked = rank_players(rows, head_to_head)
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return ranked
