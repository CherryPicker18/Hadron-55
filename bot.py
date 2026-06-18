#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HADRON-55 Telegram Bot
Принимает .dat файлы, фильтрует и возвращает результат
"""

import asyncio
import os
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ── НАСТРОЙКИ ──
TOKEN = os.environ.get("BOT_TOKEN")  # токен из переменной окружения

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── ЛОГИКА ФИЛЬТРАЦИИ ──
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


# ── ОБРАБОТЧИКИ БОТА ──

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚛ *HADRON-55 Filter Bot*\n\n"
        "Отправь мне `.dat` файл с данными детектора — я отфильтрую шум и верну чистые события.\n\n"
        "📋 *Что я делаю:*\n"
        "• Удаляю пустые события (≥70% нулей в сцинтилляторах)\n"
        "• Заменяю выбросы на среднее соседних значений\n"
        "• Подавляю одиночные шумовые импульсы\n\n"
        "Просто пришли файл 👇",
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "/start — приветствие\n"
        "/help — эта справка\n\n"
        "Отправь `.dat` файл → получи отфильтрованный файл.\n"
        "Файлы должны быть в формате Hadron-55 с блоками |EVENT: ... #",
        parse_mode="Markdown"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if not doc.file_name.endswith(".dat"):
        await update.message.reply_text("⚠️ Пожалуйста, отправь файл с расширением .dat")
        return

    await update.message.reply_text("⏳ Обрабатываю файл...")

    try:
        file = await context.bot.get_file(doc.file_id)
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")

        result, total, kept, dropped = filter_data(content)

        if kept == 0:
            await update.message.reply_text(
                f"ℹ️ Обработка завершена.\n\n"
                f"📊 Всего событий: {total}\n"
                f"✅ Сохранено: {kept}\n"
                f"🗑 Удалено: {dropped}\n\n"
                f"Все события были отфильтрованы как шум."
            )
            return

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".dat",
            prefix="filtered_", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(result)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"filtered_{doc.file_name}",
                caption=(
                    f"✅ *Фильтрация завершена*\n\n"
                    f"📊 Всего событий: `{total}`\n"
                    f"✅ Сохранено: `{kept}`\n"
                    f"🗑 Удалено (шум): `{dropped}`"
                ),
                parse_mode="Markdown"
            )

        os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Ошибка при обработке: {str(e)}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправь мне .dat файл — нажми на скрепку 📎 и выбери файл."
    )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN не задан! Установи переменную окружения BOT_TOKEN.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Бот запущен...")
    asyncio.run(app.run_polling())


if __name__ == "__main__":
    main()