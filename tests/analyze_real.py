#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick analysis of real .dat files against the filter logic."""

import os

TARGET_LABELS = [
    "back_1 : high sensitivity :", "back_2 : high sensitivity :",
    "back_3 : high sensitivity :", "back_g : high sensitivity :",
    "front_1 : high sensitivity :", "front_2 : high sensitivity :",
    "front_3 : high sensitivity :", "front_g : high sensitivity :",
    "left_1 : high sensitivity :", "left_2 : high sensitivity :",
    "left_3 : high sensitivity :", "left_g : high sensitivity :",
    "middle_1 : high sensitivity :", "middle_2 : high sensitivity :",
    "middle_3 : high sensitivity :",
    "right_1 : high sensitivity :", "right_2 : high sensitivity :",
    "right_3 : high sensitivity :", "right_g : high sensitivity :",
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


def analyze(content):
    lines = content.splitlines(keepends=True)
    blocks = split_into_blocks(lines)
    kept = dropped = 0
    r = {"calibr": 0, "scinti": 0, "labels": 0, "small": 0}
    for block in blocks:
        if len(block) > 1 and any(w in block[1].lower() for w in ["calibr", "test"]):
            dropped += 1
            r["calibr"] += 1
            continue
        if should_drop_event(block):
            dropped += 1
            r["scinti"] += 1
            continue
        numeric_lines = [l for l in block if any(lbl in l for lbl in TARGET_LABELS)]
        if len(numeric_lines) != len(TARGET_LABELS):
            dropped += 1
            r["labels"] += 1
            continue
        cleaned = []
        all_nums = []
        for line in numeric_lines:
            nums = replace_outliers(parse_numbers(line))
            all_nums.extend(nums)
            prefix = ":".join(line.split(":")[:2]) + ":"
            cleaned.append(prefix + " " + " ".join(map(str, nums)) + "\n")
        if is_mostly_small(all_nums):
            dropped += 1
            r["small"] += 1
            continue
        kept += 1
    return len(blocks), kept, dropped, r


base = os.path.dirname(os.path.abspath(__file__))

files = []
for f in os.listdir(base):
    if f.endswith(".dat"):
        files.append(("tests/", f, os.path.join(base, f)))

jan = os.path.join(base, "January")
if os.path.isdir(jan):
    for f in sorted(os.listdir(jan)):
        if f.endswith(".dat"):
            files.append(("January/", f, os.path.join(jan, f)))

files.sort(key=lambda x: x[1])

HDR = "{:<25} {:>6} {:>6} {:>7}  {:>7} {:>7} {:>7} {:>6}  {}"
ROW = "{:<25} {:>6} {:>6} {:>7}  {:>7} {:>7} {:>7} {:>6}  {}pct kept"
SEP = "-" * 90

print(HDR.format("FILE", "TOTAL", "KEPT", "DROPPED", "calibr", "scinti", "labels", "small", ""))
print(SEP)

total_ev = total_kept = total_drop = 0
for loc, name, path in files:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()
    total, kept, dropped, r = analyze(content)
    pct = round(kept / total * 100) if total > 0 else 0
    label = loc + name
    print(ROW.format(label, total, kept, dropped, r["calibr"], r["scinti"], r["labels"], r["small"], pct))
    total_ev += total
    total_kept += kept
    total_drop += dropped

print(SEP)
total_pct = round(total_kept / total_ev * 100) if total_ev > 0 else 0
print(ROW.format("TOTAL", total_ev, total_kept, total_drop, "", "", "", "", total_pct))