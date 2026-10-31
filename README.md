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
    scoring.py     # MatchFormat, Score, parse_score()  (validation)
    scheduling.py  # round_robin(n): circle/polygon method, any N
    ranking.py     # compute_standings(): recursive tie-breaks
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
1. **Setup**: tournament name, 1/2/4 groups (so exactly 4 players reach the playoffs), group names,
   3–8 players per group, best-of-1/3/5, game-score entry on/off, optional 10-point super tie-break.
2. **Group stage**: one tab per group. The schedule is listed by round, with resting players shown.
   Each score field turns green or red as you type and explains any error. Press Enter or tab away
   to save. The standings table (Rank, Player, P, W, L, Sets W/L, Diff, Games ±) updates live, and
   qualifiers are highlighted. A progress bar shows how many matches are done, and **Go to playoffs**
   unlocks once every match has a score.
3. **Playoffs**: SF1 and SF2 feed the Final and the 3rd-place match automatically. Editing a
   semi-final clears any dependent result that is no longer valid.
4. **Podium**: Champion, Runner-up and 3rd place.

Save (Ctrl+S) or open a tournament as JSON at any point to pause and resume it.

---

## Code review of the original script

### Bugs found
| Where | Problem |
|---|---|
| `play_rounds` | A win is counted only if a player has **exactly 3** sets. A best-of-3 result `2-1` gives nobody the win, and `3-3` or `5-0` are accepted. |
| `play_rounds` / `play_knockout_match` | There is no input validation. `int(input())` crashes on typos, and a tied score in a knockout gives the win to player 2. |
| `rank_players` (2-way tie) | `get_h2h_winner_and_loser` is used, which is fine. |
| `rank_players` (≥3 tied) | Sorting by set diff and then making one pass of **adjacent swaps** gives the wrong order. For example, with diffs A=B=C, swapping A/B and then B/C can never compare A with C, and the result depends on the starting order. Circular ties (A>B>C>A) get an arbitrary result. |
| `rank_players` | Head-to-head is checked with `p1, p2` order fallbacks, but if the players never met (e.g. extended formats) it raises `KeyError`. |
| `create_matchup` | Hard-coded for 3/4/5 players. The 3-player and 4/5-player branches also return different shapes (list vs tuple of pairs). |
| main | `players_list = [g1 + g2]` is unused. Duplicate names silently break the name-keyed `head_to_head`. |

### 1. Scoring & rules validation (`core/scoring.py`)
- `MatchFormat(best_of, track_games, final_set_super_tiebreak)` is passed everywhere, so nothing
  hard-codes "3". `sets_to_win = best_of // 2 + 1`.
- Sets-only mode: the winner must have exactly `sets_to_win` and the loser fewer, so `2-2` and `3-1`
  are rejected in best-of-3.
- Game mode: each set must be 6-0…6-4, 7-5 or 7-6 (or a 10-point match tie-break for the deciding
  set). No set may be played after the match is decided, and the match must actually be completed.
- The game differential is stored (`Score.games`) and used as a later tie-breaker.
- Possible extensions: retirements/walkovers (`Score(status="RET")` counted as a win with the sets
  played so far), and `no-ad` or short-set (first to 4) formats via extra `MatchFormat` fields.

### 2. Tie-breaking (`core/ranking.py`)
Tied players are handled as a **block**. A mini-league is built from only the matches among them,
using wins, then set diff, then game diff. As soon as a criterion splits the block, each remaining
tied sub-block is **re-resolved from scratch with only its own members**, which matches ITF/ATP
round-robin rules. Circular ties (each player 1-1 in the mini-league) fall through to set and game
difference. Overall set diff, game diff, sets won and then name are used as the final deterministic
fallbacks. Tests cover the circular 3-way tie and the case where splitting a block and then using
head-to-head decides the order.

### 3. Generalized scheduling (`core/scheduling.py`)
The circle (polygon / Berger) method: fix player 0 and rotate the others. Odd N adds a phantom BYE,
so each round shows who rests. Home/away orientation alternates. This produces N-1 rounds (even N)
or N rounds (odd N), covers every pair exactly once, and no one plays twice in a round. This is
verified for N = 2…10.

### 4. Persistence (`core/persistence.py`)
Every model has `to_dict`/`from_dict`, and the file includes a `version` field for later schema
migrations. Writes go to a temp file followed by `os.replace` (atomic), so a crash can't corrupt a save.
**SQLite option**: use tables `tournament`, `player`, `group`, `match(id, stage, round, p1, p2, score_json)`.
Make `persistence` an interface (`Repository.save/load`) with `JsonRepository` and `SqliteRepository`
implementations so the controller doesn't care which is used. SQLite becomes worthwhile when you want
history across many tournaments or player statistics.

### 5. Refactoring to domain models (`core/models.py`)
- `Match` is the single source of truth. Standings are **derived** on demand from match results
  instead of being mutated counters, so editing or correcting a score can never double-count. In
  the old script, re-entering a result would add the counters twice.
- `Group` owns its players, schedule and `standings()`. `Knockout` owns the bracket and its
  winner/loser propagation. `Tournament` validates setup (unique names, group sizes, group count),
  routes commands, and locks the group stage once the playoffs start (it can be reopened explicitly).
- Seeding: with 1 group it's 1v4 and 2v3. With 2 groups it's A1vB2 and B1vA2, as in the original.
  With 4 groups the winners play A–D and B–C.

### Further ideas
- Larger brackets (8/16 qualifiers) by generalizing `Knockout` into rounds of `Match` nodes, each
  with `feeds_from` links.
- Undo/redo with a command stack in the controller.
- Export standings and the bracket to PDF/CSV, and add a dark/light theme toggle.
