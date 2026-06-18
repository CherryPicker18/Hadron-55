#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HADRON-55 — Filter logic test suite
Run: py tests/test_filter.py

Self-contained — no external dependencies (telegram/tkinter/numpy not needed).
Filter functions are inlined from bot.py to avoid import side-effects.
"""

# -- Inlined filter logic ------------------------------------------------------

TARGET_LABELS = [
    "back_1 : high sensitivity :", "back_2 : high sensitivity :",
    "back_3 : high sensitivity :", "back_g : high sensitivity :",
    "front_1 : high sensitivity :", "front_2 : high sensitivity :",
    "front_3 : high sensitivity :", "front_g : high sensitivity :",
    "left_1 : high sensitivity :", "left_2 : high sensitivity :",
    "left_3 : high sensitivity :", "left_4 : high sensitivity :",
    "left_g : high sensitivity :", "middle_1 : high sensitivity :",
    "middle_2 : high sensitivity :", "middle_3 : high sensitivity :",
    "right_1 : high sensitivity :", "right_2 : high sensitivity :",
    "right_3 : high sensitivity :", "right_4 : high sensitivity :",
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


def filter_data(content: str) -> tuple:
    lines = content.splitlines(keepends=True)
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

    result = ""
    for block in kept:
        result += "".join(block)

    return result, len(blocks), len(kept), dropped


# -- Test infrastructure -------------------------------------------------------

_PASS = _FAIL = 0


def check(name: str, content: str, exp_kept: int, exp_total: int = None):
    global _PASS, _FAIL
    _, total, kept, dropped = filter_data(content)
    ok = kept == exp_kept and (exp_total is None or total == exp_total)
    if ok:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        exp = f"kept={exp_kept}" + (f", total={exp_total}" if exp_total is not None else "")
        got = f"kept={kept}, total={total}, dropped={dropped}"
        print(f"  [FAIL] {name}")
        print(f"         expected  {exp}")
        print(f"         got       {got}")


# -- Reusable data -------------------------------------------------------------

GOOD_NUMS  = "100 200 150 300 250 180 220 170 190 210"  # all > 7
SMALL_NUMS = "1 2 3 1 2 1 0 0 1 2"                      # all in [0, 7]

SH_GOOD = "scinti : high sensitivity : 50 80 90 100 120 30 40 60 70 110"
SM_GOOD = "scinti : midi sensitivity : 10 20 15 25 30 12 18 22 14 16"
SH_ZERO = "scinti : high sensitivity : 0 0 0 0 0 0 0 0 0 0"
SM_ZERO = "scinti : midi sensitivity : 0 0 0 0 0 0 0 0 0 0"
# exactly 70 pct zeros (7 of 10) — sits on the threshold
SH_70PC  = "scinti : high sensitivity : 0 0 0 0 0 0 0 100 200 300"
# 60 pct zeros (6 of 10) — just below threshold
SH_60PC  = "scinti : high sensitivity : 0 0 0 0 0 0 100 200 300 400"


def make_event(header="2101011200", sh=SH_GOOD, sm=SM_GOOD,
               labels=None, nums=GOOD_NUMS, extra_lines=None):
    if labels is None:
        labels = TARGET_LABELS
    parts = [f"|EVENT: {header}\n", f"{sh}\n", f"{sm}\n"]
    for lbl in labels:
        parts.append(f"{lbl} {nums}\n")
    if extra_lines:
        parts.extend(extra_lines)
    parts.append("#\n")
    return "".join(parts)


def make_calibr_event():
    return "|EVENT: 2101011200\ncalibration run 000\n#\n"


def make_zero_event():
    return make_event(sh=SH_ZERO, sm=SM_ZERO)


def bulk(n_good=0, n_calibr=0, n_zero=0):
    return make_event() * n_good + make_calibr_event() * n_calibr + make_zero_event() * n_zero


# -- POSITIVE: events that SHOULD survive filtering ----------------------------

print("\n-- POSITIVE (should keep) --")

check("normal physical event",
      make_event(), exp_kept=1, exp_total=1)

check("only scinti_high mostly zero — midi ok -> keep",
      make_event(sh=SH_ZERO, sm=SM_GOOD), exp_kept=1)

check("only scinti_midi mostly zero — high ok -> keep",
      make_event(sh=SH_GOOD, sm=SM_ZERO), exp_kept=1)

check("scinti_high 60 pct zeros (< 70 pct) + midi all zero -> keep",
      make_event(sh=SH_60PC, sm=SM_ZERO), exp_kept=1)

check("no scinti lines at all — check not triggered -> keep",
      "".join(
          ["|EVENT: 2101011200\n"] +
          [f"{lbl} {GOOD_NUMS}\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1)

check("middle outlier (x10 ratio) replaced — event still physical",
      make_event(nums="100 5000 100 200 150 300 250 180 220 170"), exp_kept=1)

check("first element > 1000 -> replaced by second",
      make_event(nums="2000 100 200 150 300 250 180 220 170 190"), exp_kept=1)

check("last element > 1000 -> replaced by second-to-last",
      make_event(nums="100 200 150 300 250 180 220 170 190 5000"), exp_kept=1)

check("large negative numbers — not in [0, 7] so not small -> keep",
      make_event(nums="-100 -200 -150 -300 -250 -180 -220 -170 -190 -210"), exp_kept=1)

check("garbage tokens in nums field — ignored, rest parsed -> keep",
      make_event(nums="abc xyz 100 200 150 300 250 180 220 170"), exp_kept=1)

check("single number per label — replace_outliers n=1 edge case",
      "".join(
          ["|EVENT: 2101011200\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} 500\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1)

# 89.5 pct small -> kept  (threshold is >= 90 pct)
# 21 labels x 10 nums = 210 total
# labels[0,1]: GOOD_NUMS   -> 20 big
# labels[2]:   "8 9 …"     ->  2 big, 8 small
# labels[3-20]: SMALL_NUMS -> 180 small
# 22 big / 188 small -> 188/210 = 89.5 pct < 90 pct -> kept
_nums_map = {TARGET_LABELS[0]: GOOD_NUMS,
             TARGET_LABELS[1]: GOOD_NUMS,
             TARGET_LABELS[2]: "8 9 1 2 3 1 0 0 1 2"}
check("89.5 pct small numbers — just below 90 pct threshold -> keep",
      "".join(
          ["|EVENT: 2101011200\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} {_nums_map.get(lbl, SMALL_NUMS)}\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1)

check("3 consecutive good events",
      make_event() * 3, exp_kept=3, exp_total=3)

check("2 good + 1 calibr + 1 zero-scinti -> kept=2",
      bulk(n_good=2, n_calibr=1, n_zero=1), exp_kept=2, exp_total=4)

check("500 good events — stress, no crash",
      make_event() * 500, exp_kept=500, exp_total=500)

# -- NEGATIVE: events that SHOULD be dropped -----------------------------------

print("\n-- NEGATIVE (should drop) --")

check("empty file",
      "", exp_kept=0, exp_total=0)

check("whitespace / newlines only",
      "   \n\n   \n", exp_kept=0, exp_total=0)

check("no # terminator — block never closed -> 0 blocks",
      f"|EVENT: 2101011200\n{SH_GOOD}\n{SM_GOOD}\nno_hash_here\n",
      exp_kept=0, exp_total=0)

check("calibration event (lowercase 'calibr')",
      "|EVENT: 2101011200\ncalibration run 000\n#\n", exp_kept=0, exp_total=1)

check("calibration event (uppercase 'CALIBR') — case-insensitive",
      "|EVENT: 2101011200\nCALIBRATION RUN 000\n#\n", exp_kept=0, exp_total=1)

check("test event (lowercase 'test')",
      "|EVENT: 2101011200\ntest_sequence_start\n#\n", exp_kept=0, exp_total=1)

check("both scinti all zeros -> dropped",
      make_event(sh=SH_ZERO, sm=SM_ZERO), exp_kept=0, exp_total=1)

check("scinti_high exactly 70 pct zeros + midi all zero -> dropped",
      make_event(sh=SH_70PC, sm=SM_ZERO), exp_kept=0, exp_total=1)

check("missing one target label (20 of 21) -> dropped",
      make_event(labels=TARGET_LABELS[:-1]), exp_kept=0, exp_total=1)

check("missing all target labels -> dropped",
      make_event(labels=[]), exp_kept=0, exp_total=1)

check("extra duplicate label (22 lines) -> dropped",
      make_event(labels=TARGET_LABELS + [TARGET_LABELS[0]]), exp_kept=0, exp_total=1)

check("all numbers are small (0-7) -> dropped",
      make_event(nums=SMALL_NUMS), exp_kept=0, exp_total=1)

# exactly 90 pct small -> dropped
# labels[0,1]: GOOD_NUMS   -> 20 big
# labels[2]:   "8 …"       ->  1 big (8), 9 small
# labels[3-20]: SMALL_NUMS -> 180 small
# 21 big / 189 small -> 189/210 = 90.0 pct -> dropped
_nums_map_90 = {TARGET_LABELS[0]: GOOD_NUMS,
                TARGET_LABELS[1]: GOOD_NUMS,
                TARGET_LABELS[2]: "8 1 2 3 1 2 1 0 0 1"}
check("exactly 90 pct small numbers -> dropped",
      "".join(
          ["|EVENT: 2101011200\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} {_nums_map_90.get(lbl, SMALL_NUMS)}\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=0, exp_total=1)

check("empty event (only |EVENT + #) -> 0 labels -> dropped",
      "|EVENT: 2101011200\n#\n", exp_kept=0, exp_total=1)

check("label lines present but values empty -> all_nums=[] -> is_mostly_small=True -> dropped",
      "".join(
          ["|EVENT: 2101011200\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} :\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=0, exp_total=1)

check("500 calibration events — stress, no crash",
      make_calibr_event() * 500, exp_kept=0, exp_total=500)

check("500 zero-scinti events — stress, no crash",
      make_zero_event() * 500, exp_kept=0, exp_total=500)

# -- EDGE CASES ----------------------------------------------------------------

print("\n-- EDGE CASES --")

# spike at middle with avg=0: cur > 1000 -> result = int(0) = 0 -> all zeros -> dropped
check("isolated spike surrounded by zeros -> zeroed by outlier logic -> dropped",
      make_event(nums="0 0 0 5000 0 0 0 0 0 0"), exp_kept=0)

# |EVENT immediately followed by another |EVENT — second overrides first -> 1 block
check("consecutive |EVENT headers — second overrides first -> 1 block kept",
      "".join(
          ["|EVENT: first\n", "|EVENT: second\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} {GOOD_NUMS}\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1, exp_total=1)

# scinti_high exactly at 69 pct zeros (< 70 pct), midi all zero -> NOT both >= threshold -> keep
check("scinti_high 69 pct zeros + midi all zero — high just below threshold -> keep",
      "".join(
          ["|EVENT: 2101011200\n",
           "scinti : high sensitivity : 0 0 0 0 0 0 0 100 200 300 400\n",  # 6/11 = 54 pct... let me use: 0*6 + non-0*5 out of 11
           f"{SM_ZERO}\n"] +
          [f"{lbl} {GOOD_NUMS}\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1)

# outlier on first element of single-value array (n=1) — none of the guards fire
check("outlier first element n=1 list — no replacement (guards need n>1)",
      "".join(
          ["|EVENT: 2101011200\n", f"{SH_GOOD}\n", f"{SM_GOOD}\n"] +
          [f"{lbl} 5000\n" for lbl in TARGET_LABELS] +
          ["#\n"]
      ), exp_kept=1)

# numbers field is pure zeros but scinti lines are healthy — is_mostly_small drops it
check("all-zero label values but healthy scinti -> dropped by is_mostly_small",
      make_event(nums="0 0 0 0 0 0 0 0 0 0"), exp_kept=0)

# 1000 mixed events
check("1000 mixed events (500 good / 300 calibr / 200 zero) — no crash",
      bulk(n_good=500, n_calibr=300, n_zero=200), exp_kept=500, exp_total=1000)

# -- Summary -------------------------------------------------------------------

total = _PASS + _FAIL
print(f"\n{'-' * 50}")
print(f"Results: {_PASS}/{total} passed, {_FAIL} failed")
if _FAIL == 0:
    print("All tests passed!")
else:
    print(f"{_FAIL} test(s) FAILED — see details above.")