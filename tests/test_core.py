import itertools
import tempfile
import unittest
from pathlib import Path

from tennis.core import (Match, MatchFormat, Score, ScoreError, Tournament, TournamentError,
                         compute_standings, get_h2h_winner_and_loser, parse_score,
                         playoff_pairs, round_robin, tally)
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
def make(groups, advance=2, group_formats=None, playoff_fmt=None):
    return Tournament.create("T", groups, group_formats, playoff_fmt, advance)


def play_groups(t):
    """Enter a valid score for every group match (player 1 always wins)."""
    for g in t.groups:
        w, lo = g.fmt.valid_results()[0]
        for m in g.matches:
            t.record_score(m.id, f"{w}-{lo}")


def play_bracket(t, text="6-1"):
    ko = t.knockout
    for _name, ids in ko.rounds:
        for mid in ids + (["3P"] if "3P" in ko.matches and ids == ["F"] else []):
            t.record_score(mid, text)


def players(prefix, n):
    return [f"{prefix}{i}" for i in range(1, n + 1)]


class FlowTests(unittest.TestCase):
    def test_full_flow_and_persistence(self):
        t = make({"A": players("a", 3), "B": players("b", 5)},
                 group_formats={"A": MatchFormat(6, True), "B": MatchFormat(3, False)},
                 playoff_fmt=MatchFormat(2, True))
        a, b = t.groups
        self.assertEqual(t.format_for(a.matches[0].id), MatchFormat(6, True))
        self.assertEqual(t.format_for(b.matches[0].id), MatchFormat(3, False))
        with self.assertRaises(ScoreError):                 # 6-1 is not first-to-3
            t.record_score(b.matches[0].id, "6-1")
        play_groups(t)
        self.assertTrue(t.group_stage_complete)
        ko = t.start_playoffs()
        self.assertEqual(t.format_for("SF1"), MatchFormat(2, True))
        with self.assertRaises(ScoreError):                 # playoffs are first to 2
            t.record_score("SF1", "6-1")
        sf1, sf2 = ko.matches["SF1"], ko.matches["SF2"]
        t.record_score("SF1", "3-2")
        t.record_score("SF2", "1-3")
        self.assertEqual((ko.matches["F"].p1, ko.matches["F"].p2), (sf1.p1, sf2.p2))
        self.assertEqual((ko.matches["3P"].p1, ko.matches["3P"].p2), (sf1.p2, sf2.p1))
        t.record_score("F", "2-0")
        t.record_score("3P", "3-1")
        self.assertEqual(ko.podium, (sf1.p1, sf2.p2, sf1.p2))
        with self.assertRaises(TournamentError):            # group stage locked
            t.record_score(a.matches[0].id, "6-0")
        t.record_score("SF1", "1-3")                        # changing a semi clears the final
        self.assertIsNone(ko.matches["F"].score)
        self.assertIsNone(ko.podium)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            persistence.save(t, p)
            t2 = persistence.load(p)
        self.assertEqual(t2.to_dict(), t.to_dict())

    def test_rounds_must_be_completed_in_order(self):
        t = make({"G": ["A", "B", "C", "D"]})
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
        d = make({"G": ["A", "B", "C", "D"]}).to_dict()
        d["version"] = 2
        with self.assertRaises(TournamentError):
            Tournament.from_dict(d)

    def test_setup_validation(self):
        bad = [
            {"A": ["a", "b"]},                                  # too few
            {"A": ["a", "b", "c", "d", "e", "f"]},              # too many
            {"A": ["a", "b", "c"], "B": ["A", "d", "e"]},       # duplicate name
            {"A": ["a", "b", "c"], "B": ["d", "e", "f"], "C": ["g", "h", "i"]},  # 3 groups
        ]
        for groups in bad:
            with self.subTest(groups=groups), self.assertRaises(TournamentError):
                make(groups)
        for n in (3, 4, 5):
            make({"A": players("a", n)})
            make({"A": players("a", n), "B": players("b", n)})


# --------------------------------------------------------------------------- #
# Playoff qualification and bracket sizes
# --------------------------------------------------------------------------- #
def ranked(*prefixes, n=5):
    return [players(p, n) for p in prefixes]


class QualificationTests(unittest.TestCase):
    def test_advance_options(self):
        opts = Tournament.advance_options
        self.assertEqual(opts([3]), [2])                     # 1 group: Final
        self.assertEqual(opts([4]), [2])
        self.assertEqual(opts([5]), [2, 4])                  # 1 group of 5: Final or SFs
        self.assertEqual(opts([5, 5]), [2, 4])
        self.assertEqual(opts([5, 4]), [2])
        self.assertEqual(opts([5, 5, 5, 5]), [2, 4])
        self.assertEqual(opts([5, 5, 5, 3]), [2])

    def test_top4_only_with_all_groups_of_five(self):
        for groups in ({"A": players("a", 3)},
                       {"A": players("a", 4)},
                       {"A": players("a", 5), "B": players("b", 4)},
                       {g: players(g.lower(), 5 if g != "D" else 4) for g in "ABCD"}):
            with self.subTest(groups=groups), self.assertRaises(TournamentError):
                make(groups, advance=4)

    def test_pairs(self):
        self.assertEqual(playoff_pairs(ranked("A", n=3), 2), [("A1", "A2")])
        self.assertEqual(playoff_pairs(ranked("A", "B"), 2), [("A1", "B2"), ("B1", "A2")])
        self.assertEqual(playoff_pairs(ranked("A", "B"), 4),
                         [("A1", "B4"), ("B2", "A3"), ("B1", "A4"), ("A2", "B3")])
        self.assertEqual(playoff_pairs(ranked("A", "B", "C", "D", n=3), 2),
                         [("A1", "B2"), ("C1", "D2"), ("B1", "A2"), ("D1", "C2")])

    def test_round_of_16_keeps_group_mates_apart(self):
        pairs = playoff_pairs(ranked("A", "B", "C", "D"), 4)
        flat = [p for pair in pairs for p in pair]
        self.assertEqual(sorted(flat), sorted(f"{g}{i}" for g in "ABCD" for i in range(1, 5)))
        for a, b in pairs:                       # 1st v 4th and 2nd v 3rd, different groups
            self.assertNotEqual(a[0], b[0])
            self.assertEqual(int(a[1]) + int(b[1]), 5)
        quarter = {p: i // 4 for i, p in enumerate(flat)}
        for g in "ABCD":
            self.assertEqual(len({quarter[f"{g}{i}"] for i in range(1, 5)}), 4)
            self.assertNotEqual(quarter[f"{g}1"] // 2, quarter[f"{g}2"] // 2)   # other half

    def test_bracket_shapes(self):
        cases = [  # groups, advance, size, round names
            ({"A": players("a", 3)}, 2, 2, ["Final"]),
            ({"A": players("a", 4)}, 2, 2, ["Final"]),
            ({"A": players("a", 5)}, 2, 2, ["Final"]),
            ({"A": players("a", 5)}, 4, 4, ["Semi-Finals", "Final"]),
            ({"A": players("a", 4), "B": players("b", 3)}, 2, 4, ["Semi-Finals", "Final"]),
            ({"A": players("a", 5), "B": players("b", 5)}, 2, 4, ["Semi-Finals", "Final"]),
            ({"A": players("a", 5), "B": players("b", 5)}, 4, 8,
             ["Quarter-Finals", "Semi-Finals", "Final"]),
            ({g: players(g.lower(), 3) for g in "ABCD"}, 2, 8,
             ["Quarter-Finals", "Semi-Finals", "Final"]),
            ({g: players(g.lower(), 5) for g in "ABCD"}, 4, 16,
             ["Round of 16", "Quarter-Finals", "Semi-Finals", "Final"]),
        ]
        for groups, adv, size, names in cases:
            with self.subTest(groups=list(map(len, groups.values())), advance=adv):
                t = make(groups, advance=adv)
                self.assertEqual(t.playoff_size, size)
                play_groups(t)
                ko = t.start_playoffs()
                self.assertEqual(ko.size, size)
                self.assertEqual([n for n, _ in ko.rounds], names)
                first = ko.rounds[0][1]
                self.assertEqual(len(first), size // 2)
                self.assertTrue(all(ko.matches[m].is_ready for m in first))
                three_player_group = len(groups) == 1 and len(t.groups[0].players) == 3
                self.assertEqual("3P" in ko.matches, not three_player_group)
                play_bracket(t)
                champ, runner, third = ko.podium
                self.assertEqual(champ, ko.matches["F"].winner)
                self.assertEqual(runner, ko.matches["F"].loser)
                if three_player_group:
                    self.assertEqual(third, t.groups[0].standings()[2].name)
                else:
                    self.assertEqual(third, ko.matches["3P"].winner)

    def test_round_of_16_progression_and_reset(self):
        t = make({g: players(g.lower(), 5) for g in "ABCD"}, advance=4)
        play_groups(t)
        ko = t.start_playoffs()
        play_bracket(t)                           # player 1 always wins
        r16 = [ko.matches[f"R16-{j}"] for j in range(1, 9)]
        qf = [ko.matches[f"QF{j}"] for j in range(1, 5)]
        for j, m in enumerate(qf):
            self.assertEqual((m.p1, m.p2), (r16[2 * j].winner, r16[2 * j + 1].winner))
        self.assertEqual(ko.matches["F"].p1, ko.matches["SF1"].winner)
        t.record_score("R16-1", "1-6")            # upset in the first match
        self.assertEqual(qf[0].p1, r16[0].p2)
        for mid in ("QF1", "SF1", "F", "3P"):     # everything downstream is reset
            self.assertIsNone(ko.matches[mid].score, mid)
        self.assertIsNotNone(ko.matches["QF2"].score)   # other half untouched
        self.assertIsNone(ko.podium)
        with self.assertRaises(TournamentError):  # SF1 has no players yet
            t.record_score("SF1", "6-1")

    def test_quarter_final_bracket_persists(self):
        t = make({"A": players("a", 5), "B": players("b", 5)}, advance=4)
        play_groups(t)
        t.start_playoffs()
        t.record_score("QF1", "6-2")
        d = t.to_dict()
        self.assertEqual(Tournament.from_dict(d).to_dict(), d)
        self.assertEqual(Tournament.from_dict(d).knockout.size, 8)


class SingleGroupTests(unittest.TestCase):
    """1 group: 3 players -> Final + bronze by ranking; 4 players -> Final +
    3rd v 4th; 5 players -> that (default) or Semi-Finals 1v4, 2v3."""

    def start(self, n, advance=2):
        t = make({"G": players("p", n)}, advance=advance)
        play_groups(t)                        # player 1 of every match wins
        order = [r.name for r in t.groups[0].standings()]
        return t, t.start_playoffs(), order

    def test_three_players_final_and_bronze_from_group(self):
        t, ko, order = self.start(3)
        self.assertEqual(list(ko.matches), ["F"])
        self.assertEqual((ko.matches["F"].p1, ko.matches["F"].p2), (order[0], order[1]))
        self.assertEqual(ko.bronze, order[2])
        self.assertEqual(t.bronze_ranks, [3])
        self.assertIsNone(ko.podium)
        t.record_score("F", "1-6")             # 2nd beats 1st
        self.assertEqual(ko.podium, (order[1], order[0], order[2]))
        with self.assertRaises(TournamentError):
            make({"G": players("p", 3)}, advance=4)

    def test_four_players_final_and_third_place_match(self):
        t, ko, order = self.start(4)
        self.assertEqual(sorted(ko.matches), ["3P", "F"])
        f, tp = ko.matches["F"], ko.matches["3P"]
        self.assertEqual((f.p1, f.p2), (order[0], order[1]))
        self.assertEqual((tp.p1, tp.p2), (order[2], order[3]))
        self.assertIsNone(ko.bronze)
        self.assertEqual(sorted(ko.participants), sorted(order))
        self.assertEqual(t.bronze_ranks, [3, 4])
        t.record_score("3P", "2-6")            # 4th beats 3rd
        t.record_score("F", "6-2")
        self.assertEqual(ko.podium, (order[0], order[1], order[3]))
        t.record_score("F", "2-6")             # editing the Final keeps the 3P result
        self.assertIsNotNone(tp.score)
        self.assertEqual(ko.podium, (order[1], order[0], order[3]))
        with self.assertRaises(TournamentError):
            make({"G": players("p", 4)}, advance=4)

    def test_five_players_default_is_final_plus_third_place(self):
        t, ko, order = self.start(5)
        self.assertEqual(ko.size, 2)
        self.assertEqual((ko.matches["F"].p1, ko.matches["F"].p2), (order[0], order[1]))
        self.assertEqual((ko.matches["3P"].p1, ko.matches["3P"].p2), (order[2], order[3]))
        self.assertNotIn(order[4], ko.participants)

    def test_five_players_semi_finals_option(self):
        t, ko, order = self.start(5, advance=4)
        self.assertEqual(t.bronze_ranks, [])
        sf1, sf2 = ko.matches["SF1"], ko.matches["SF2"]
        self.assertEqual((sf1.p1, sf1.p2), (order[0], order[3]))    # 1st v 4th
        self.assertEqual((sf2.p1, sf2.p2), (order[1], order[2]))    # 2nd v 3rd
        self.assertFalse(ko.matches["3P"].is_ready)
        t.record_score("SF1", "2-6")
        t.record_score("SF2", "6-2")
        self.assertEqual((ko.matches["F"].p1, ko.matches["F"].p2), (order[3], order[1]))
        self.assertEqual((ko.matches["3P"].p1, ko.matches["3P"].p2), (order[0], order[2]))
        t.record_score("F", "6-3")
        t.record_score("3P", "6-3")
        self.assertEqual(ko.podium, (order[3], order[1], order[0]))

    def test_single_group_brackets_persist(self):
        for n, adv in ((3, 2), (4, 2), (5, 4)):
            with self.subTest(n=n, advance=adv):
                t, ko, _ = self.start(n, adv)
                d = t.to_dict()
                t2 = Tournament.from_dict(d)
                self.assertEqual(t2.to_dict(), d)
                self.assertEqual(t2.knockout.bronze, ko.bronze)


if __name__ == "__main__":
    unittest.main()
