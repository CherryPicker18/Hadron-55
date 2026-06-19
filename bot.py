#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HADRON-55 — Telegram Bot + Flask Web API
"""

import os
import asyncio
import tempfile
import logging
import threading
from flask import Flask, request, jsonify, send_file
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart, Command

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))

# ── ФИЛЬТРАЦИЯ ──
TARGET_LABELS = [
    "back_1 : high sensitivity :", "back_2 : high sensitivity :",
    "back_3 : high sensitivity :", "back_g : high sensitivity :",
    "front_1 : high sensitivity :", "front_2 : high sensitivity :",
    "front_3 : high sensitivity :", "front_g : high sensitivity :",
    "left_1 : high sensitivity :", "left_2 : high sensitivity :",
    "left_3 : high sensitivity :",
    "left_4 : high sensitivity :",
    "left_g : high sensitivity :",
    "middle_1 : high sensitivity :", "middle_2 : high sensitivity :",
    "middle_3 : high sensitivity :",
    "right_1 : high sensitivity :", "right_2 : high sensitivity :",
    "right_3 : high sensitivity :",
    "right_4 : high sensitivity :",
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


def is_mostly_small(numbers, ratio=0.9):
    if not numbers:
        return True
    return sum(1 for x in numbers if 0 <= x <= 7) / len(numbers) >= ratio


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


def filter_data(content: str):
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


# ── FLASK API ──
app = Flask(__name__)


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "HADRON-55"})


@app.route("/filter", methods=["POST"])
def filter_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if not file.filename.endswith(".dat"):
        return jsonify({"error": "Only .dat files accepted"}), 400

    try:
        content = file.read().decode("utf-8", errors="ignore")
        result, total, kept, dropped = filter_data(content)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".dat",
            prefix="filtered_", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(result)
            tmp_path = tmp.name

        response = send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"filtered_{file.filename}",
            mimetype="text/plain"
        )
        response.headers["X-Total-Events"] = str(total)
        response.headers["X-Kept-Events"] = str(kept)
        response.headers["X-Dropped-Events"] = str(dropped)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Events,X-Kept-Events,X-Dropped-Events"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/filter", methods=["OPTIONS"])
def filter_options():
    response = jsonify({"ok": True})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False)


# ── TELEGRAM БОТ ──
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "⚛ *HADRON-55 Filter Bot*\n\n"
        "Отправь мне `.dat` файл — я отфильтрую шум и верну чистые события.\n\n"
        "📋 *Что я делаю:*\n"
        "• Удаляю пустые события (≥70% нулей)\n"
        "• Заменяю выбросы на среднее соседних\n"
        "• Подавляю одиночные шумы\n\n"
        "Просто пришли файл 👇",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 *Справка*\n\n"
        "/start — приветствие\n"
        "/help — эта справка\n\n"
        "Отправь `.dat` файл → получи отфильтрованный файл.",
        parse_mode="Markdown"
    )


@dp.message(F.document)
async def handle_document(message: Message, bot: Bot):
    doc = message.document

    if not doc.file_name.endswith(".dat"):
        await message.answer("⚠️ Пожалуйста, отправь файл с расширением .dat")
        return

    await message.answer("⏳ Обрабатываю файл...")

    try:
        file = await bot.get_file(doc.file_id)
        content_bytes = await bot.download_file(file.file_path)
        content = content_bytes.read().decode("utf-8", errors="ignore")

        result, total, kept, dropped = filter_data(content)

        if kept == 0:
            await message.answer(
                f"ℹ️ Обработка завершена.\n\n"
                f"📊 Всего событий: {total}\n"
                f"✅ Сохранено: {kept}\n"
                f"🗑 Удалено: {dropped}\n\n"
                f"Все события отфильтрованы как шум."
            )
            return

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".dat",
            prefix="filtered_", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(result)
            tmp_path = tmp.name

        await message.answer_document(
            document=FSInputFile(tmp_path, filename=f"filtered_{doc.file_name}"),
            caption=(
                f"✅ *Фильтрация завершена*\n\n"
                f"📊 Всего: `{total}`\n"
                f"✅ Сохранено: `{kept}`\n"
                f"🗑 Удалено: `{dropped}`"
            ),
            parse_mode="Markdown"
        )

        os.unlink(tmp_path)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message()
async def handle_text(message: Message):
    await message.answer("Отправь мне .dat файл — нажми на скрепку 📎")


async def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN не задан!")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"🌐 Flask запущен на порту {PORT}")

    bot = Bot(token=TOKEN)
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
