import itertools
import tempfile
import unittest
from pathlib import Path

from tennis.core import (MatchFormat, ScoreError, Tournament, parse_score, round_robin)
from tennis.core import persistence


class ScoringTests(unittest.TestCase):
    def test_valid_bo3(self):
        s = parse_score("6-4, 3-6 7-6", MatchFormat(3))
        self.assertEqual(s.sets, (2, 1))
        self.assertEqual(s.games, (16, 16))

    def test_invalid(self):
        bad = ["6-5 6-4", "6-4 6-4 6-4", "6-4", "8-6 6-3", "abc", "6-6 6-4", ""]
        for txt in bad:
            with self.subTest(txt=txt), self.assertRaises(ScoreError):
                parse_score(txt, MatchFormat(3))

    def test_bo5_and_sets_only(self):
        self.assertEqual(parse_score("6-0 6-0 6-0", MatchFormat(5)).sets, (3, 0))
        f = MatchFormat(5, track_games=False)
        self.assertEqual(parse_score("1-3", f).sets, (1, 3))
        for txt in ("3-3", "2-1", "4-0"):
            with self.assertRaises(ScoreError):
                parse_score(txt, f)

    def test_super_tiebreak(self):
        f = MatchFormat(3, final_set_super_tiebreak=True)
        self.assertEqual(parse_score("6-4 4-6 12-10", f).sets, (2, 1))
        with self.assertRaises(ScoreError):
            parse_score("6-4 4-6 10-9", f)


class ScheduleTests(unittest.TestCase):
    def test_every_pair_once(self):
        for n in range(2, 11):
            rounds = round_robin(n)
            pairs = [frozenset(p) for r in rounds for p in r.pairs]
            self.assertEqual(len(pairs), n * (n - 1) // 2)
            self.assertEqual(set(pairs), {frozenset(c) for c in itertools.combinations(range(n), 2)})
            for r in rounds:  # nobody plays twice in a round
                flat = [x for p in r.pairs for x in p] + r.resting
                self.assertEqual(sorted(flat), list(range(n)))


def play(t, results):
    """results: {(winner, loser): score_text_from_winner_view}"""
    for g in t.groups:
        for m in g.matches:
            for (w, l), txt in results.items():
                if {m.p1, m.p2} == {w, l}:
                    if m.p1 != w:
                        txt = " ".join("-".join(reversed(s.split("-"))) for s in txt.split())
                    t.record_score(m.id, txt)


class RankingTests(unittest.TestCase):
    def test_circular_three_way_tie(self):
        t = Tournament.create("T", {"G": ["A", "B", "C", "D"]})
        play(t, {("A", "B"): "6-0 6-0", ("B", "C"): "6-0 6-0", ("C", "A"): "6-4 4-6 6-4",
                 ("A", "D"): "6-0 6-0", ("B", "D"): "6-0 6-0", ("C", "D"): "6-0 6-0"})
        # A,B,C all 2-1. Mini-league sets: A +1, B 0, C -1
        self.assertEqual([r.player for r in t.groups[0].standings()], ["A", "B", "C", "D"])

    def test_three_player_circular_falls_back_to_set_diff(self):
        t = Tournament.create("T", {"G": ["A", "B", "C"]})
        play(t, {("B", "A"): "7-6 4-6 7-6", ("A", "C"): "6-0 6-0", ("C", "B"): "6-0 6-0"})
        # all 1-1, circular; mini-league set diffs decide
        order = [r.player for r in t.groups[0].standings()]
        self.assertEqual(order, ["A", "C", "B"])  # set diffs +1, 0, -1

    def test_split_then_resolve_by_h2h(self):
        t = Tournament.create("T", {"G": ["A", "B", "C", "D"]})
        # A,B,C 2-1 ; A beats B, B beats C, C beats A but A,B big set diff vs C
        play(t, {("B", "A"): "6-0 6-0", ("A", "C"): "6-0 6-0", ("C", "B"): "6-0 4-6 6-0",
                 ("A", "D"): "6-0 6-0", ("B", "D"): "6-0 6-0", ("C", "D"): "6-0 6-0"})
        order = [r.player for r in t.groups[0].standings()]
        # mini sets: A 2-2=0, B 3-2=+1, C 2-3=-1 -> B, A, C
        self.assertEqual(order, ["B", "A", "C", "D"])


class FlowTests(unittest.TestCase):
    def test_full_flow_and_persistence(self):
        t = Tournament.create("Cup", {"A": ["a1", "a2", "a3"], "B": ["b1", "b2", "b3", "b4", "b5"]})
        for m in t.all_matches():
            t.record_score(m.id, "6-1 6-1")  # p1 always wins
        ko = t.start_playoffs()
        sf1, sf2 = ko.matches["SF1"], ko.matches["SF2"]
        t.record_score("SF1", "6-1 6-1"); t.record_score("SF2", "1-6 1-6")
        self.assertEqual(ko.matches["F"].p1, sf1.p1)
        self.assertEqual(ko.matches["F"].p2, sf2.p2)
        t.record_score("F", "6-1 6-1"); t.record_score("3P", "6-1 6-1")
        self.assertEqual(ko.podium[0], sf1.p1)
        # changing a semi clears the dependent final
        t.record_score("SF1", "1-6 1-6")
        self.assertIsNone(ko.matches["F"].score)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            persistence.save(t, p)
            t2 = persistence.load(p)
        self.assertEqual(t2.to_dict(), t.to_dict())

    def test_validation(self):
        with self.assertRaises(Exception):
            Tournament.create("x", {"A": ["a", "b"]})
        with self.assertRaises(Exception):
            Tournament.create("x", {"A": ["a", "b", "c"], "B": ["A", "d", "e"]})


if __name__ == "__main__":
    unittest.main()
