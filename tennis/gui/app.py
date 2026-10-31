"""CustomTkinter front-end: Setup -> Group Stage -> Playoffs -> Podium."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ..core import GAME_TARGETS, MatchFormat, ScoreError, Tournament, TournamentError, parse_score
from ..core.models import ROUND_NAMES, Knockout, Match
from .controller import TournamentController

OK_COLOR, ERR_COLOR, MUTED = "#2fa572", "#d9534f", "gray60"
GOLD, SILVER, BRONZE = "#d4af37", "#c0c0c0", "#cd7f32"


# --------------------------------------------------------------------------- #
class ScoreRow(ctk.CTkFrame):
    """One match: names, score entry with live validation, status icon."""

    def __init__(self, master, ctrl: TournamentController, match: Match, title: str = ""):
        super().__init__(master, corner_radius=8)
        self.ctrl, self.match_id = ctrl, match.id
        self.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=MUTED).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 0))
        self.names = ctk.CTkLabel(self, anchor="w")
        self.names.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        # no textvariable: CTkEntry only shows placeholder_text without one
        fmt = ctrl.tournament.format_for(match.id)
        self.entry = ctk.CTkEntry(self, width=90, justify="center",
                                  placeholder_text=f"e.g. {fmt.example}")
        self.entry.grid(row=1, column=1, padx=4)
        self.status = ctk.CTkLabel(self, text="", width=24)
        self.status.grid(row=1, column=2, padx=(0, 10))
        self.msg = ctk.CTkLabel(self, text="", text_color=ERR_COLOR, font=ctk.CTkFont(size=11))
        self.msg.grid(row=2, column=0, columnspan=3, sticky="w", padx=10)
        self.msg.grid_remove()
        self.entry.bind("<Return>", self._commit)
        self.entry.bind("<FocusOut>", self._commit)
        self.entry.bind("<KeyRelease>", lambda _e: self._live_check())
        self.update_from(match)

    def _score_text(self) -> str:
        return self.entry.get().strip()

    def _set_score_text(self, value: str) -> None:
        if self._score_text() == value:
            return
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value)

    def update_from(self, m: Match) -> None:
        p1, p2 = m.p1 or "TBD", m.p2 or "TBD"
        if m.winner:
            p1 = f"★ {p1}" if m.winner == m.p1 else p1
            p2 = f"★ {p2}" if m.winner == m.p2 else p2
        self.names.configure(text=f"{p1}   vs   {p2}")
        try:
            editing = self.focus_get() is self.entry._entry
        except (KeyError, tk.TclError):
            editing = False
        if not editing:
            self.entry.configure(state="normal")       # a disabled entry can't be written
            self._set_score_text(str(m.score) if m.score else "")
            self._live_check()
        state = "normal" if self.ctrl.tournament.is_editable(m.id) else "disabled"
        self.entry.configure(state=state)
        self.status.configure(text="✔" if m.is_played else "", text_color=OK_COLOR)

    def _live_check(self) -> None:
        txt = self._score_text()
        fmt = self.ctrl.tournament.format_for(self.match_id)
        try:
            if txt:
                parse_score(txt, fmt)
            self.entry.configure(border_color=OK_COLOR if txt else ("gray70", "gray30"))
            self.msg.grid_remove()
        except ScoreError as e:
            self.entry.configure(border_color=ERR_COLOR)
            self.msg.configure(text=str(e))
            self.msg.grid()

    def _commit(self, _evt=None) -> None:
        m = self.ctrl.tournament.find_match(self.match_id)
        if self._score_text() == (str(m.score) if m.score else ""):
            return
        try:
            self.ctrl.record_score(self.match_id, self._score_text())
        except ScoreError:
            pass  # message already shown by live validation
        except TournamentError as e:
            self.msg.configure(text=str(e))
            self.msg.grid()


# --------------------------------------------------------------------------- #
class FormatCard(ctk.CTkFrame):
    """Match-format control: games to win [2][3][6], tie-break checkbox, valid scores."""

    def __init__(self, master, title: str = "Match format", fmt: MatchFormat | None = None):
        super().__init__(master, corner_radius=8, border_width=1, border_color=("gray75", "gray30"))
        fmt = fmt or MatchFormat()
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 2))
        ctk.CTkLabel(self, text="Games to win").grid(row=1, column=0, sticky="w", padx=10)
        self.games = ctk.CTkSegmentedButton(self, values=[str(n) for n in GAME_TARGETS],
                                            command=lambda _v: self._update_hint())
        self.games.set(str(fmt.games_to_win))
        self.games.grid(row=1, column=1, sticky="w", padx=6, pady=2)
        self.tiebreak = ctk.CTkCheckBox(self, text="Enable Tie-Break", command=self._update_hint)
        if fmt.tiebreak:
            self.tiebreak.select()
        self.tiebreak.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=2)
        self.hint = ctk.CTkLabel(self, text="", text_color=MUTED, justify="left", anchor="w",
                                 wraplength=320, font=ctk.CTkFont(size=11))
        self.hint.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))
        self._update_hint()

    def get(self) -> MatchFormat:
        return MatchFormat(int(self.games.get()), bool(self.tiebreak.get()))

    def _update_hint(self) -> None:
        fmt = self.get()
        n = fmt.games_to_win
        rule = (f"Win by two at {n - 1}-{n - 1}; deciding game at {n}-{n}."
                if fmt.tiebreak else f"Sudden death: first to {n} wins.")
        scores = ", ".join(f"{w}-{lo}" for w, lo in fmt.valid_results())
        self.hint.configure(text=f"Valid scores: {scores}\n{rule}")


class SetupView(ctk.CTkScrollableFrame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app
        # per group: (name entry, format card, players textbox, count label)
        self.group_frames: list[tuple[ctk.CTkEntry, FormatCard, ctk.CTkTextbox, ctk.CTkLabel]] = []
        self.advance_choices: dict[str, int] = {}
        ctk.CTkLabel(self, text="🎾 New Tournament", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(10, 4))
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(top, text="Name").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.name = ctk.CTkEntry(top, width=220)
        self.name.insert(0, "Club Championship")
        self.name.grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkLabel(top, text="Groups").grid(row=0, column=2, padx=8)
        self.n_groups = ctk.CTkSegmentedButton(top, values=["1", "2", "4"], command=self._rebuild)
        self.n_groups.set("2")
        self.n_groups.grid(row=0, column=3, padx=8, sticky="w")

        self.groups_box = ctk.CTkFrame(self, fg_color="transparent")
        self.groups_box.pack(fill="both", expand=True, padx=20)

        # ---- playoffs card
        po = ctk.CTkFrame(self)
        po.pack(fill="x", padx=28, pady=8)
        po.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(po, text="🏆 Playoffs", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        self.playoff_fmt = FormatCard(po, "Playoff Format")
        self.playoff_fmt.grid(row=1, column=0, rowspan=3, sticky="nw", padx=10, pady=(0, 10))
        ctk.CTkLabel(po, text="Qualification", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=1, sticky="w", padx=10)
        self.advance = ctk.CTkSegmentedButton(po, values=["-"], command=lambda _v: self._update_qualification())
        self.advance.grid(row=2, column=1, sticky="w", padx=10)
        self.qual_info = ctk.CTkLabel(po, text="", text_color=MUTED, justify="left", anchor="w")
        self.qual_info.grid(row=3, column=1, sticky="nw", padx=10)

        self.error = ctk.CTkLabel(self, text="", text_color=ERR_COLOR)
        self.error.pack()
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(pady=10)
        ctk.CTkButton(bar, text="Load saved…", fg_color="gray40", command=app.load).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Create tournament ▶", command=self._create).pack(side="left", padx=6)
        self._rebuild("2")

    # ---- group cards ---------------------------------------------------------
    def _rebuild(self, n: str) -> None:
        # keep what was already typed into the groups that remain
        kept = [(e.get(), card.get(), tb.get("1.0", "end").strip()) for e, card, tb, _ in self.group_frames]
        for w in self.groups_box.winfo_children():
            w.destroy()
        self.group_frames.clear()
        for i in range(int(n)):
            name, fmt, text = kept[i] if i < len(kept) else (f"Group {chr(65 + i)}", None, "")
            f = ctk.CTkFrame(self.groups_box)
            f.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="nsew")
            self.groups_box.grid_columnconfigure(i % 2, weight=1)
            e = ctk.CTkEntry(f, font=ctk.CTkFont(weight="bold"))
            e.insert(0, name)
            e.pack(fill="x", padx=10, pady=(10, 6))
            card = FormatCard(f, "Match format", fmt)
            card.pack(fill="x", padx=10, pady=(0, 6))
            count = ctk.CTkLabel(f, text="", text_color=MUTED, anchor="w")
            count.pack(fill="x", padx=10)
            tb = ctk.CTkTextbox(f, height=120)
            if text:
                tb.insert("1.0", text)
            tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            tb.bind("<KeyRelease>", lambda _e: self._players_changed())
            self.group_frames.append((e, card, tb, count))
        self._players_changed()

    @staticmethod
    def _players(tb: ctk.CTkTextbox) -> list[str]:
        return [ln.strip() for ln in tb.get("1.0", "end").splitlines() if ln.strip()]

    def _players_changed(self) -> None:
        """Update the per-group player counts and the qualification options."""
        for _e, _card, tb, count in self.group_frames:
            k = len(self._players(tb))
            ok = Tournament.MIN_GROUP <= k <= Tournament.MAX_GROUP
            count.configure(text=f"Players (one per line, 3–5): {k}",
                            text_color=MUTED if ok or k == 0 else ERR_COLOR)
        self._update_qualification()

    # ---- qualification -------------------------------------------------------
    def _update_qualification(self) -> None:
        n = len(self.group_frames)
        sizes = [len(self._players(tb)) for _e, _c, tb, _l in self.group_frames]
        options = Tournament.advance_options(sizes)
        labels = {f"Top {a} → {ROUND_NAMES[Tournament.bracket_size(n, a)]}": a for a in options}
        if list(labels) != list(self.advance_choices):
            previous = self.advance_choices.get(self.advance.get(), 2)
            self.advance_choices = labels
            self.advance.configure(values=list(labels))
            self.advance.set(next((l for l, a in labels.items() if a == previous), next(iter(labels))))
        if len(options) > 1:
            self.advance.grid()
        else:
            self.advance.grid_remove()
        adv = self._advance()
        size = Tournament.bracket_size(n, adv)
        if n == 1:
            text = "The top 2 of the group play the Final."
        else:
            text = (f"Top {adv} of each group → {ROUND_NAMES[size]} ({size} players)"
                    + (", then the Final and a 3rd place match." if size >= 4 else "."))
        if n in (2, 4) and len(options) == 1:
            text += "\nTop 4 per group is available when every group has exactly 5 players."
        self.qual_info.configure(text=text)

    def _advance(self) -> int:
        return self.advance_choices.get(self.advance.get(), 2)

    def _create(self) -> None:
        names = [e.get().strip() for e, _c, _t, _l in self.group_frames]
        try:
            if len(set(names)) != len(names):
                raise TournamentError("Group names must be unique")
            groups = {nm: self._players(tb) for nm, (_e, _c, tb, _l) in zip(names, self.group_frames)}
            formats = {nm: card.get() for nm, (_e, card, _t, _l) in zip(names, self.group_frames)}
            self.app.ctrl.new_tournament(self.name.get(), groups, formats,
                                         self.playoff_fmt.get(), self._advance())
            self.error.configure(text="")
        except (TournamentError, ValueError) as e:
            self.error.configure(text=str(e))


# --------------------------------------------------------------------------- #
class GroupStageView(ctk.CTkFrame):
    COLS = ("rank", "player", "p", "w", "l", "gw", "gl", "gdiff")
    HEAD = ("#", "Player", "P", "W", "L", "Games Won", "Games Lost", "Game Diff")

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        t = app.ctrl.tournament
        self.rows: dict[str, ScoreRow] = {}
        self.tables: list[ttk.Treeview] = []
        self.round_headers: list[tuple] = []   # (label, group, round)
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        for g in t.groups:
            tab = self.tabs.add(g.name)
            tab.grid_columnconfigure(0, weight=3)
            tab.grid_columnconfigure(1, weight=2)
            tab.grid_rowconfigure(0, weight=1)
            fmt = g.fmt
            sched = ctk.CTkScrollableFrame(tab, label_text=f"Schedule  ·  {fmt.describe()}")
            sched.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            for r in g.rounds:
                hdr = ctk.CTkLabel(sched, text="", font=ctk.CTkFont(weight="bold"))
                hdr.pack(anchor="w", pady=(8, 2))
                self.round_headers.append((hdr, g, r))
                for m in g.matches_in_round(r):
                    row = ScoreRow(sched, app.ctrl, m)
                    row.pack(fill="x", pady=2)
                    self.rows[m.id] = row
            right = ctk.CTkFrame(tab)
            right.grid(row=0, column=1, sticky="nsew")
            ctk.CTkLabel(right, text="Live standings", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=6)
            tv = ttk.Treeview(right, columns=self.COLS, show="headings", height=10, style="Standings.Treeview")
            for c, h in zip(self.COLS, self.HEAD):
                tv.heading(c, text=h)
                tv.column(c, width=140 if c == "player" else (85 if c.startswith("g") else 45),
                          anchor="w" if c == "player" else "center")
            tv.tag_configure("q", background="#1f6aa5", foreground="white")
            tv.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            tv.group = g
            self.tables.append(tv)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(0, 10))
        self.progress = ctk.CTkProgressBar(bar)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_lbl = ctk.CTkLabel(bar, text="")
        self.progress_lbl.pack(side="left", padx=6)
        first_round = ROUND_NAMES[t.playoff_size]
        self.next_btn = ctk.CTkButton(bar, text=f"Go to the {first_round} ▶", command=self._go)
        self.next_btn.pack(side="right")
        self.refresh()

    def _qualifiers_per_group(self) -> int:
        return self.app.ctrl.tournament.qualifiers_per_group

    def refresh(self) -> None:
        t = self.app.ctrl.tournament
        for m in t.all_matches():
            if m.id in self.rows:
                self.rows[m.id].update_from(m)
        for lbl, g, r in self.round_headers:
            rest = g.resting.get(r)
            text = f"Round {r}" + (f"   ·   resting: {', '.join(rest)}" if rest else "")
            if t.knockout is None and not g.round_is_open(r):
                text += f"   🔒 enter all round {g.current_round} scores first"
            lbl.configure(text=text, text_color=MUTED if "🔒" in text else ("gray10", "gray90"))
        q = self._qualifiers_per_group()
        for tv in self.tables:
            tv.delete(*tv.get_children())
            for r in tv.group.standings():
                tv.insert("", "end", values=(r.rank, r.name, r.played, r.wins, r.losses,
                                             r.games_won, r.games_lost, f"{r.game_diff:+d}"),
                          tags=("q",) if r.rank <= q else ())
        ms = [m for g in t.groups for m in g.matches]
        done = sum(m.is_played for m in ms)
        self.progress.set(done / len(ms))
        self.progress_lbl.configure(text=f"{done}/{len(ms)} matches")
        self.next_btn.configure(state="normal" if t.group_stage_complete else "disabled")

    def _go(self) -> None:
        try:
            self.app.ctrl.start_playoffs()
            self.app.show("playoffs")
        except TournamentError as e:
            messagebox.showwarning("Not yet", str(e))


# --------------------------------------------------------------------------- #
class PlayoffView(ctk.CTkFrame):
    """Bracket drawn from the knockout's rounds: one column per round, each
    match centred between the two matches that feed it."""

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        t = app.ctrl.tournament
        ko = t.knockout
        ctk.CTkLabel(self, text=f"Playoffs · {ko.size} players · {t.playoff_fmt.describe()}",
                     text_color=MUTED).pack(pady=(6, 0))
        board = ctk.CTkScrollableFrame(self)
        board.pack(fill="both", expand=True, padx=20, pady=10)
        rounds = ko.rounds
        first = len(rounds[0][1])                     # matches in the first round
        self.rows: dict[str, ScoreRow] = {}
        for col, (name, ids) in enumerate(rounds):
            board.grid_columnconfigure(col, weight=1, uniform="round")
            ctk.CTkLabel(board, text=name, font=ctk.CTkFont(size=16, weight="bold")).grid(
                row=0, column=col, pady=8)
            span = first // len(ids)
            for j, mid in enumerate(ids):
                row = ScoreRow(board, app.ctrl, ko.matches[mid], title=Knockout.label(mid))
                row.grid(row=1 + j * span, column=col, rowspan=span, sticky="ew", padx=8, pady=6)
                self.rows[mid] = row
        last = len(rounds) - 1
        if "3P" in ko.matches:
            row = ScoreRow(board, app.ctrl, ko.matches["3P"], title=Knockout.label("3P"))
            row.grid(row=1 + first, column=last, sticky="ew", padx=8, pady=(24, 6))
            self.rows["3P"] = row
        board.grid_columnconfigure(last + 1, weight=1, uniform="round")
        self.champ = ctk.CTkLabel(board, text="", font=ctk.CTkFont(size=22, weight="bold"), text_color=GOLD)
        self.champ.grid(row=1, column=last + 1, rowspan=first)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(bar, text="◀ Back to groups", fg_color="gray40",
                      command=lambda: app.show("groups")).pack(side="left")
        ctk.CTkButton(bar, text="Reopen group stage", fg_color="gray30", command=self._reopen).pack(side="left", padx=8)
        self.podium_btn = ctk.CTkButton(bar, text="🏆 Podium", command=lambda: app.show("podium"))
        self.podium_btn.pack(side="right")
        self.refresh()

    def _reopen(self) -> None:
        if messagebox.askyesno("Reopen", "This discards all playoff results. Continue?"):
            self.app.ctrl.reopen_groups()
            self.app.show("groups")

    def refresh(self) -> None:
        ko = self.app.ctrl.tournament.knockout
        if not ko:
            return
        for mid, row in self.rows.items():
            row.update_from(ko.matches[mid])
        f = ko.matches["F"]
        self.champ.configure(text=f"🏆\n{f.winner}" if f.winner else "🏆\n?")
        self.podium_btn.configure(state="normal" if ko.podium else "disabled")


# --------------------------------------------------------------------------- #
class PodiumView(ctk.CTkFrame):
    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        champ, runner, third = app.ctrl.tournament.knockout.podium
        ctk.CTkLabel(self, text=f"🎉 {app.ctrl.tournament.name} 🎉",
                     font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(30, 10))
        stage = ctk.CTkFrame(self, fg_color="transparent")
        stage.pack(expand=True)
        places = [(runner, "🥈 Runner-up", SILVER, 160), (champ, "🥇 Champion", GOLD, 240)]
        if third:                                    # no 3rd-place match when 2 players qualify
            places.append((third, "🥉 3rd place", BRONZE, 110))
        for col, (name, medal, color, h) in enumerate(places):
            box = ctk.CTkFrame(stage, fg_color="transparent")
            box.grid(row=0, column=col, padx=10, sticky="s")
            ctk.CTkLabel(box, text=name, font=ctk.CTkFont(size=22 if col == 1 else 18, weight="bold")).pack()
            block = ctk.CTkFrame(box, width=170, height=h, fg_color=color, corner_radius=6)
            block.pack(pady=(6, 0))
            block.pack_propagate(False)
            ctk.CTkLabel(block, text=medal, text_color="black",
                         font=ctk.CTkFont(size=16, weight="bold")).pack(expand=True)
        ctk.CTkButton(self, text="◀ Back to bracket", command=lambda: app.show("playoffs")).pack(pady=20)


# --------------------------------------------------------------------------- #
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title("Tennis Tournament Manager")
        self.geometry("1150x720")
        self.minsize(900, 600)
        self._style_treeview()
        self.ctrl = TournamentController()
        self.ctrl.subscribe(self._on_change)
        self.current: ctk.CTkFrame | None = None
        self.screen = ""

        header = ctk.CTkFrame(self, height=50, corner_radius=0)
        header.pack(fill="x")
        self.title_lbl = ctk.CTkLabel(header, text="🎾 Tennis Tournament Manager",
                                      font=ctk.CTkFont(size=18, weight="bold"))
        self.title_lbl.pack(side="left", padx=14, pady=10)
        for txt, cmd in (("New", lambda: self.show("setup")), ("Open…", self.load), ("Save…", self.save)):
            ctk.CTkButton(header, text=txt, width=80, command=cmd).pack(side="right", padx=4)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        self.bind_all("<Control-s>", lambda e: self.save())
        self.show("setup")

    def _style_treeview(self) -> None:
        s = ttk.Style()
        s.theme_use("clam")
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2b2b2b", "#dce4ee") if dark else ("#f5f5f5", "#1a1a1a")
        s.configure("Standings.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                    rowheight=28, borderwidth=0, font=("Segoe UI", 11))
        s.configure("Standings.Treeview.Heading", background="#1f538d", foreground="white",
                    relief="flat", font=("Segoe UI", 11, "bold"))

    def show(self, screen: str) -> None:
        if self.current is not None:
            self.current.destroy()
        views = {"setup": SetupView, "groups": GroupStageView, "playoffs": PlayoffView, "podium": PodiumView}
        self.screen = screen
        self.current = views[screen](self.body, self)
        self.current.pack(fill="both", expand=True)
        t = self.ctrl.tournament
        self.title_lbl.configure(text=f"🎾 {t.name}" if t and screen != "setup" else "🎾 Tennis Tournament Manager")

    def _on_change(self) -> None:
        t = self.ctrl.tournament
        if self.screen == "setup" and t:
            self.show("playoffs" if t.knockout else "groups")
        elif hasattr(self.current, "refresh"):
            self.current.refresh()

    def save(self) -> None:
        if not self.ctrl.tournament:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Tournament", "*.json")])
        if path:
            self.ctrl.save(path)

    def load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Tournament", "*.json")])
        if not path:
            return
        try:
            self.ctrl.load(path)
        except Exception as e:  # corrupt / foreign file
            messagebox.showerror("Could not open", str(e))
            return
        t = self.ctrl.tournament
        self.show("podium" if t.knockout and t.knockout.podium else "playoffs" if t.knockout else "groups")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
