import itertools
import tempfile
import unittest
from pathlib import Path

from tennis.core import (Match, MatchFormat, Score, ScoreError, Tournament, TournamentError,
                         compute_standings, get_h2h_winner_and_loser, parse_score,
                         round_robin, tally)
from tennis.core import persistence


# --------------------------------------------------------------------------- #
# Scoring: one set per match, first to 2 / 3 / 6, tie-break on or off
# --------------------------------------------------------------------------- #
VALID = {
    (2, False): ["2-0", "2-1", "0-2", "1-2"],
    (2, True):  ["2-0", "3-1", "3-2", "1-3", "2-3"],
    (3, False): ["3-0", "3-1", "3-2", "2-3"],
    (3, True):  ["3-0", "3-1", "4-2", "4-3", "3-4"],
    (6, False): ["6-0", "6-4", "6-5", "5-6"],
    (6, True):  ["6-0", "6-4", "7-5", "7-6", "6-7"],
}
INVALID = {
    (2, False): ["2-2", "1-0", "3-1", "3-2", "0-0"],
    (2, True):  ["2-1", "1-0", "3-0", "4-2", "2-2", "4-3"],
    (3, False): ["3-3", "2-1", "4-2", "4-3"],
    (3, True):  ["3-2", "2-1", "4-1", "5-3", "4-4", "5-4"],
    (6, False): ["6-6", "5-4", "7-5", "7-6"],
    (6, True):  ["6-5", "5-3", "7-4", "8-6", "6-6", "8-7"],
}


class ScoringTests(unittest.TestCase):
    def test_valid_scores(self):
        for (n, tb), scores in VALID.items():
            for txt in scores:
                with self.subTest(games_to_win=n, tiebreak=tb, score=txt):
                    s = parse_score(txt, MatchFormat(n, tb))
                    a, b = map(int, txt.split("-"))
                    self.assertEqual(s.games, (a, b))
                    self.assertEqual(s.p1_won, a > b)

    def test_invalid_scores(self):
        for (n, tb), scores in INVALID.items():
            for txt in scores:
                with self.subTest(games_to_win=n, tiebreak=tb, score=txt), \
                        self.assertRaises(ScoreError):
                    parse_score(txt, MatchFormat(n, tb))

    def test_malformed_input(self):
        for txt in ("", "   ", "abc", "6", "6-4 6-3", "6-4-1", "-6-4"):
            with self.subTest(txt=txt), self.assertRaises(ScoreError):
                parse_score(txt, MatchFormat(6, True))
        self.assertEqual(parse_score(" 6 : 4 ", MatchFormat(6, True)).games, (6, 4))

    def test_valid_results_table(self):
        self.assertEqual(MatchFormat(6, True).valid_results(),
                         [(6, 0), (6, 1), (6, 2), (6, 3), (6, 4), (7, 5), (7, 6)])
        self.assertEqual(MatchFormat(3, True).valid_results(), [(3, 0), (3, 1), (4, 2), (4, 3)])
        self.assertEqual(MatchFormat(2, True).valid_results(), [(2, 0), (3, 1), (3, 2)])
        self.assertEqual(MatchFormat(3, False).valid_results(), [(3, 0), (3, 1), (3, 2)])

    def test_error_messages_explain_the_rule(self):
        with self.assertRaisesRegex(ScoreError, "win by two"):
            parse_score("3-2", MatchFormat(3, True))
        with self.assertRaisesRegex(ScoreError, "no tie-break"):
            parse_score("4-3", MatchFormat(3, False))
        with self.assertRaisesRegex(ScoreError, "already over"):
            parse_score("7-4", MatchFormat(6, True))

    def test_only_2_3_6_allowed(self):
        for n in (1, 4, 5, 7):
            with self.subTest(n=n), self.assertRaises(ValueError):
                MatchFormat(n)


class ScheduleTests(unittest.TestCase):
    def test_every_pair_once(self):
        for n in (3, 4, 5):
            rounds = round_robin(n)
            pairs = [frozenset(p) for r in rounds for p in r.pairs]
            self.assertEqual(len(pairs), n * (n - 1) // 2)
            self.assertEqual(set(pairs), {frozenset(c) for c in itertools.combinations(range(n), 2)})
            for r in rounds:  # nobody plays twice in a round
                flat = [x for p in r.pairs for x in p] + r.resting
                self.assertEqual(sorted(flat), list(range(n)))


# --------------------------------------------------------------------------- #
# Standings and the original tie-breaking algorithm
# --------------------------------------------------------------------------- #
def matches(*results):
    """results: ("A", "B", 6, 4) means A beat B 6-4 (A listed as player 1)."""
    return [Match(f"M{i}", a, b, 1, Score(ga, gb)) for i, (a, b, ga, gb) in enumerate(results)]


def order(players, ms):
    return [r.name for r in compute_standings(players, ms)]


class StandingsTests(unittest.TestCase):
    def test_game_totals(self):
        rows = {r.name: r for r in compute_standings(
            ["A", "B", "C"], matches(("A", "B", 6, 4), ("A", "C", 7, 5), ("C", "B", 6, 2)))}
        a, b, c = rows["A"], rows["B"], rows["C"]
        self.assertEqual((a.played, a.wins, a.losses, a.games_won, a.games_lost, a.game_diff),
                         (2, 2, 0, 13, 9, 4))
        self.assertEqual((c.wins, c.games_won, c.games_lost, c.game_diff), (1, 11, 9, 2))
        self.assertEqual((b.wins, b.losses, b.games_won, b.games_lost, b.game_diff), (0, 2, 6, 12, -6))
        self.assertEqual([a.rank, c.rank, b.rank], [1, 2, 3])

    def test_correcting_a_score_does_not_double_count(self):
        t = Tournament.create("T", {"G": ["A", "B", "C", "D"]})
        first = t.groups[0].matches[0]
        t.record_score(first.id, "6-4")
        t.record_score(first.id, "6-1")
        row = next(r for r in t.groups[0].standings() if r.name == first.p1)
        self.assertEqual((row.played, row.wins, row.games_won, row.games_lost), (1, 1, 6, 1))


class TieBreakTests(unittest.TestCase):
    def test_h2h_lookup_both_orders_and_missing(self):
        rows, h2h = tally(["A", "B", "C"], matches(("A", "B", 4, 6)))
        a, b, c = rows
        self.assertEqual(get_h2h_winner_and_loser(a, b, h2h), (b, a))
        self.assertEqual(get_h2h_winner_and_loser(b, a, h2h), (b, a))
        self.assertIsNone(get_h2h_winner_and_loser(a, c, h2h))  # original: KeyError

    def test_two_way_tie_is_decided_by_head_to_head(self):
        ms = matches(("A", "B", 6, 5), ("B", "C", 6, 0), ("B", "D", 6, 0),
                     ("C", "A", 6, 0), ("A", "D", 6, 5), ("D", "C", 6, 0))
        # A and B both have 2 wins. B's game diff (+11) is far better than A's (-4),
        # but A beat B, so A is first. C and D (1 win each): D beat C.
        self.assertEqual(order(["A", "B", "C", "D"], ms), ["A", "B", "D", "C"])

    def test_three_way_tie_uses_game_diff_first(self):
        ms = matches(("A", "B", 6, 5), ("B", "C", 6, 5), ("C", "A", 6, 0),
                     ("A", "D", 6, 0), ("B", "D", 6, 0), ("C", "D", 6, 0))
        # A, B, C have 2 wins each; game diffs C +11, B +6, A +1 are all
        # different, so head-to-head is never consulted.
        self.assertEqual(order(["A", "B", "C", "D"], ms), ["C", "B", "A", "D"])

    def test_three_way_tie_equal_neighbours_swapped_by_h2h(self):
        ms = matches(("A", "B", 6, 0), ("B", "C", 6, 1), ("C", "A", 6, 1),
                     ("A", "D", 6, 5), ("B", "D", 6, 0), ("C", "D", 6, 1))
        # 2 wins each. Sort by (diff, games won): C (+5, 13), B (+5, 12), A (+2).
        # C and B are neighbours with equal diff and B beat C -> B, C, A.
        self.assertEqual(order(["A", "B", "C", "D"], ms), ["B", "C", "A", "D"])

    def test_three_way_full_tie_single_adjacent_pass(self):
        """Everything level: the sort keeps registration order and one pass of
        neighbour head-to-head swaps is made, exactly like the original."""
        ms = matches(("A", "B", 6, 3), ("B", "C", 6, 3), ("C", "A", 6, 3),
                     ("A", "D", 6, 3), ("B", "D", 6, 3), ("C", "D", 6, 3))
        # [A,B,C]: A beat B (keep), B beat C (keep)
        self.assertEqual(order(["A", "B", "C", "D"], ms), ["A", "B", "C", "D"])
        # [C,B,A]: B beat C -> [B,C,A]; then C beat A (keep)
        self.assertEqual(order(["C", "B", "A", "D"], ms), ["B", "C", "A", "D"])

    def test_live_standings_with_unplayed_matches_do_not_crash(self):
        players = ["A", "B", "C", "D"]
        self.assertEqual(order(players, []), players)
        # 3-way bucket on 0 wins with no head-to-head between C and D
        self.assertEqual(order(players, matches(("A", "B", 6, 4))), ["A", "C", "D", "B"])
        # 2-way buckets with no head-to-head fall back to game diff
        self.assertEqual(order(players, matches(("A", "B", 6, 4), ("C", "D", 6, 0))),
                         ["C", "A", "B", "D"])


# --------------------------------------------------------------------------- #
# Tournament flow
# --------------------------------------------------------------------------- #
class FlowTests(unittest.TestCase):
    def test_full_flow_and_persistence(self):
        t = Tournament.create("Cup", {"A": ["a1", "a2", "a3"], "B": ["b1", "b2", "b3", "b4", "b5"]},
                              MatchFormat(6, True), {"B": MatchFormat(3, False)})
        a, b = t.groups
        self.assertEqual(t.format_for(a.matches[0].id), MatchFormat(6, True))
        self.assertEqual(t.format_for(b.matches[0].id), MatchFormat(3, False))
        with self.assertRaises(ScoreError):                 # 6-1 is not first-to-3
            t.record_score(b.matches[0].id, "6-1")
        for m in a.matches:
            t.record_score(m.id, "6-1")                     # p1 always wins
        for m in b.matches:
            t.record_score(m.id, "3-2")
        self.assertTrue(t.group_stage_complete)
        ko = t.start_playoffs()
        sf1, sf2 = ko.matches["SF1"], ko.matches["SF2"]
        t.record_score("SF1", "6-1")
        t.record_score("SF2", "1-6")
        self.assertEqual(ko.matches["F"].p1, sf1.p1)
        self.assertEqual(ko.matches["F"].p2, sf2.p2)
        t.record_score("F", "7-6")
        t.record_score("3P", "7-5")
        self.assertEqual(ko.podium[0], sf1.p1)
        with self.assertRaises(TournamentError):            # group stage locked
            t.record_score(a.matches[0].id, "6-0")
        t.record_score("SF1", "1-6")                        # changing a semi clears the final
        self.assertIsNone(ko.matches["F"].score)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            persistence.save(t, p)
            t2 = persistence.load(p)
        self.assertEqual(t2.to_dict(), t.to_dict())

    def test_rounds_must_be_completed_in_order(self):
        t = Tournament.create("T", {"G": ["A", "B", "C", "D"]})
        g = t.groups[0]
        r1, r2 = g.matches_in_round(1), g.matches_in_round(2)
        self.assertFalse(t.is_editable(r2[0].id))
        with self.assertRaisesRegex(TournamentError, "Finish round 1"):
            t.record_score(r2[0].id, "6-4")
        t.record_score(r1[0].id, "6-4")
        with self.assertRaises(TournamentError):            # round 1 still incomplete
            t.record_score(r2[0].id, "6-4")
        t.record_score(r1[1].id, "6-4")
        self.assertEqual(g.current_round, 2)
        t.record_score(r2[0].id, "6-4")
        with self.assertRaises(TournamentError):            # every score is required
            t.start_playoffs()

    def test_old_save_files_are_rejected(self):
        t = Tournament.create("T", {"G": ["A", "B", "C", "D"]})
        d = t.to_dict()
        d["version"] = 1
        with self.assertRaises(TournamentError):
            Tournament.from_dict(d)

    def test_setup_validation(self):
        bad = [
            {"A": ["a", "b"]},                                  # too few
            {"A": ["a", "b", "c", "d", "e", "f"]},              # too many
            {"A": ["a", "b", "c"]},                             # 1 group needs 4+
            {"A": ["a", "b", "c"], "B": ["A", "d", "e"]},       # duplicate name
            {"A": ["a", "b", "c"], "B": ["d", "e", "f"], "C": ["g", "h", "i"]},  # 3 groups
        ]
        for groups in bad:
            with self.subTest(groups=groups), self.assertRaises(TournamentError):
                Tournament.create("x", groups)
        for n in (3, 4, 5):
            Tournament.create("x", {"A": list("abcde")[:n], "B": list("fghij")[:n]})


if __name__ == "__main__":
    unittest.main()
