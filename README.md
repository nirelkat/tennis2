# 🎾 Tennis Tournament Manager

A tennis tournament manager covering the group stage (round robin) and the playoffs, with a CustomTkinter GUI.

```bash
pip install -r requirements.txt     # customtkinter (needs Python built with tkinter)
python -m tennis                    # launch the GUI
python -m unittest discover tests   # run core tests
```

The original CLI script `tennis_group_standings.py` is still here for reference.

## Architecture

```
tennis/
  core/            # pure domain logic, no UI imports, fully unit-tested
    scoring.py     # MatchFormat(games_to_win, tiebreak), Score, parse_score()
    scheduling.py  # round_robin(n): circle/polygon method, any N
    ranking.py     # rank_players(): the original tie-break algorithm, in games
    models.py      # Match, Group, Knockout, Tournament (commands + to/from dict)
    persistence.py # JSON save/load (atomic write)
  gui/
    controller.py  # TournamentController: the only bridge view -> model, observer notify
    app.py         # Setup -> Group Stage -> Playoffs -> Podium screens
tests/test_core.py
```

The views never change the model directly. They call controller commands, the controller
notifies its subscribers, and the active screen re-renders from the model. This MVC
structure means any frontend (CLI, web, Qt) can reuse `core` unchanged.

### User flow
1. **Setup**: tournament name, 1/2/4 groups, group names and **3, 4 or 5 players per group**.
   Every group card has its own format card (**Games to win [2] [3] [6]**, **Enable Tie-Break**, and the
   valid scores underneath). A separate **Playoff Format** card sets the knockout format, and the
   **Qualification** control shows how many players advance (see below). It updates as you type players.
2. **Group stage**: one tab per group. The schedule is listed by round, with resting players shown.
   Rounds are played in order: a round unlocks once every score of the previous round is in. Each
   score field turns green or red as you type and explains any error. Press Enter or tab away to
   save. The standings table (#, Player, P, W, L, Games Won, Games Lost, Game Diff) updates live and
   qualifiers are highlighted. The button to start the playoffs unlocks only when every match has a score.
3. **Playoffs**: the bracket has one column per round (Round of 16 → Quarter-Finals → Semi-Finals →
   Final), plus a 3rd place match whenever there are semi-finals. Winners move forward automatically.
   Changing an earlier result clears every later result that depended on it.
4. **Podium**: Champion, Runner-up and (when there was a 3rd place match) 3rd place.

### Playoff qualification (`Tournament.advance_options`, `playoff_pairs`)
| Groups | Group sizes | Advance per group | Bracket |
|---|---|---|---|
| 1 | 3–5 | top 2 | **Final** (1 v 2) |
| 2 | any | top 2 (default) | **Semi-Finals**: A1–B2, B1–A2 → Final + 3rd place |
| 2 | both exactly 5 | top 4 (option) | **Quarter-Finals**: A1–B4, B2–A3 → SF1; B1–A4, A2–B3 → SF2 |
| 4 | any | top 2 (default) | **Quarter-Finals**: A1–B2, C1–D2 → SF1; B1–A2, D1–C2 → SF2 |
| 4 | all exactly 5 | top 4 (option) | **Round of 16**: 1st v 4th and 2nd v 3rd of another group |

Players from the same group are placed in opposite halves of the bracket, so a group's top two can
only meet in the Final. In the Round of 16, a group's four qualifiers are in four different quarters.

Save (Ctrl+S) or open a tournament as JSON at any point to pause and resume it.

---

## Match format (`core/scoring.py`)

Every match is **one set**, entered as the games each player won (`6-4`, player 1 first).
`MatchFormat(games_to_win, tiebreak)`:

| Games to win | Tie-break off (sudden death) | Tie-break on (win by two at N-1 all, deciding game at N-N) |
|---|---|---|
| 2 | 2-0, 2-1 | 2-0, 3-1, 3-2 |
| 3 | 3-0, 3-1, 3-2 | 3-0, 3-1, 4-2, 4-3 |
| 6 | 6-0 … 6-5 | 6-0 … 6-4, 7-5, 7-6 |

Anything else is rejected with a reason, e.g. `3-2` with tie-break on: *"At 2-2 a player must win
by two: 4-2, or 4-3 after the tie-break game"*. Level scores, unfinished matches and games played
after the match was over are all rejected. A score is required for every match: there is no
"skip" option, and the next round, the playoffs and the podium stay locked until scores are in.

## Standings & tie-breaking (`core/ranking.py`)

The ranking engine is **the algorithm from the original script**. `rank_players()` and
`get_h2h_winner_and_loser()` keep their names and their flow:

1. Players are bucketed by number of wins, most wins first.
2. A bucket of **1** is placed as is.
3. A bucket of **2** is ordered by their head-to-head match.
4. A bucket of **3 or more** is sorted by *(game difference, games won)*, then one pass is made over
   neighbouring pairs: if two neighbours have the same game difference, they are put in
   head-to-head order.

What changed, without touching that logic:
- **Games instead of sets.** A match is now one set, so the totals and the differential are in games.
  The head-to-head dictionary keeps the original shape, `(p1, p2) -> (games p1, games p2)`.
- **Crash guards.** Standings are shown live, before every match is played. In the original,
  `get_h2h_winner_and_loser()` raised `KeyError` when two tied players hadn't met. It now returns
  `None`, a 2-player bucket then falls back to *(game difference, games won)*, and in a 3+ bucket
  the neighbours keep their sorted order. A level score (impossible after validation) is treated the
  same way.
- **Standings are recomputed from the match results** every time (`tally()`), instead of
  incremented counters, so correcting a score never double-counts.

Properties of the algorithm worth knowing when presenting it (covered by tests): in a 3+ bucket
the game difference comes before head-to-head, the swap pass compares neighbours only, and when
everything is level, registration order is kept (Python's sort is stable).

---

## Code review of the original script

### Bugs found
| Where | Problem | Now |
|---|---|---|
| `play_rounds` | A win was counted only if a player had **exactly 3**; any other score gave nobody the win. | Single-set game scores, validated against the format; the winner is whoever has more games. |
| `play_rounds` / `play_knockout_match` | No input validation: `int(input())` crashes on typos, and a level knockout score gives the win to player 2. | `parse_score()` rejects malformed and impossible scores with a message. |
| `get_h2h_winner_and_loser` | `KeyError` if the two players haven't played each other. | Returns `None`; `rank_players()` handles it (see above). |
| main | `players_list = [g1 + g2]` is unused. Duplicate names silently break the name-keyed `head_to_head`. | Setup rejects duplicate names (case-insensitive). |

### Scheduling (`core/scheduling.py`)
The circle (polygon / Berger) method: fix player 0 and rotate the others. Odd N adds a phantom BYE,
so each round shows who rests. Home/away orientation alternates. This produces N-1 rounds (even N)
or N rounds (odd N), covers every pair exactly once, and no one plays twice in a round. This is
verified for N = 3, 4, 5.

### Persistence (`core/persistence.py`)
Every model has `to_dict`/`from_dict`, and the file includes a `version` field (now 3; files
saved by older versions are refused with a clear message). Writes go to a temp file followed by `os.replace` (atomic), so a crash can't corrupt a save.
**SQLite option**: use tables `tournament`, `player`, `group`, `match(id, stage, round, p1, p2, score_json)`.
Make `persistence` an interface (`Repository.save/load`) with `JsonRepository` and `SqliteRepository`
implementations so the controller doesn't care which is used. SQLite becomes worthwhile when you want
history across many tournaments or player statistics.

### Domain models (`core/models.py`)
- `Match` is the single source of truth. Standings are **derived** on demand from match results
  instead of being mutated counters, so editing or correcting a score can never double-count. In
  the old script, re-entering a result would add the counters twice.
- `Group` owns its players, schedule and `standings()`. `Knockout` owns the bracket and its
  winner/loser propagation. `Tournament` validates setup (unique names, group sizes, group count),
  routes commands, and locks the group stage once the playoffs start (it can be reopened explicitly).
- `Knockout` is a generic single-elimination bracket for 2, 4, 8 or 16 players: match *j* of a round is
  fed by the winners of matches *2j-1* and *2j* of the previous round. Seeding is in the table above.

### Further ideas
- Undo/redo with a command stack in the controller.
- Export standings and the bracket to PDF/CSV, and add a dark/light theme toggle.
