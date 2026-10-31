"""CustomTkinter front-end: Setup -> Group Stage -> Playoffs -> Podium."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ..core import MatchFormat, ScoreError, TournamentError
from ..core.models import Knockout, Match
from .controller import TournamentController

OK_COLOR, ERR_COLOR, MUTED = "#2fa572", "#d9534f", "gray60"
GOLD, SILVER, BRONZE = "#d4af37", "#c0c0c0", "#cd7f32"


# --------------------------------------------------------------------------- #
class ScoreRow(ctk.CTkFrame):
    """One match: names, score entry with live validation, status icon."""

    def __init__(self, master, ctrl: TournamentController, match: Match, title: str = "",
                 locked: bool = False):
        super().__init__(master, corner_radius=8)
        self.ctrl, self.match_id = ctrl, match.id
        self.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=MUTED).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 0))
        self.names = ctk.CTkLabel(self, anchor="w")
        self.names.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        self.var = tk.StringVar(value=str(match.score) if match.score else "")
        self.entry = ctk.CTkEntry(self, textvariable=self.var, width=150,
                                  placeholder_text="6-4 3-6 7-5")
        self.entry.grid(row=1, column=1, padx=4)
        self.status = ctk.CTkLabel(self, text="", width=24)
        self.status.grid(row=1, column=2, padx=(0, 10))
        self.msg = ctk.CTkLabel(self, text="", text_color=ERR_COLOR, font=ctk.CTkFont(size=11))
        self.msg.grid(row=2, column=0, columnspan=3, sticky="w", padx=10)
        self.msg.grid_remove()
        self.entry.bind("<Return>", self._commit)
        self.entry.bind("<FocusOut>", self._commit)
        self.var.trace_add("write", lambda *_: self._live_check())
        self.update_from(match, locked)

    def update_from(self, m: Match, locked: bool = False) -> None:
        p1, p2 = m.p1 or "TBD", m.p2 or "TBD"
        if m.winner:
            p1 = f"★ {p1}" if m.winner == m.p1 else p1
            p2 = f"★ {p2}" if m.winner == m.p2 else p2
        self.names.configure(text=f"{p1}   vs   {p2}")
        state = "normal" if m.is_ready and not locked else "disabled"
        self.entry.configure(state=state)
        try:
            editing = self.focus_get() is self.entry._entry
        except (KeyError, tk.TclError):
            editing = False
        if not editing:
            self.var.set(str(m.score) if m.score else "")
        self.status.configure(text="✔" if m.is_played else "", text_color=OK_COLOR)

    def _live_check(self) -> None:
        from ..core import parse_score
        txt = self.var.get().strip()
        fmt = self.ctrl.tournament.fmt
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
        if self.var.get().strip() == (str(m.score) if m.score else ""):
            return
        try:
            self.ctrl.record_score(self.match_id, self.var.get())
        except (ScoreError, TournamentError):
            pass  # message already shown by live validation


# --------------------------------------------------------------------------- #
class SetupView(ctk.CTkScrollableFrame):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app
        self.group_frames: list[tuple[ctk.CTkEntry, ctk.CTkTextbox]] = []
        ctk.CTkLabel(self, text="🎾 New Tournament", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(10, 4))
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(top, text="Name").grid(row=0, column=0, padx=8, pady=8)
        self.name = ctk.CTkEntry(top, width=220)
        self.name.insert(0, "Club Championship")
        self.name.grid(row=0, column=1, padx=8)
        ctk.CTkLabel(top, text="Groups").grid(row=0, column=2, padx=8)
        self.n_groups = ctk.CTkSegmentedButton(top, values=["1", "2", "4"], command=self._rebuild)
        self.n_groups.set("2")
        self.n_groups.grid(row=0, column=3, padx=8)
        ctk.CTkLabel(top, text="Best of").grid(row=1, column=0, padx=8, pady=8)
        self.best_of = ctk.CTkSegmentedButton(top, values=["1", "3", "5"])
        self.best_of.set("3")
        self.best_of.grid(row=1, column=1, sticky="w", padx=8)
        self.track_games = ctk.CTkSwitch(top, text="Enter game scores (6-4 …)")
        self.track_games.select()
        self.track_games.grid(row=1, column=2, columnspan=2, sticky="w", padx=8)
        self.super_tb = ctk.CTkSwitch(top, text="Deciding set = 10-pt super tie-break")
        self.super_tb.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))

        self.groups_box = ctk.CTkFrame(self, fg_color="transparent")
        self.groups_box.pack(fill="both", expand=True, padx=20)
        self.error = ctk.CTkLabel(self, text="", text_color=ERR_COLOR)
        self.error.pack()
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(pady=10)
        ctk.CTkButton(bar, text="Load saved…", fg_color="gray40", command=app.load).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Create tournament ▶", command=self._create).pack(side="left", padx=6)
        self._rebuild("2")

    def _rebuild(self, n: str) -> None:
        for w in self.groups_box.winfo_children():
            w.destroy()
        self.group_frames.clear()
        for i in range(int(n)):
            f = ctk.CTkFrame(self.groups_box)
            f.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="nsew")
            self.groups_box.grid_columnconfigure(i % 2, weight=1)
            e = ctk.CTkEntry(f)
            e.insert(0, f"Group {chr(65 + i)}")
            e.pack(fill="x", padx=10, pady=(10, 4))
            ctk.CTkLabel(f, text="Players (one per line, 3–8)", text_color=MUTED).pack(anchor="w", padx=10)
            tb = ctk.CTkTextbox(f, height=150)
            tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.group_frames.append((e, tb))

    def _create(self) -> None:
        groups = {e.get(): tb.get("1.0", "end").splitlines() for e, tb in self.group_frames}
        try:
            fmt = MatchFormat(int(self.best_of.get()), bool(self.track_games.get()),
                              bool(self.super_tb.get()))
            if len(groups) != len(self.group_frames):
                raise TournamentError("Group names must be unique")
            self.app.ctrl.new_tournament(self.name.get(), groups, fmt)
            self.error.configure(text="")
        except (TournamentError, ValueError) as e:
            self.error.configure(text=str(e))


# --------------------------------------------------------------------------- #
class GroupStageView(ctk.CTkFrame):
    COLS = ("rank", "player", "p", "w", "l", "sw", "sl", "diff", "gdiff")
    HEAD = ("#", "Player", "P", "W", "L", "Sets W", "Sets L", "Diff", "Games ±")

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        t = app.ctrl.tournament
        self.rows: dict[str, ScoreRow] = {}
        self.tables: list[ttk.Treeview] = []
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        locked = t.knockout is not None
        for g in t.groups:
            tab = self.tabs.add(g.name)
            tab.grid_columnconfigure(0, weight=3)
            tab.grid_columnconfigure(1, weight=2)
            tab.grid_rowconfigure(0, weight=1)
            sched = ctk.CTkScrollableFrame(tab, label_text="Schedule")
            sched.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            for r in g.rounds:
                rest = g.resting.get(r)
                hdr = f"Round {r}" + (f"   ·   resting: {', '.join(rest)}" if rest else "")
                ctk.CTkLabel(sched, text=hdr, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(8, 2))
                for m in g.matches_in_round(r):
                    row = ScoreRow(sched, app.ctrl, m, locked=locked)
                    row.pack(fill="x", pady=2)
                    self.rows[m.id] = row
            right = ctk.CTkFrame(tab)
            right.grid(row=0, column=1, sticky="nsew")
            ctk.CTkLabel(right, text="Live standings", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=6)
            tv = ttk.Treeview(right, columns=self.COLS, show="headings", height=10, style="Standings.Treeview")
            for c, h in zip(self.COLS, self.HEAD):
                tv.heading(c, text=h)
                tv.column(c, width=150 if c == "player" else 55, anchor="w" if c == "player" else "center")
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
        self.next_btn = ctk.CTkButton(bar, text="Go to playoffs ▶", command=self._go)
        self.next_btn.pack(side="right")
        self.refresh()

    def _qualifiers_per_group(self) -> int:
        return {1: 4, 2: 2, 4: 1}[len(self.app.ctrl.tournament.groups)]

    def refresh(self) -> None:
        t = self.app.ctrl.tournament
        locked = t.knockout is not None
        for m in t.all_matches():
            if m.id in self.rows:
                self.rows[m.id].update_from(m, locked)
        q = self._qualifiers_per_group()
        for tv in self.tables:
            tv.delete(*tv.get_children())
            for r in tv.group.standings():
                tv.insert("", "end", values=(r.rank, r.player, r.played, r.wins, r.losses, r.sets_won,
                                             r.sets_lost, f"{r.set_diff:+d}", f"{r.game_diff:+d}"),
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
    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        ko = app.ctrl.tournament.knockout
        board = ctk.CTkFrame(self)
        board.pack(fill="both", expand=True, padx=20, pady=10)
        for c in range(3):
            board.grid_columnconfigure(c, weight=1)
        for c, h in enumerate(("Semi-Finals", "Finals", "")):
            ctk.CTkLabel(board, text=h, font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=c, pady=8)
        self.rows: dict[str, ScoreRow] = {}
        layout = {"SF1": (1, 0), "SF2": (3, 0), "F": (1, 1), "3P": (3, 1)}
        for mid, (r, c) in layout.items():
            row = ScoreRow(board, app.ctrl, ko.matches[mid], title=Knockout.LABELS[mid])
            row.grid(row=r, column=c, sticky="ew", padx=16, pady=24)
            self.rows[mid] = row
        ctk.CTkLabel(board, text="→", font=ctk.CTkFont(size=30)).grid(row=2, column=0, columnspan=2)
        self.champ = ctk.CTkLabel(board, text="", font=ctk.CTkFont(size=22, weight="bold"), text_color=GOLD)
        self.champ.grid(row=1, column=2, rowspan=3)
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
        for col, (name, medal, color, h) in enumerate(((runner, "🥈 Runner-up", SILVER, 160),
                                                         (champ, "🥇 Champion", GOLD, 240),
                                                         (third, "🥉 3rd place", BRONZE, 110))):
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
