"""Telegram-бот-помощник по подбору настольных игр.

Бот написан на библиотеке python-telegram-bot и использует JSON-файл для хранения
статистики пользователей. База игр загружается из CSV-файла, чтобы её можно было
легко расширять без изменения кода.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STATS_FILE = BASE_DIR / "stats.json"
CSV_FILE = BASE_DIR / "board_games.csv"


@dataclass(frozen=True)
class BoardGame:
    """Описание настольной игры из CSV."""

    name: str
    genre: str
    player_count: str
    min_age: int
    play_time_minutes: str
    difficulty: str
    company_type: str
    description: str


GENRE_CATEGORIES: dict[str, str] = {
    "strategies": "стратегия",
    "detectives": "детектив",
    "economic": "экономическая",
    "party": "карточная",
    "family": "семейная",
    "cooperative": "кооперативная",
    "abstract": "абстрактная",
}

COMPANY_CATEGORIES: dict[str, str] = {
    "family": "семья",
    "friends": "друзья",
    "couple": "пара",
    "group": "компания",
}

DIFFICULTY_CATEGORIES: dict[str, str] = {
    "easy": "лёгкая",
    "medium": "средняя",
    "hard": "сложная",
}

GAMES: list[BoardGame] = []


def load_stats() -> dict:
    if not STATS_FILE.exists():
        return {}
    try:
        with STATS_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        logger.error("Не удалось загрузить stats.json: %s", error)
        return {}


def save_stats(stats: dict) -> None:
    try:
        with STATS_FILE.open("w", encoding="utf-8") as file:
            json.dump(stats, file, ensure_ascii=False, indent=2)
    except OSError as error:
        logger.error("Не удалось сохранить stats.json: %s", error)


def increase_recommendation_count(user_id: int) -> int:
    stats = load_stats()
    user_key = str(user_id)
    if user_key not in stats:
        stats[user_key] = {"recommendations": 0}
    stats[user_key]["recommendations"] += 1
    save_stats(stats)
    return stats[user_key]["recommendations"]


def get_recommendation_count(user_id: int) -> int:
    stats = load_stats()
    return int(stats.get(str(user_id), {}).get("recommendations", 0))


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_games_from_csv() -> list[BoardGame]:
    if not CSV_FILE.exists():
        logger.warning("CSV-файл с играми не найден: %s", CSV_FILE)
        return []

    games: list[BoardGame] = []
    try:
        with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row.get("name"):
                    continue
                games.append(
                    BoardGame(
                        name=row.get("name", "").strip(),
                        genre=row.get("genre", "").strip(),
                        player_count=row.get("player_count", "").strip(),
                        min_age=parse_int(row.get("min_age", "0")),
                        play_time_minutes=row.get("play_time_minutes", "").strip(),
                        difficulty=row.get("difficulty", "").strip(),
                        company_type=row.get("company_type", "").strip(),
                        description=row.get("description", "").strip(),
                    )
                )
    except (OSError, csv.Error, KeyError) as error:
        logger.error("Не удалось загрузить board_games.csv: %s", error)
        return []

    return games


def match_player_count(player_count: str, query: str) -> bool:
    return query in player_count


def find_games_by_genre(genre_name: str) -> list[BoardGame]:
    return [game for game in GAMES if game.genre.lower() == genre_name.lower()]


def find_games_by_company(company_name: str) -> list[BoardGame]:
    return [game for game in GAMES if game.company_type.lower() == company_name.lower()]


def find_games_by_difficulty(difficulty_name: str) -> list[BoardGame]:
    return [game for game in GAMES if game.difficulty.lower() == difficulty_name.lower()]


def find_games_by_players(player_query: str) -> list[BoardGame]:
    return [game for game in GAMES if match_player_count(game.player_count, player_query)]


def find_games_by_time(time_query: str) -> list[BoardGame]:
    if time_query == "short":
        return [game for game in GAMES if parse_int(game.play_time_minutes.split("-")[0], 999) <= 30]
    if time_query == "medium":
        return [game for game in GAMES if 30 <= parse_int(game.play_time_minutes.split("-")[0], 0) <= 60]
    return [game for game in GAMES if parse_int(game.play_time_minutes.split("-")[0], 0) >= 60]


def choose_random_games(games: Sequence[BoardGame], count: int = 3) -> list[BoardGame]:
    if not games:
        return []
    return random.sample(list(games), k=min(count, len(games)))


def format_games(games: Sequence[BoardGame]) -> str:
    if not games:
        return "К сожалению, подходящих игр не нашлось."

    lines = []
    for game in games:
        lines.append(
            f"• <b>{game.name}</b>\n"
            f"  Жанр: {game.genre}\n"
            f"  Игроки: {game.player_count}\n"
            f"  Возраст: {game.min_age}+\n"
            f"  Время партии: {game.play_time_minutes} мин.\n"
            f"  Сложность: {game.difficulty}\n"
            f"  Тип компании: {game.company_type}\n"
            f"  Описание: {game.description}"
        )
    return "\n\n".join(lines)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 По типу компании", callback_data="menu_types")],
        [InlineKeyboardButton("🧩 По жанрам", callback_data="menu_genres")],
        [InlineKeyboardButton("⚙️ По сложности", callback_data="menu_difficulty")],
        [InlineKeyboardButton("👥 По количеству игроков", callback_data="menu_players")],
        [InlineKeyboardButton("⏱ По времени партии", callback_data="menu_time")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu_stats")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="menu_about")],
    ])


def types_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Семья", callback_data="type_family")],
        [InlineKeyboardButton("Друзья", callback_data="type_friends")],
        [InlineKeyboardButton("Пара", callback_data="type_couple")],
        [InlineKeyboardButton("Компания", callback_data="type_group")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


def genres_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Стратегия", callback_data="genre_strategies")],
        [InlineKeyboardButton("Детектив", callback_data="genre_detectives")],
        [InlineKeyboardButton("Экономическая", callback_data="genre_economic")],
        [InlineKeyboardButton("Карточная", callback_data="genre_party")],
        [InlineKeyboardButton("Семейная", callback_data="genre_family")],
        [InlineKeyboardButton("Кооперативная", callback_data="genre_cooperative")],
        [InlineKeyboardButton("Абстрактная", callback_data="genre_abstract")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


def difficulty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Лёгкая", callback_data="difficulty_easy")],
        [InlineKeyboardButton("Средняя", callback_data="difficulty_medium")],
        [InlineKeyboardButton("Сложная", callback_data="difficulty_hard")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


def players_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2 игрока", callback_data="players_2")],
        [InlineKeyboardButton("3-4 игрока", callback_data="players_3-4")],
        [InlineKeyboardButton("5+ игроков", callback_data="players_5")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


def time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("До 30 минут", callback_data="time_short")],
        [InlineKeyboardButton("30-60 минут", callback_data="time_medium")],
        [InlineKeyboardButton("60+ минут", callback_data="time_long")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    message = (
        "👋 Привет! Я бот-помощник по подбору настольных игр.\n\n"
        "Я помогу выбрать игру по типу компании, жанру, сложности, количеству игроков и времени партии.\n"
        "Нажимай кнопки ниже или используй команды /types и /genres."
    )
    await update.message.reply_text(message, reply_markup=main_menu_keyboard())


async def types(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Выбери тип компании:", reply_markup=types_keyboard())


async def genres(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Выбери жанр:", reply_markup=genres_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    message = query.message
    if message is None or message.chat is None:
        return

    chat_id = message.chat.id

    try:
        text = update.effective_message.text if update.effective_message and update.effective_message.text else ""
        data = query.data or ""

        if data == "menu_types":
            await context.bot.send_message(chat_id=chat_id, text="🎲 По типу компании")
            await context.bot.send_message(chat_id=chat_id, text="Выбери тип компании:", reply_markup=types_keyboard())
            return

        if data == "menu_genres":
            await context.bot.send_message(chat_id=chat_id, text="🧩 По жанрам")
            await context.bot.send_message(chat_id=chat_id, text="Выбери жанр:", reply_markup=genres_keyboard())
            return

        if data == "menu_difficulty":
            await context.bot.send_message(chat_id=chat_id, text="⚙️ По сложности")
            await context.bot.send_message(chat_id=chat_id, text="Выбери сложность:", reply_markup=difficulty_keyboard())
            return

        if data == "menu_players":
            await context.bot.send_message(chat_id=chat_id, text="👥 По количеству игроков")
            await context.bot.send_message(chat_id=chat_id, text="Выбери количество игроков:", reply_markup=players_keyboard())
            return

        if data == "menu_time":
            await context.bot.send_message(chat_id=chat_id, text="⏱ По времени партии")
            await context.bot.send_message(chat_id=chat_id, text="Выбери длительность партии:", reply_markup=time_keyboard())
            return

        if data == "menu_stats":
            await context.bot.send_message(chat_id=chat_id, text="📊 Моя статистика")
            count = get_recommendation_count(query.from_user.id if query.from_user else 0)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 Твоя статистика\n\nТы запрашивал рекомендации {count} раз(а).",
                reply_markup=main_menu_keyboard(),
            )
            return

        if data == "menu_about":
            await context.bot.send_message(chat_id=chat_id, text="ℹ️ О боте")
            about_text = (
                "ℹ️ О боте\n\n"
                "Этот проект помогает подбирать настольные игры по CSV-базе.\n"
                "Бот умеет искать игры по жанру, типу компании, сложности, количеству игроков и времени партии.\n\n"
                "Статистика запросов хранится в JSON-файле."
            )
            await context.bot.send_message(chat_id=chat_id, text=about_text, reply_markup=main_menu_keyboard())
            return

        if data == "menu_back":
            await context.bot.send_message(chat_id=chat_id, text="⬅️ Назад")
            await context.bot.send_message(chat_id=chat_id, text="Главное меню:", reply_markup=main_menu_keyboard())
            return

        if data.startswith("type_"):
            category_key = data.replace("type_", "")
            games = choose_random_games(find_games_by_company(COMPANY_CATEGORIES.get(category_key, "")))
            if query.from_user:
                increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎲 Рекомендации по типу компании: {COMPANY_CATEGORIES.get(category_key, 'неизвестно')}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        if data.startswith("genre_"):
            genre_key = data.replace("genre_", "")
            games = choose_random_games(find_games_by_genre(GENRE_CATEGORIES.get(genre_key, "")))
            if query.from_user:
                increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧩 Рекомендации по жанру: {GENRE_CATEGORIES.get(genre_key, 'неизвестно')}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        if data.startswith("difficulty_"):
            diff_key = data.replace("difficulty_", "")
            games = choose_random_games(find_games_by_difficulty(DIFFICULTY_CATEGORIES.get(diff_key, "")))
            if query.from_user:
                increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚙️ Рекомендации по сложности: {DIFFICULTY_CATEGORIES.get(diff_key, 'неизвестно')}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        if data.startswith("players_"):
            player_key = data.replace("players_", "")
            games = choose_random_games(find_games_by_players(player_key))
            if query.from_user:
                increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"👥 Рекомендации по количеству игроков: {player_key}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        if data.startswith("time_"):
            time_key = data.replace("time_", "")
            games = choose_random_games(find_games_by_time(time_key))
            if query.from_user:
                increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏱ Рекомендации по времени партии: {time_key}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        await context.bot.send_message(chat_id=chat_id, text="Неизвестная команда меню. Попробуй вернуться в главное меню.", reply_markup=main_menu_keyboard())
    except Exception:
        logger.exception("Ошибка при обработке callback_query")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Произошла ошибка при обработке запроса. Попробуй ещё раз.", reply_markup=main_menu_keyboard())


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(
            "Я не увидел текст сообщения. Используй команды /start, /types или /genres.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if text.startswith("/"):
        await update.message.reply_text(
            "Неизвестная команда. Используй /start, /types или /genres.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "Я не знаю такой команды. Используй кнопки меню или команды /start, /types и /genres.",
        reply_markup=main_menu_keyboard(),
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Неизвестная команда. Используй /start, /types или /genres.", reply_markup=main_menu_keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Произошла ошибка в боте: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Внутренняя ошибка. Попробуй повторить действие чуть позже.", reply_markup=main_menu_keyboard())


def main() -> None:
    global GAMES

    if not TOKEN:
        raise RuntimeError("Переменная окружения TELEGRAM_BOT_TOKEN не найдена. Создай файл .env и добавь туда токен бота.")

    GAMES = load_games_from_csv()
    logger.info("Загружено игр из CSV: %s", len(GAMES))

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("types", types))
    application.add_handler(CommandHandler("genres", genres))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен...")
    asyncio.set_event_loop(asyncio.new_event_loop())
    application.run_polling()


if __name__ == "__main__":
    main()
