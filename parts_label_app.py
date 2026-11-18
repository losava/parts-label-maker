#!/usr/bin/env python3
"""Parts Label — shop floor window.

Double-click MakePartsLabel.bat to open this app.
The console generator is still available: python make_parts_label.py
"""

import os
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError:
    Image = ImageDraw = ImageFont = ImageTk = None

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import make_parts_label as eng  # noqa: E402
import updater  # noqa: E402

try:
    from version import __version__
except ImportError:
    __version__ = "0.0.0"

BG = "#14181d"
PANEL = "#1e242c"
CARD = "#262d36"
INK = "#f4f1ea"
MUTED = "#9aa3ad"
AMBER = "#f0a202"
GREEN = "#3dcc7a"
LINE = "#3a4450"
BLUE = "#6cb6ff"


class LabelApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Parts Label {__version__}")
        self.geometry("1280x980")
        self.minsize(1180, 860)
        self.after(10, self._center_window)
        self.configure(bg=BG)
        self.parts = eng.load_parts_lookup()
        self.last = None
        self.busy = False

        self.part_var = tk.StringVar()
        self.header_var = tk.StringVar()
        self.price_var = tk.StringVar()
        self.qty_var = tk.StringVar(value="1")
        self.printer_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")

        self._style()
        self._build()
        self.part_entry.focus_set()
        n = len(self.parts)
        self._log(f"Parts list loaded — {n} part{'s' if n != 1 else ''}.")
        parts_path = eng.find_parts_csv()
        if parts_path:
            self._log(f"Parts list file: {parts_path}")
        else:
            remembered = eng.configured_parts_csv()
            if remembered:
                self._log(f"Parts list file is missing: {remembered}")
            else:
                self._log("No parts list selected yet.")
        self._log("Type a part number and press Enter to look it up.")
        self.after(120, self.draw_preview)
        self.after(200, self.refresh_printers)
        self._parts_mtime = self._parts_file_mtime()
        self.after(3000, self._watch_parts)
        self._update_busy = False
        self._update_win = None
        self._parts_prompt = None
        self.after(600, self._maybe_choose_parts_list)
        self.after(2500, self._startup_update_check)

    def _dance(self) -> None:
        import math
        c = self.dance
        c.delete("all")
        t = self._dance_t
        bob = math.sin(t * 0.28) * 5
        sway = math.sin(t * 0.28) * 6
        kick = math.sin(t * 0.55) * 5
        x = 30 + sway
        y = 10 + bob
        c.create_rectangle(x, y, x + 36, y + 26, fill="white", outline=AMBER, width=2)
        c.create_rectangle(x, y, x + 36, y + 7, fill="#111", outline="")
        c.create_text(x + 18, y + 4, text="LABEL", fill="white", font=("Segoe UI", 5, "bold"))
        bx = x + 4
        for w in (2, 1, 3, 1, 2, 1, 3, 2, 1):
            c.create_rectangle(bx, y + 12, bx + w, y + 22, fill="#111", outline="")
            bx += w + 1
        wave = math.sin(t * 0.45) * 8
        colors = [AMBER, "#ff4d4d", "#4dff88", "#4db8ff", "#ff66cc", "#ffffff"]
        left_c = colors[(t // 4) % len(colors)]
        right_c = colors[((t // 4) + 3) % len(colors)]
        c.create_line(x, y + 12, x - 10, y + 8 - wave, fill=AMBER, width=2)
        c.create_oval(x - 18, y + 1 - wave, x - 6, y + 13 - wave, fill=left_c, outline="")
        c.create_line(x + 36, y + 12, x + 46, y + 8 + wave, fill=AMBER, width=2)
        c.create_oval(x + 42, y + 1 + wave, x + 54, y + 13 + wave, fill=right_c, outline="")
        c.create_line(x + 10, y + 26, x + 8 - kick, y + 36, fill=AMBER, width=2)
        c.create_line(x + 26, y + 26, x + 28 + kick, y + 36, fill=AMBER, width=2)
        self._dance_t += 1
        self.after(45, self._dance)

    def _fireworks(self) -> None:
        import math
        import random
        if getattr(self, "_boom_win", None) is not None:
            try:
                self._boom_win.destroy()
            except Exception:
                pass
            self._boom_win = None
        self.update_idletasks()
        w = max(self.winfo_width(), 400)
        h = max(self.winfo_height(), 300)
        x = self.winfo_rootx()
        y = self.winfo_rooty()
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", "#010101")
        except tk.TclError:
            pass
        win.geometry(f"{w}x{h}+{x}+{y}")
        c = tk.Canvas(win, width=w, height=h, bg="#010101", highlightthickness=0)
        c.pack()
        self._boom_win = win
        colors = [AMBER, "#ff4d4d", "#4dff88", "#4db8ff", "#ff66cc", "#ffffff", GREEN, "#ffd000"]
        bursts = []
        for _ in range(8):
            cx = random.randint(60, w - 60)
            cy = random.randint(30, max(40, int(h * 0.6)))
            bits = []
            for _p in range(36):
                ang = random.random() * math.pi * 2
                spd = random.uniform(3.0, 8.0)
                bits.append([
                    float(cx), float(cy),
                    math.cos(ang) * spd, math.sin(ang) * spd,
                    random.choice(colors), random.randint(3, 6),
                ])
            bursts.append(bits)
        state = {"n": 0}

        def tick():
            if self._boom_win is not win:
                return
            try:
                c.delete("all")
            except tk.TclError:
                return
            for bits in bursts:
                for p in bits:
                    p[0] += p[2]
                    p[1] += p[3]
                    p[3] += 0.12
                    p[2] *= 0.99
                    size = p[5]
                    c.create_oval(
                        p[0] - size, p[1] - size, p[0] + size, p[1] + size,
                        fill=p[4], outline=p[4],
                    )
            state["n"] += 1
            if state["n"] < 45:
                self.after(28, tick)
            else:
                try:
                    win.destroy()
                except tk.TclError:
                    pass
                self._boom_win = None

        tick()

    def _center_window(self) -> None:
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = 0
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Printer.TCombobox",
            fieldbackground=CARD,
            background=CARD,
            foreground=INK,
            arrowcolor=INK,
        )
        style.map("Printer.TCombobox", fieldbackground=[("readonly", CARD)])

    def _build(self) -> None:
        self._build_menu()
        top = tk.Frame(self, bg="#0f1318", height=72)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(
            top, text="PARTS LABEL", bg="#0f1318", fg=AMBER,
            font=("Segoe UI", 22, "bold"),
        ).pack(side="left", padx=22, pady=14)
        tk.Label(
            top, text="3 × 2 in   ·   Code 128   ·   GC420d",
            bg="#0f1318", fg=MUTED, font=("Segoe UI", 11),
        ).pack(side="left", pady=18)
        tk.Label(
            top, textvariable=self.status_var, bg="#0f1318", fg=GREEN,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="right", padx=22)
        self.dance = tk.Canvas(top, width=96, height=56, bg="#0f1318", highlightthickness=0, cursor="hand2")
        self.dance.pack(side="right", padx=(0, 4))
        self.dance.bind("<Button-1>", lambda e: self._fireworks())
        self._btn(top, "UPDATES", lambda: self.check_for_updates(manual=True), "#3a4450", INK).pack(
            side="right", padx=(0, 8)
        )
        self._dance_t = 0
        self._boom = None
        self.after(200, self._dance)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        form = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        form.pack(side="left", fill="both", expand=True, padx=(0, 12))

        def field_label(parent, text):
            tk.Label(
                parent, text=text, bg=PANEL, fg=MUTED,
                font=("Segoe UI", 9, "bold"), anchor="w",
            ).pack(fill="x", padx=18, pady=(14, 4))

        field_label(form, "PART NUMBER")
        row = tk.Frame(form, bg=PANEL)
        row.pack(fill="x", padx=18)
        self.part_entry = tk.Entry(
            row, textvariable=self.part_var, bg=CARD, fg=INK, insertbackground=AMBER,
            relief="flat", font=("Consolas", 16), highlightthickness=1,
            highlightbackground=LINE, highlightcolor=AMBER,
        )
        self.part_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.part_entry.bind("<Return>", lambda e: self.lookup())
        self.part_entry.bind("<FocusOut>", lambda e: self.lookup())
        self._add_edit_menu(self.part_entry)
        self._last_looked = ""
        self.part_var.trace_add("write", self._force_part_upper)
        self._btn(row, "LOOK UP", self.lookup, AMBER, "#1b1f24").pack(side="left", padx=(8, 0))
        self._btn(row, "REFRESH LIST", lambda: self.reload_parts(manual=True), "#3a4450", INK).pack(side="left", padx=(8, 0))

        field_label(form, "DESCRIPTION")
        self.desc = tk.Text(
            form, height=3, bg=CARD, fg=INK, insertbackground=AMBER,
            relief="flat", font=("Segoe UI", 13), wrap="word",
            highlightthickness=1, highlightbackground=LINE, highlightcolor=AMBER,
        )
        self.desc.pack(fill="x", padx=18, ipady=6)
        self._add_edit_menu(self.desc)

        mid = tk.Frame(form, bg=PANEL)
        mid.pack(fill="x", padx=18)
        left = tk.Frame(mid, bg=PANEL)
        left.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right = tk.Frame(mid, bg=PANEL)
        right.pack(side="left", fill="x", expand=True, padx=(8, 0))

        tk.Label(left, text="HEADER", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(14, 4))
        self.header_entry = tk.Entry(
            left, textvariable=self.header_var, bg=CARD, fg=INK, insertbackground=AMBER,
            relief="flat", font=("Segoe UI", 14), highlightthickness=1,
            highlightbackground=LINE, highlightcolor=AMBER,
        )
        self.header_entry.pack(fill="x", ipady=8)
        self._add_edit_menu(self.header_entry)

        tk.Label(right, text="PRICE", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(14, 4))
        self.price_entry = tk.Entry(
            right, textvariable=self.price_var, bg=CARD, fg=INK, insertbackground=AMBER,
            relief="flat", font=("Segoe UI", 14), highlightthickness=1,
            highlightbackground=LINE, highlightcolor=AMBER,
        )
        self.price_entry.pack(fill="x", ipady=8)
        self._add_edit_menu(self.price_entry)

        qty_row = tk.Frame(form, bg=PANEL)
        qty_row.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(qty_row, text="QUANTITY", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.qty_box = tk.Spinbox(
            qty_row, from_=1, to=99, textvariable=self.qty_var, width=6,
            bg=CARD, fg=INK, buttonbackground=CARD, relief="flat",
            font=("Segoe UI", 14), justify="center",
        )
        self.qty_box.pack(side="left", padx=12, ipady=4)
        self._add_edit_menu(self.qty_box)

        pr_row = tk.Frame(form, bg=PANEL)
        pr_row.pack(fill="x", padx=18, pady=(8, 0))
        tk.Label(pr_row, text="PRINTER", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.printer_box = ttk.Combobox(
            pr_row, textvariable=self.printer_var, state="readonly",
            font=("Segoe UI", 11), width=46, style="Printer.TCombobox",
        )
        self.printer_box.pack(side="left", padx=12, ipady=3)
        self.printer_box.bind("<<ComboboxSelected>>", lambda e: self._note_printer())
        self._btn(pr_row, "SET DEFAULT", self._save_printer, AMBER, "#1b1f24").pack(side="left", padx=(0, 8))
        self._btn(pr_row, "REFRESH", self.refresh_printers, "#3a4450", INK).pack(side="left")

        btns = tk.Frame(form, bg=PANEL)
        btns.pack(fill="x", padx=18, pady=16)
        self._btn(btns, "PRINT", lambda: self.run(print_it=True), GREEN, "#102418").pack(side="left", padx=(0, 8))
        self._btn(btns, "UPDATE ONLY", lambda: self.run(print_it=False), BLUE, "#102030").pack(side="left", padx=(0, 8))
        self._btn(btns, "REPRINT LAST", self.reprint, AMBER, "#1b1f24").pack(side="left", padx=(0, 8))
        self._btn(btns, "EDIT LAST", self.edit_last, BLUE, "#102030").pack(side="left", padx=(0, 8))
        self._btn(btns, "CLEAR", self.clear_form, "#3a4450", INK).pack(side="left")

        side = tk.Frame(body, bg=PANEL, width=430, highlightbackground=LINE, highlightthickness=1)
        side.pack(side="right", fill="both")
        side.pack_propagate(False)
        tk.Label(
            side, text="LABEL PREVIEW", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))
        self.preview = tk.Canvas(side, width=400, height=280, bg="#1e242c", highlightthickness=0)
        self.preview.pack(padx=12, pady=(0, 4))
        self.preview.bind("<Button-1>", lambda e: self._bulk_step(1))
        self._preview_photo = None
        self._preview_job = None
        self.bulk_view = []
        self.bulk_index = 0

        nav = tk.Frame(side, bg=PANEL)
        nav.pack(fill="x", padx=12, pady=(0, 6))
        self._btn(nav, "PREV", lambda: self._bulk_step(-1), "#3a4450", INK).pack(side="left")
        self.bulk_pos = tk.StringVar(value="")
        tk.Label(nav, textvariable=self.bulk_pos, bg=PANEL, fg=AMBER, font=("Segoe UI", 10, "bold")).pack(side="left", expand=True)
        self._btn(nav, "NEXT", lambda: self._bulk_step(1), "#3a4450", INK).pack(side="right")

        tk.Label(
            side, text="ACTIVITY", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(16, 6))
        self.log = tk.Text(
            side, bg="#12161b", fg=INK, relief="flat", font=("Consolas", 10),
            wrap="word", height=12, state="disabled",
        )
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.draw_preview()

        self.part_var.trace_add("write", lambda *_: self.draw_preview())
        self.header_var.trace_add("write", lambda *_: self.draw_preview())
        self.price_var.trace_add("write", lambda *_: self.draw_preview())
        self.desc.bind("<KeyRelease>", lambda e: self.draw_preview())

        bulk = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        bulk.pack(fill="x", padx=18, pady=(0, 14))
        tk.Label(
            bulk, text="BULK PASTE", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(
            bulk,
            text="One part per line. Looks up the part first. Saved description/price are kept. Only new parts are added. Qty in ( ).",
            bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w",
        ).pack(fill="x", padx=14)
        self.bulk = tk.Text(
            bulk, height=6, bg=CARD, fg=INK, insertbackground=AMBER,
            relief="flat", font=("Consolas", 11), wrap="none",
            highlightthickness=1, highlightbackground=LINE, highlightcolor=AMBER,
        )
        self.bulk.pack(fill="x", padx=14, pady=8)
        self._add_edit_menu(self.bulk)
        brow = tk.Frame(bulk, bg=PANEL)
        brow.pack(fill="x", padx=14, pady=(0, 12))
        self._btn(brow, "LOOK UP", self.lookup_bulk, AMBER, "#1b1f24").pack(side="left", padx=(0, 8))
        self._btn(brow, "PRINT ALL", lambda: self.run_bulk(True), GREEN, "#102418").pack(side="left", padx=(0, 8))
        self._btn(brow, "PRINT 1 EACH", lambda: self.run_bulk(True, one_each=True), AMBER, "#1b1f24").pack(side="left", padx=(0, 8))
        self._btn(brow, "UPDATE ALL", lambda: self.run_bulk(False), BLUE, "#102030").pack(side="left", padx=(0, 8))
        self._btn(brow, "CLEAR LIST", self._clear_bulk, "#3a4450", INK).pack(side="left")

    def _clear_bulk(self) -> None:
        self.bulk.delete("1.0", "end")
        self.bulk_view = []
        self.bulk_index = 0
        self.bulk_pos.set("")

    def _parts_file_mtime(self):
        try:
            path = eng.find_parts_csv()
            return (path, os.path.getmtime(path)) if path else None
        except Exception:
            return None

    def reload_parts(self, manual: bool = False) -> None:
        """Re-read the parts database from disk."""
        try:
            new_parts = eng.load_parts_lookup()
        except Exception as e:
            self._log(f"Refresh failed: {e}")
            return
        if not new_parts and self.parts:
            # File mid-write or unreadable; keep what we have and try again later.
            if manual:
                self._log("Refresh: parts list was empty or busy, kept current list.")
            return
        old_n = len(self.parts)
        self.parts = new_parts
        self._part_index_n = None
        self._parts_mtime = self._parts_file_mtime()
        n = len(self.parts)
        self._log(f"Parts list {'refreshed' if manual else 'auto-refreshed'} - {n} parts ({n - old_n:+d}).")
        if manual:
            self.status_var.set("Parts list refreshed")
            if self.part_var.get().strip():
                self._last_looked = ""
                self.lookup()

    def _watch_parts(self) -> None:
        try:
            current = self._parts_file_mtime()
            if current != self._parts_mtime and not self.busy:
                self.reload_parts(manual=False)
        finally:
            self.after(3000, self._watch_parts)

    def _ensure_part_index(self) -> None:
        import re
        if getattr(self, "_part_index_n", None) == len(self.parts):
            return
        space_index = {}
        nospace_index = {}
        for key, entry in self.parts.items():
            collapsed = re.sub(r"\s+", " ", key).strip()
            space_index.setdefault(collapsed, (key, entry))
            nospace_index.setdefault(re.sub(r"\s+", "", collapsed), (key, entry))
        self._space_index = space_index
        self._nospace_index = nospace_index
        self._part_index_n = len(self.parts)

    def _find_part(self, pn: str):
        """Match a part even if spacing differs. Returns (saved part number, entry)."""
        import re
        pn = eng.normalize_part_number(pn)
        if not pn:
            return None
        self._ensure_part_index()
        if pn in self.parts:
            return pn, self.parts[pn]
        collapsed = re.sub(r"\s+", " ", pn).strip()
        hit = self._space_index.get(collapsed)
        if hit:
            return hit
        hit = self._nospace_index.get(re.sub(r"\s+", "", collapsed))
        if hit:
            return hit
        dash = re.sub(r"\s*-\s*", "-", collapsed)
        for key, entry in self.parts.items():
            stored = re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", key))
            if stored == dash:
                return key, entry
        return None

    def _resolve_rows(self, rows: list[dict]) -> list[dict]:
        form_header = self.header_var.get().strip()
        resolved = []
        for row in rows:
            pn = row["part_number"]
            found_hit = self._find_part(pn)
            found = bool(found_hit)
            if found:
                pn, entry = found_hit
                desc = entry.get("description", "") or row["description"]
                header = entry.get("header", "")
                price = entry.get("price", "")
            else:
                desc = row["description"]
                header = row["header"] or form_header
                price = row["price"]
            resolved.append({
                "part_number": pn,
                "description": desc,
                "qty": row["qty"],
                "price": price,
                "header": header,
                "found": found,
            })
        return resolved

    def lookup_bulk(self) -> None:
        rows = self._parse_bulk()
        if not rows:
            messagebox.showwarning("Parts Label", "Paste at least one part line.")
            return
        self.bulk_view = self._resolve_rows(rows)
        self.bulk_index = 0
        found = sum(1 for r in self.bulk_view if r["found"])
        missing = len(self.bulk_view) - found
        self._log(f"Looked up {len(self.bulk_view)} — {found} found, {missing} new")
        self._show_bulk()

    def _show_bulk(self) -> None:
        if not self.bulk_view:
            self.bulk_pos.set("")
            return
        self.bulk_index %= len(self.bulk_view)
        row = self.bulk_view[self.bulk_index]
        self._last_looked = row["part_number"]
        self.part_var.set(row["part_number"])
        self._set_desc(row["description"])
        self.header_var.set(row["header"])
        self.price_var.set(row["price"])
        self.qty_var.set(str(row["qty"]))
        tag = "found" if row["found"] else "new"
        self.bulk_pos.set(f"{self.bulk_index + 1} / {len(self.bulk_view)}  {tag}")
        self.status_var.set(row["part_number"])
        self.draw_preview()

    def _bulk_step(self, delta: int) -> None:
        if not self.bulk_view:
            return
        self.bulk_index = (self.bulk_index + delta) % len(self.bulk_view)
        self._show_bulk()

    def _parse_bulk(self) -> list[dict]:
        import re
        rows = []
        text = self.bulk.get("1.0", "end")
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            price = ""
            qty = 1
            header = ""
            if "\t" in line:
                cols = [c.strip() for c in line.split("\t")]
                pn = cols[0]
                desc = cols[1] if len(cols) > 1 else ""
                if len(cols) > 2 and cols[2]:
                    m = re.search(r"\d+", cols[2])
                    if m:
                        qty = int(m.group())
                if len(cols) > 3 and cols[3]:
                    _, price = eng.parse_header_or_price(cols[3])
                    if not price and cols[3].startswith("$"):
                        price = cols[3]
                if len(cols) > 4:
                    header = cols[4]
            else:
                work = line
                mp = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", work)
                if mp:
                    price = f"${float(mp.group(1)):.2f}"
                    work = (work[:mp.start()] + " " + work[mp.end():]).strip()
                mq = re.search(r"\((\d+)\)", work)
                if mq:
                    qty = int(mq.group(1))
                    work = (work[:mq.start()] + " " + work[mq.end():]).strip()
                work = re.sub(r"\s+", " ", work).strip()
                pn, desc = self._split_part_and_desc(work)
            pn = eng.normalize_part_number(pn)
            if not pn:
                continue
            rows.append({
                "part_number": pn,
                "description": desc,
                "qty": max(1, qty),
                "price": price,
                "header": header,
            })
        return rows

    def _split_part_and_desc(self, text: str) -> tuple[str, str]:
        """Longest parts-list match wins. New parts keep the first word as the number."""
        text = eng.normalize_part_number(text)
        if not text:
            return "", ""
        words = text.split()
        # Try the whole line, then drop words from the end until a part is found
        for n in range(len(words), 0, -1):
            candidate = " ".join(words[:n])
            hit = self._find_part(candidate)
            if hit:
                saved_pn, _entry = hit
                desc = " ".join(words[n:]).strip()
                return saved_pn, desc
        return words[0], " ".join(words[1:]).strip()

    def run_bulk(self, print_it: bool, one_each: bool = False) -> None:
        if self.busy:
            return
        rows = self._parse_bulk()
        if not rows:
            messagebox.showwarning("Parts Label", "Paste at least one part line.")
            return
        printer = self.printer_var.get().strip()
        if print_it and not printer:
            messagebox.showwarning("Parts Label", "Select a printer first.")
            return
        form_header = self.header_var.get().strip()
        self.busy = True
        self.status_var.set(f"{'Printing' if print_it else 'Updating'} {len(rows)}…")
        self._log(f"Bulk {len(rows)} part{'s' if len(rows) != 1 else ''}")

        def work():
            ok = 0
            errors = []
            last = None
            try:
                for row in rows:
                    pn = row["part_number"]
                    hit = self._find_part(pn)
                    found = bool(hit)
                    if found:
                        pn, entry = hit
                        desc = entry.get("description", "") or row["description"]
                        header = entry.get("header", "")
                        price = entry.get("price", "")
                    else:
                        desc = row["description"]
                        header = row["header"] or form_header
                        price = row["price"]
                    if not desc:
                        errors.append(f"{pn}: not in list and no description")
                        continue
                    combined = f"{header} {price}".strip() if (header or price) else ""
                    try:
                        qty = 1 if one_each else row["qty"]
                        out = eng.make_one_label(
                            pn, desc, combined, copies=qty,
                            auto_print=print_it, printer_name=printer,
                        )
                        if not found:
                            eng.update_parts_list(pn, desc, self.parts, price=price, header=header)
                        ok += 1
                        last = {
                            "part_number": pn,
                            "description": desc,
                            "header": combined,
                            "header_text": header,
                            "price": price,
                            "copies": qty,
                        }
                        note = "found" if found else "new, saved"
                        self.after(0, lambda p=pn, q=qty, o=out, n=note: self._log(
                            f"{'Printed' if print_it else 'Updated'} {p} × {q} ({n}): {o}"
                        ))
                    except Exception as e:
                        errors.append(f"{pn}: {e}")
                self.after(0, lambda: self._bulk_done(ok, errors, last, print_it))
            except Exception as e:
                self.after(0, lambda err=e: self._fail(err))

        threading.Thread(target=work, daemon=True).start()

    def _bulk_done(self, ok: int, errors: list, last, printed: bool) -> None:
        self.busy = False
        if last:
            self.last = last
        self.status_var.set(f"Bulk done {ok}")
        self._log(f"Bulk finished: {ok} ok, {len(errors)} skipped")
        for err in errors:
            self._log(f"  {err}")
        if ok and not errors:
            self.bulk.delete("1.0", "end")
        if errors:
            messagebox.showwarning("Parts Label", "\n".join(errors[:12]))

    def _add_edit_menu(self, widget) -> None:
        """Right-click Cut / Copy / Paste / Select All."""
        menu = tk.Menu(
            widget, tearoff=0, bg=CARD, fg=INK,
            activebackground=AMBER, activeforeground="#1b1f24",
            font=("Segoe UI", 10),
        )

        def cut():
            widget.event_generate("<<Cut>>")

        def copy():
            widget.event_generate("<<Copy>>")

        def paste():
            widget.event_generate("<<Paste>>")

        def select_all(_event=None):
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
            else:
                widget.select_range(0, "end")
                widget.icursor("end")
            return "break"

        menu.add_command(label="Cut", command=cut)
        menu.add_command(label="Copy", command=copy)
        menu.add_command(label="Paste", command=paste)
        menu.add_separator()
        menu.add_command(label="Select All", command=select_all)

        def popup(event):
            widget.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", popup)
        widget.bind("<Control-a>", select_all)
        widget.bind("<Control-A>", select_all)

    def _btn(self, parent, text, cmd, bg, fg):
        return tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=bg,
            activeforeground=fg, relief="flat", font=("Segoe UI", 11, "bold"),
            padx=16, pady=8, cursor="hand2", bd=0,
        )

    def _log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _force_part_upper(self, *_args) -> None:
        val = self.part_var.get()
        up = val.upper()
        if val != up:
            self.part_var.set(up)

    def refresh_printers(self) -> None:
        names = eng.list_printers()
        chosen = eng.pick_default_printer(names)
        if chosen and chosen not in names:
            names = [chosen] + names
        self.printer_box["values"] = names
        self.printer_var.set(chosen)
        self._log(f"Printer default: {chosen}")

    def _note_printer(self) -> None:
        name = self.printer_var.get().strip()
        if name:
            self.status_var.set(name)
            self._log(f"This print will use {name}")

    def _save_printer(self) -> None:
        name = self.printer_var.get().strip()
        if not name:
            return
        eng.save_printer_choice(name)
        self.status_var.set("Default saved")
        self._log(f"Default printer saved: {name}")

    def _desc_text(self) -> str:
        return self.desc.get("1.0", "end").strip()

    def _set_desc(self, text: str) -> None:
        self.desc.delete("1.0", "end")
        self.desc.insert("1.0", text)

    def lookup(self) -> None:
        pn = eng.normalize_part_number(self.part_var.get())
        if pn == self._last_looked:
            return
        self.part_var.set(pn)
        if not pn:
            self.status_var.set("Enter a part number")
            self._last_looked = ""
            return
        hit = self._find_part(pn)
        if not hit:
            self._last_looked = pn
            self.status_var.set("New part — type a description")
            self._log(f"Not in list: {pn}")
            self.desc.focus_set()
            return
        saved_pn, entry = hit
        self._last_looked = saved_pn
        self.part_var.set(saved_pn)
        self._set_desc(entry.get("description", ""))
        self.header_var.set(entry.get("header", ""))
        self.price_var.set(entry.get("price", ""))
        self.status_var.set("Found")
        self._log(f"Found {saved_pn} — {entry.get('description', '')}")
        self.draw_preview()

    def clear_form(self) -> None:
        self._last_looked = ""
        self.part_var.set("")
        self._set_desc("")
        self.header_var.set("")
        self.price_var.set("")
        self.qty_var.set("1")
        self.status_var.set("Cleared")
        self.part_entry.focus_set()
        self.draw_preview()

    def _combined_header(self) -> tuple[str, str, str]:
        header = self.header_var.get().strip()
        price_raw = self.price_var.get().strip()
        price = ""
        if price_raw and price_raw.upper() != "[BLANK]":
            _, price = eng.parse_header_or_price(
                price_raw if price_raw.startswith("$") else f"${price_raw.lstrip('$')}"
            )
            if not price:
                price = price_raw if price_raw.startswith("$") else f"${price_raw}"
        if header and price:
            combined = f"{header} {price}"
        else:
            combined = header or price
        return combined, header, price

    def run(self, print_it: bool) -> None:
        if self.busy:
            return
        pn = eng.normalize_part_number(self.part_var.get())
        desc = self._desc_text()
        if not pn:
            messagebox.showwarning("Parts Label", "Part number is required.")
            return
        if not desc:
            messagebox.showwarning("Parts Label", "Description is required.")
            return
        printer = self.printer_var.get().strip()
        if print_it and not printer:
            messagebox.showwarning("Parts Label", "Select a printer first.")
            return
        try:
            copies = int(self.qty_var.get() or "1")
            if copies < 1:
                copies = 1
        except ValueError:
            copies = 1
        combined, header, price = self._combined_header()
        self.busy = True
        self.status_var.set("Printing…" if print_it else "Updating…")
        self._log(("Printing" if print_it else "Updating") + f" {pn} × {copies if print_it else 1}")
        if print_it:
            self._log(f"Printer: {printer}")

        def work():
            try:
                out = eng.make_one_label(
                    pn, desc, combined, copies=copies, auto_print=print_it,
                    printer_name=printer,
                )
                eng.update_parts_list(pn, desc, self.parts, price=price, header=header)
                self.last = {
                    "part_number": pn,
                    "description": desc,
                    "header": combined,
                    "header_text": header,
                    "price": price,
                    "copies": copies,
                }
                self.after(0, lambda: self._done(out, print_it))
            except Exception as e:
                self.after(0, lambda err=e: self._fail(err))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, out: str, printed: bool) -> None:
        self.busy = False
        self.status_var.set("Printed" if printed else "Updated")
        self._log(("Printed" if printed else "Updated (no print)") + f": {out}")
        self._last_looked = ""
        self.part_var.set("")
        self._set_desc("")
        self.header_var.set("")
        self.price_var.set("")
        self.qty_var.set("1")
        self.part_entry.focus_set()
        self.draw_preview()

    def _fail(self, err: Exception) -> None:
        self.busy = False
        self.status_var.set("Error")
        self._log(f"ERROR: {err}")
        messagebox.showerror("Parts Label", str(err))

    def edit_last(self) -> None:
        if not self.last:
            messagebox.showinfo("Parts Label", "No last entry to edit yet.")
            return
        self.part_var.set(self.last["part_number"])
        self._set_desc(self.last["description"])
        self.header_var.set(self.last.get("header_text") or "")
        self.price_var.set(self.last.get("price") or "")
        self.qty_var.set(str(self.last.get("copies") or 1))
        self.status_var.set("Editing last entry")
        self._log(f"Loaded last entry: {self.last['part_number']}")
        self.part_entry.focus_set()
        self.draw_preview()

    def reprint(self) -> None:
        if not self.last:
            messagebox.showinfo("Parts Label", "Nothing to reprint yet.")
            return
        self.part_var.set(self.last["part_number"])
        self._set_desc(self.last["description"])
        self.header_var.set(self.last.get("header_text") or "")
        self.price_var.set(self.last.get("price") or "")
        self.qty_var.set("1")
        self.run(print_it=True)

    def draw_preview(self) -> None:
        if self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(180, self._render_preview)

    def _font(self, size: int, bold: bool = False):
        names = (
            ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
            if bold
            else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
        )
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _wrap_to_width(self, text: str, font, max_width: int) -> list[str]:
        """Wrap on word boundaries using the same width the preview draws."""
        words = (text or "").split()
        if not words:
            return []
        lines: list[str] = []
        cur = ""
        for word in words:
            trial = word if not cur else f"{cur} {word}"
            width = font.getlength(trial) if hasattr(font, "getlength") else font.getsize(trial)[0]
            if width <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _render_preview(self) -> None:
        """Draw the same 3x2 layout the PDF/print uses."""
        self._preview_job = None
        c = self.preview
        c.delete("all")
        if Image is None:
            c.create_text(20, 20, anchor="nw", text="Preview needs Pillow")
            return

        W, H = 450, 300  # 3 in x 2 in at 150 dpi
        img = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(img)

        def yb(pdf_y: float) -> float:
            # PDF y is from the bottom, 72 pt per inch. Image y is from the top.
            return H - (pdf_y / 72.0) * 150

        header = self.header_var.get().strip()
        pn = self.part_var.get().strip()
        desc = self._desc_text()
        price_raw = self.price_var.get().strip()
        price = ""
        if price_raw and price_raw.upper() != "[BLANK]":
            price = price_raw if price_raw.startswith("$") else f"${price_raw.lstrip('$')}"

        # Double border is drawn after the barcode so bars cannot cover it
        d.rectangle((6, 6, W - 7, H - 7), outline="black", width=3)
        d.rectangle((12, 12, W - 13, H - 13), outline="black", width=1)

        has_header = bool(header)
        y = 16
        if has_header:
            bar_h = 36
            d.rectangle((14, 14, W - 15, 14 + bar_h), fill="black")
            d.text((W / 2, 14 + bar_h / 2), header, fill="white", font=self._font(16, True), anchor="mm")
            y = 14 + bar_h + 10

        d.text((24, y), "PART NUMBER", fill="black", font=self._font(11), anchor="lt")
        y += 16
        d.text((W / 2, y), pn or " ", fill="black", font=self._font(20, True), anchor="mt")
        y += 28
        d.line((24, y, W - 24, y), fill="black", width=2)
        y += 8

        d.text((24, y), "DESCRIPTION", fill="black", font=self._font(11), anchor="lt")
        y += 16
        # Same wrap rules as the printed label
        if len(desc) <= 18:
            desc_font_size, max_chars = 16, 22
        elif len(desc) <= 28:
            desc_font_size, max_chars = 15, 26
        elif len(desc) <= 40:
            desc_font_size, max_chars = 14, 30
        else:
            desc_font_size, max_chars = 13, 34
        lines = eng.wrap_text_lines(desc, max_chars) if desc else []
        if len(lines) > 3:
            desc_font_size = max(11, desc_font_size - 1)
            max_chars = min(40, max_chars + 4)
            lines = eng.wrap_text_lines(desc, max_chars)[:3]
        for line in lines:
            d.text((W / 2, y), line, fill="black", font=self._font(desc_font_size, True), anchor="mt")
            y += desc_font_size + 3

        if price:
            y += 2
            d.text((24, y), "PRICE", fill="black", font=self._font(11), anchor="lt")
            y += 14
            d.text((W / 2, y), price, fill="black", font=self._font(16, True), anchor="mt")
            y += 22

        y += 4
        d.line((24, y, W - 24, y), fill="black", width=2)

        # Barcode only in the space left under the price line
        band_top = y + 10
        band_bot = H - 18
        band_left = 28
        band_right = W - 28
        if pn and band_bot > band_top + 20:
            try:
                fd, raw = tempfile.mkstemp(prefix="lblprev_")
                os.close(fd)
                base = raw
                bc_path = eng.generate_barcode(pn, base)
                if bc_path and os.path.isfile(bc_path):
                    bc = Image.open(bc_path).convert("L")
                    # Drop the quiet-zone padding so bars stay inside the frame
                    mask = bc.point(lambda p: 255 if p < 200 else 0)
                    bbox = mask.getbbox()
                    if bbox:
                        bc = bc.crop(bbox)
                    bc = bc.convert("RGB")
                    max_w = band_right - band_left
                    max_h = band_bot - band_top
                    try:
                        resample = Image.Resampling.LANCZOS
                    except AttributeError:
                        resample = Image.LANCZOS
                    bc.thumbnail((max_w, max_h), resample)
                    x = band_left + (max_w - bc.width) // 2
                    y = band_top + (max_h - bc.height) // 2
                    img.paste(bc, (x, y))
                for p in (bc_path, base, base + ".png"):
                    try:
                        if p and os.path.isfile(p):
                            os.remove(p)
                    except Exception:
                        pass
            except Exception:
                pass

        # Borders on top so the barcode cannot spill past them
        d.rectangle((6, 6, W - 7, H - 7), outline="black", width=3)
        d.rectangle((12, 12, W - 13, H - 13), outline="black", width=1)

        self._preview_photo = ImageTk.PhotoImage(img)
        # Fit the whole label, including the barcode, inside the preview box
        cw = max(int(c.winfo_width() or 400), 400)
        ch = max(int(c.winfo_height() or 280), 280)
        fitted = img.copy()
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        fitted.thumbnail((cw - 8, ch - 8), resample)
        self._preview_photo = ImageTk.PhotoImage(fitted)
        c.create_image(cw // 2, ch // 2, anchor="center", image=self._preview_photo)


    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        self.config(menu=bar)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Choose Parts List…", command=self.choose_parts_list)
        file_menu.add_command(label="Open Parts List Folder", command=self.open_parts_folder)
        file_menu.add_command(label="Open Settings Folder", command=self.open_user_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        bar.add_cascade(label="File", menu=file_menu)

        updates = tk.Menu(bar, tearoff=0)
        updates.add_command(
            label="Check for Updates",
            command=lambda: self.check_for_updates(manual=True),
        )
        self._startup_check_var = tk.BooleanVar(value=eng.updates_on_startup())
        updates.add_checkbutton(
            label="Check for Updates on Startup",
            variable=self._startup_check_var,
            command=self._toggle_startup_updates,
        )
        bar.add_cascade(label="Updates", menu=updates)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="About Parts Label", command=self.show_about)
        bar.add_cascade(label="Help", menu=help_menu)

    def _toggle_startup_updates(self) -> None:
        enabled = bool(self._startup_check_var.get())
        eng.set_updates_on_startup(enabled)
        self._log("Startup update check " + ("on" if enabled else "off"))

    def choose_parts_list(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose parts_list_clean.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        eng.set_parts_csv(path)
        self._last_looked = ""
        self.reload_parts(manual=True)
        self._log(f"Parts list set to {path}")

    def open_parts_folder(self) -> None:
        path = eng.find_parts_csv() or eng.configured_parts_csv()
        folder = os.path.dirname(path) if path else eng.user_data_dir()
        if folder and os.path.isdir(folder):
            eng.open_file(folder)
        else:
            messagebox.showinfo("Parts Label", "No parts list folder yet. Choose a parts list first.")

    def open_user_data(self) -> None:
        eng.open_file(eng.user_data_dir())

    def show_about(self) -> None:
        path = eng.find_parts_csv() or eng.configured_parts_csv() or "(none selected)"
        messagebox.showinfo(
            "About Parts Label",
            f"Parts Label {__version__}\n\n"
            "3 × 2 in labels with a Code 128 barcode\n"
            "for a Zebra GC420d.\n\n"
            f"Parts list:\n{path}\n\n"
            f"Your settings:\n{eng.user_data_dir()}\n\n"
            "Updates are optional. Nothing installs unless you click Download & install.",
        )

    def _maybe_choose_parts_list(self) -> None:
        """Ask once when no list is selected. Never invents an empty shop file."""
        if eng.find_parts_csv():
            return
        remembered = eng.configured_parts_csv()
        win = tk.Toplevel(self)
        self._parts_prompt = win
        win.title("Choose your parts list")
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        if remembered:
            text = (
                "The parts list this app was using is not there anymore:\n\n"
                f"{remembered}\n\n"
                "Choose that file again if it moved. A new empty list is only "
                "created if you ask for one."
            )
        else:
            text = (
                "Parts Label needs the CSV of part numbers, descriptions, and prices.\n\n"
                "If this computer already has a LABEL MAKER folder, choose the "
                "parts_list_clean.csv in that folder. Other shop tools keep editing "
                "that same file, and this app will use it too.\n\n"
                "Do not start a new empty list if that file is already on this computer."
            )
        tk.Label(
            win, text="Where is the parts list?", bg=BG, fg=AMBER,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Label(
            win, text=text, bg=BG, fg=INK, font=("Segoe UI", 11),
            wraplength=520, justify="left",
        ).pack(anchor="w", padx=18)

        def close():
            self._parts_prompt = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        def choose():
            path = filedialog.askopenfilename(
                parent=win,
                title="Choose parts_list_clean.csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if not path:
                return
            eng.set_parts_csv(path)
            close()
            self.reload_parts(manual=True)
            self._log(f"Parts list set to {path}")

        def create_new():
            if not messagebox.askokcancel(
                "Parts Label",
                "This creates an empty parts list in your personal folder.\n"
                "It does not copy prices from the LABEL MAKER folder.\n\n"
                "Continue?",
                parent=win,
            ):
                return
            path = os.path.join(eng.user_data_dir(), "parts_list_clean.csv")
            if not os.path.isfile(path):
                with open(path, "w", encoding="utf-8", newline="") as handle:
                    handle.write("PartNo,Description,Price,Header\n")
            eng.set_parts_csv(path)
            close()
            self.reload_parts(manual=True)
            self._log(f"New empty parts list: {path}")

        def later():
            close()
            self._log("No parts list selected. Use File → Choose Parts List when you are ready.")

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=18, pady=16)
        self._btn(row, "CHOOSE EXISTING FILE", choose, AMBER, "#1b1f24").pack(side="left", padx=(0, 8))
        self._btn(row, "CREATE NEW EMPTY LIST", create_new, "#3a4450", INK).pack(side="left", padx=(0, 8))
        self._btn(row, "NOT NOW", later, "#3a4450", INK).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", later)
        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + 80}+{self.winfo_rooty() + 80}")

    def _startup_update_check(self) -> None:
        prompt = getattr(self, "_parts_prompt", None)
        if prompt is not None:
            try:
                if prompt.winfo_exists():
                    self.after(1500, self._startup_update_check)
                    return
            except tk.TclError:
                pass
        if not eng.updates_on_startup():
            return
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool = False) -> None:
        """Ask GitHub if a newer release exists. Offline checks stay quiet unless asked."""
        if self._update_busy:
            return
        self._update_busy = True
        if manual:
            self.status_var.set("Checking for updates…")
            self._log("Checking GitHub for a newer version…")

        def work():
            release = updater.fetch_latest_release()
            self.after(0, lambda: self._update_result(release, manual))

        threading.Thread(target=work, daemon=True).start()

    def _update_result(self, release, manual: bool) -> None:
        self._update_busy = False
        if release is None:
            if manual:
                self.status_var.set("Offline")
                self._log("Update check failed (offline or GitHub unavailable).")
                messagebox.showinfo(
                    "Parts Label",
                    "Couldn't reach GitHub. You may be offline.\nThe app works without updates.",
                )
            return
        remote = updater.release_version(release)
        tag = str(release.get("tag_name") or remote)
        if not updater.is_newer(remote, __version__):
            if manual:
                self.status_var.set("Up to date")
                self._log(f"Parts Label {__version__} is the latest version.")
                messagebox.showinfo(
                    "Parts Label",
                    f"Parts Label {__version__} is the latest version.",
                )
            return
        if not manual and (tag == eng.skipped_version() or remote == eng.skipped_version()):
            return
        self.status_var.set(f"Update {remote}")
        self._log(f"Update available: {remote}")
        self._show_update_dialog(release)

    def _show_update_dialog(self, release: dict) -> None:
        existing = getattr(self, "_update_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    return
            except tk.TclError:
                pass
        remote = updater.release_version(release)
        tag = str(release.get("tag_name") or remote)
        win = tk.Toplevel(self)
        self._update_win = win
        win.title("Update available")
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)
        tk.Label(
            win, text=f"Parts Label {remote} is available", bg=BG, fg=AMBER,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(
            win,
            text=(
                f"You are running {__version__}. "
                "Nothing installs unless you click Download & install."
            ),
            bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=520, justify="left",
        ).pack(anchor="w", padx=18)
        notes = tk.Text(
            win, height=14, width=64, bg=CARD, fg=INK, relief="flat",
            font=("Segoe UI", 10), wrap="word", highlightthickness=0,
        )
        notes.pack(fill="both", expand=True, padx=18, pady=12)
        notes.insert("1.0", updater.release_notes(release))
        notes.configure(state="disabled")
        status = tk.StringVar(value="")
        tk.Label(
            win, textvariable=status, bg=BG, fg=GREEN, font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18)

        def close():
            self._update_win = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        def skip():
            eng.set_skipped_version(tag)
            self._log(f"Skipped update {tag}")
            close()

        buttons = []

        def set_buttons(state: str) -> None:
            for button in buttons:
                button.configure(state=state)

        def finished(message: str, error: Exception | None) -> None:
            set_buttons("normal")
            if error:
                status.set("Download failed")
                self._log(f"Update download failed: {error}")
                messagebox.showerror("Parts Label", str(error), parent=win)
                return
            status.set("Downloaded")
            self._log(message.replace("\n", " "))
            messagebox.showinfo("Parts Label", message, parent=win)

        def download():
            asset = updater.pick_asset(release)
            if not asset:
                messagebox.showinfo(
                    "Parts Label",
                    "This release has no installer for this computer yet.",
                    parent=win,
                )
                return
            status.set("Downloading… you still confirm the installer.")
            set_buttons("disabled")

            def work():
                try:
                    dest_dir = os.path.join(eng.user_data_dir(), "updates")
                    path = updater.download_asset(asset, dest_dir)
                    message = updater.launch_installer(path)
                    self.after(0, lambda: finished(message, None))
                except Exception as exc:
                    self.after(0, lambda err=exc: finished("", err))

            threading.Thread(target=work, daemon=True).start()

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=18, pady=(8, 16))
        buttons.append(self._btn(row, "Download & install", download, GREEN, "#102418"))
        buttons.append(self._btn(row, "Not now", close, "#3a4450", INK))
        buttons.append(self._btn(row, "Skip this version", skip, "#3a4450", INK))
        for button in buttons:
            button.pack(side="left", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", close)
        win.update_idletasks()
        win.geometry(f"580x480+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 80}")


def main() -> None:
    try:
        app = LabelApp()
        app.mainloop()
    except Exception as e:
        try:
            messagebox.showerror("Parts Label", str(e))
        except Exception:
            raise


if __name__ == "__main__":
    main()
