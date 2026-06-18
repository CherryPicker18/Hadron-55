#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADRON-55 — GUI для обработки данных космических лучей
Тянь-Шаньская горная станция
"""

import os
import re
import glob
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import numpy as np


# ─────────────────────────────────────────────
#  ЛОГИКА ФИЛЬТРАЦИИ (из скриптов сестры)
# ─────────────────────────────────────────────

TARGET_LABELS = [
    "back_1 : high sensitivity :", "back_2 : high sensitivity :",
    "back_3 : high sensitivity :", "back_g : high sensitivity :",
    "front_1 : high sensitivity :", "front_2 : high sensitivity :",
    "front_3 : high sensitivity :", "front_g : high sensitivity :",
    "left_1 : high sensitivity :", "left_2 : high sensitivity :",
    "left_3 : high sensitivity :",
    # "left_4 : high sensitivity :",  # not present in all datasets
    "left_g : high sensitivity :",
    "middle_1 : high sensitivity :", "middle_2 : high sensitivity :",
    "middle_3 : high sensitivity :",
    "right_1 : high sensitivity :", "right_2 : high sensitivity :",
    "right_3 : high sensitivity :",
    # "right_4 : high sensitivity :",  # not present in all datasets
    "right_g : high sensitivity :",
]

SCINTI_HIGH = "scinti : high sensitivity :"
SCINTI_MIDI = "scinti : midi sensitivity :"
ZERO_RATIO_THRESHOLD = 0.7


def parse_numbers(line):
    parts = line.split(":")
    if len(parts) < 3:
        return []
    return [int(x) for x in parts[2].strip().split() if x.strip().lstrip("-").isdigit()]


def replace_outliers(numbers, ratio_threshold=10, absolute_threshold=1000):
    arr = list(numbers)
    n = len(arr)
    result = arr[:]
    for i in range(n):
        cur = arr[i]
        if i == 0 and n > 1:
            if abs(cur) > absolute_threshold:
                result[i] = arr[i + 1]
                continue
            elif cur > 0 and sum(arr[j] == 0 for j in range(1, min(5, n))) >= 2:
                result[i] = 0
                continue
        elif i == n - 1 and abs(cur) > absolute_threshold:
            result[i] = arr[i - 1]
            continue
        elif 0 < i < n - 1:
            left, right = arr[i - 1], arr[i + 1]
            avg = (left + right) / 2
            if (cur > avg * ratio_threshold and avg > 0) or cur > absolute_threshold:
                result[i] = int(avg)
                continue
        left_zeros = sum(arr[j] == 0 for j in range(max(0, i - 3), i)) >= 2
        right_zeros = sum(arr[j] == 0 for j in range(i + 1, min(n, i + 4))) >= 2
        if cur > 0 and left_zeros and right_zeros:
            result[i] = 0
    return result


def is_mostly_small(numbers, ratio=0.9):
    if not numbers:
        return True
    return sum(1 for x in numbers if 0 <= x <= 7) / len(numbers) >= ratio


def zero_ratio(numbers):
    if not numbers:
        return 1.0
    return numbers.count(0) / len(numbers)


def should_drop_event(block):
    high_zero = midi_zero = False
    for line in block:
        s = line.strip()
        if s.startswith(SCINTI_HIGH):
            if zero_ratio(parse_numbers(s)) >= ZERO_RATIO_THRESHOLD:
                high_zero = True
        elif s.startswith(SCINTI_MIDI):
            if zero_ratio(parse_numbers(s)) >= ZERO_RATIO_THRESHOLD:
                midi_zero = True
    return high_zero and midi_zero


def split_into_blocks(lines):
    blocks, current, inside = [], [], False
    for line in lines:
        if line.startswith("|EVENT"):
            inside = True
            current = [line]
        elif line.strip() == "#" and inside:
            current.append(line)
            blocks.append(current)
            inside = False
        elif inside:
            current.append(line)
    return blocks


def process_file(input_path, output_path, log_fn):
    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    blocks = split_into_blocks(lines)
    kept = []
    dropped = 0

    for block in blocks:
        if len(block) > 1 and any(w in block[1].lower() for w in ["calibr", "test"]):
            dropped += 1
            continue
        if should_drop_event(block):
            dropped += 1
            continue

        numeric_lines = [l for l in block if any(lbl in l for lbl in TARGET_LABELS)]
        if len(numeric_lines) != len(TARGET_LABELS):
            dropped += 1
            continue

        cleaned_lines = []
        all_nums = []
        for line in numeric_lines:
            nums = replace_outliers(parse_numbers(line))
            all_nums.extend(nums)
            prefix = ":".join(line.split(":")[:2]) + ":"
            cleaned_lines.append(prefix + " " + " ".join(map(str, nums)) + "\n")

        if is_mostly_small(all_nums):
            dropped += 1
            continue

        cleaned_block = []
        idx = 0
        for line in block:
            if any(lbl in line for lbl in TARGET_LABELS):
                cleaned_block.append(cleaned_lines[idx])
                idx += 1
            else:
                cleaned_block.append(line)
        kept.append(cleaned_block)

    with open(output_path, "w", encoding="utf-8") as f:
        for block in kept:
            f.writelines(block)

    name = os.path.basename(input_path)
    log_fn(f"  {name}: всего={len(blocks)}, удалено={dropped}, сохранено={len(kept)}")
    return len(blocks), len(kept), dropped


# ─────────────────────────────────────────────
#  ИНТЕРФЕЙС
# ─────────────────────────────────────────────

class Adron55App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HADRON-55 — Обработка данных космических лучей")
        self.geometry("780x580")
        self.resizable(True, True)
        self.configure(bg="#1a1a2e")
        self._build_ui()

    def _build_ui(self):
        # ── Заголовок ──
        header = tk.Frame(self, bg="#16213e", pady=10)
        header.pack(fill="x")
        tk.Label(header, text="⚛  HADRON-55", font=("Helvetica", 20, "bold"),
                 fg="#e94560", bg="#16213e").pack()
        tk.Label(header, text="Тянь-Шаньская горная станция • Фильтрация космических частиц",
                 font=("Helvetica", 10), fg="#a8a8b3", bg="#16213e").pack()

        # ── Папки ──
        frame = tk.Frame(self, bg="#1a1a2e", padx=20, pady=15)
        frame.pack(fill="x")

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()

        self._folder_row(frame, "📂  Входная папка (.dat файлы):", self.input_var,
                         self._choose_input, row=0)
        self._folder_row(frame, "💾  Выходная папка (результаты):", self.output_var,
                         self._choose_output, row=1)

        # ── Кнопка запуска ──
        btn_frame = tk.Frame(self, bg="#1a1a2e")
        btn_frame.pack(pady=5)
        self.run_btn = tk.Button(
            btn_frame, text="▶  Запустить фильтрацию",
            font=("Helvetica", 12, "bold"),
            bg="#e94560", fg="white", activebackground="#c73652",
            relief="flat", padx=20, pady=8, cursor="hand2",
            command=self._start
        )
        self.run_btn.pack()

        # ── Прогресс-бар ──
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=740)
        self.progress.pack(padx=20, pady=(5, 0))

        # ── Лог ──
        log_frame = tk.Frame(self, bg="#1a1a2e", padx=20, pady=10)
        log_frame.pack(fill="both", expand=True)
        tk.Label(log_frame, text="Лог обработки:", fg="#a8a8b3",
                 bg="#1a1a2e", anchor="w").pack(fill="x")
        self.log = scrolledtext.ScrolledText(
            log_frame, bg="#0f3460", fg="#e2e2e2",
            font=("Courier", 10), relief="flat", height=15
        )
        self.log.pack(fill="both", expand=True)

        # ── Статус-бар ──
        self.status_var = tk.StringVar(value="Готов к работе")
        tk.Label(self, textvariable=self.status_var, fg="#a8a8b3",
                 bg="#1a1a2e", anchor="w", padx=20).pack(fill="x", pady=(0, 5))

    def _folder_row(self, parent, label, var, cmd, row):
        tk.Label(parent, text=label, fg="#e2e2e2", bg="#1a1a2e",
                 font=("Helvetica", 10)).grid(row=row, column=0, sticky="w", pady=4)
        entry = tk.Entry(parent, textvariable=var, width=50,
                         bg="#0f3460", fg="white", insertbackground="white",
                         relief="flat", font=("Courier", 10))
        entry.grid(row=row, column=1, padx=10, pady=4)
        tk.Button(parent, text="Обзор", command=cmd,
                  bg="#533483", fg="white", relief="flat",
                  padx=8, cursor="hand2").grid(row=row, column=2)

    def _choose_input(self):
        d = filedialog.askdirectory(title="Выберите папку с .dat файлами")
        if d:
            self.input_var.set(d)

    def _choose_output(self):
        d = filedialog.askdirectory(title="Выберите папку для результатов")
        if d:
            self.output_var.set(d)

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _start(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()

        if not inp or not out:
            self._log("⚠️  Укажите обе папки!")
            return
        if not os.path.isdir(inp):
            self._log("❌  Входная папка не найдена.")
            return

        self.run_btn.config(state="disabled")
        self.progress.start(10)
        self.status_var.set("Обработка...")
        threading.Thread(target=self._run, args=(inp, out), daemon=True).start()

    def _run(self, inp, out):
        os.makedirs(out, exist_ok=True)
        files = [f for f in os.listdir(inp)
                 if f.endswith(".dat") and f[:-4].isdigit() and len(f[:-4]) == 6]

        if not files:
            self._log("⚠️  .dat файлы не найдены в указанной папке.")
            self._done()
            return

        self._log(f"\n🚀 Начало обработки. Найдено файлов: {len(files)}\n")

        total_events = total_kept = total_dropped = 0
        for fname in sorted(files):
            inp_path = os.path.join(inp, fname)
            out_path = os.path.join(out, fname)
            ev, kept, dropped = process_file(inp_path, out_path, self._log)
            total_events += ev
            total_kept += kept
            total_dropped += dropped

        self._log(f"\n{'─'*50}")
        self._log(f"✅ Готово!")
        self._log(f"   Файлов обработано : {len(files)}")
        self._log(f"   Событий всего     : {total_events}")
        self._log(f"   Сохранено         : {total_kept}")
        self._log(f"   Удалено (мусор)   : {total_dropped}")
        self._log(f"   Результаты в      : {out}\n")
        self._done()

    def _done(self):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set("Обработка завершена")


if __name__ == "__main__":
    app = Adron55App()
    app.mainloop()
