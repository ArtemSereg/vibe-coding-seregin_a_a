"""Telegram-бот-помощник по подбору настольных игр.

Бот написан на библиотеке python-telegram-bot и использует JSON-файл для хранения
статистики пользователей. Встроенная база игр находится прямо в коде, поэтому
бот можно запустить сразу после установки зависимостей и указания токена.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STATS_FILE = BASE_DIR / "stats.json"


@dataclass(frozen=True)
class BoardGame:
    name: str
    players: str
    genres: List[str]
    description: str


GAMES: List[BoardGame] = [
    BoardGame("Каркассон", "2-5", ["стратегии", "семейные"], "Классическая игра о выкладывании тайлов и развитии территории."),
    BoardGame("Колонизаторы", "3-4", ["стратегии", "экономические"], "Игра про развитие поселений, торговлю ресурсами и тактику."),
    BoardGame("Детектив: Игра о современном расследовании", "1-5", ["детективы"], "Кооперативное расследование с поиском улик и анализом базы данных."),
    BoardGame("Имаджинариум", "4-7", ["пати-геймы", "семейные"], "Игра на ассоциации, фантазию и яркое общение в компании."),
    BoardGame("Манчкин", "3-6", ["пати-геймы"], "Сатирическая карточная игра с юмором, подставами и прокачкой героя."),
    BoardGame("7 чудес", "3-7", ["стратегии", "экономические"], "Драфт карт, развитие цивилизации и борьба за победные очки."),
    BoardGame("Азул", "2-4", ["семейные", "стратегии"], "Красивый абстрактный пазл про выкладку плиток и планирование ходов."),
    BoardGame("Саботёр", "3-10", ["пати-геймы"], "Блеф, скрытые роли и попытка добыть золото быстрее соперников."),
    BoardGame("Пандемия", "2-4", ["семейные", "стратегии"], "Кооперативная игра о спасении мира от распространения болезней."),
    BoardGame("Root", "2-4", ["стратегии"], "Асимметричная стратегия о борьбе фракций за контроль над лесом."),
    BoardGame("Кодовые имена", "4-8", ["пати-геймы", "семейные"], "Командная игра на ассоциации и угадывание тайных слов."),
    BoardGame("Остров духов", "1-4", ["стратегии", "соло"], "Сложная кооперативная стратегия о защите острова от захватчиков."),
    BoardGame("Шерлок Холмс: Детектив-консультант", "1-8", ["детективы", "соло"], "Сюжетные расследования с чтением улик и дедукцией."),
    BoardGame("BANG!", "4-7", ["пати-геймы"], "Дикий Запад, скрытые роли и перестрелки между шерифом и бандитами."),
    BoardGame("Terraforming Mars", "1-5", ["экономические", "стратегии", "соло"], "Глубокая экономическая стратегия о терраформировании Марса."),
]

TYPE_CATEGORIES: Dict[str, str] = {
    "for_two": "для двоих",
    "for_group": "для большой компании",
    "family": "семейные",
    "solo": "соло",
}

GENRE_CATEGORIES: Dict[str, str] = {
    "strategies": "стратегии",
    "detectives": "детективы",
    "economic": "экономические",
    "party": "пати-геймы",
}


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


def find_games_by_genre(genre_name: str) -> List[BoardGame]:
    return [game for game in GAMES if genre_name in game.genres]


def find_games_by_type(category_key: str) -> List[BoardGame]:
    if category_key == "for_two":
        return [game for game in GAMES if game.players.startswith("2") or game.players.startswith("1-2")]
    if category_key == "for_group":
        return [game for game in GAMES if any(x in game.players for x in ["5", "6", "7", "8", "9", "10"])]
    if category_key == "family":
        return [game for game in GAMES if "семейные" in game.genres]
    if category_key == "solo":
        return [game for game in GAMES if "соло" in game.genres or game.players.startswith("1")]
    return []


def choose_random_games(games: List[BoardGame], count: int = 3) -> List[BoardGame]:
    if not games:
        return []
    return random.sample(games, k=min(count, len(games)))


def format_games(games: List[BoardGame]) -> str:
    if not games:
        return "К сожалению, подходящих игр не нашлось."
    lines = []
    for game in games:
        lines.append(
            f"• <b>{game.name}</b>\n"
            f"  Игроки: {game.players}\n"
            f"  Жанры: {', '.join(game.genres)}\n"
            f"  Описание: {game.description}"
        )
    return "\n\n".join(lines)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 По типу компании", callback_data="menu_types")],
        [InlineKeyboardButton("🧩 По жанрам", callback_data="menu_genres")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="menu_stats")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="menu_about")],
    ])


def types_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Для двоих", callback_data="type_for_two")],
        [InlineKeyboardButton("Для большой компании", callback_data="type_for_group")],
        [InlineKeyboardButton("Семейные", callback_data="type_family")],
        [InlineKeyboardButton("Соло", callback_data="type_solo")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


def genres_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Стратегии", callback_data="genre_strategies")],
        [InlineKeyboardButton("Детективы", callback_data="genre_detectives")],
        [InlineKeyboardButton("Экономические", callback_data="genre_economic")],
        [InlineKeyboardButton("Пати-геймы", callback_data="genre_party")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu_back")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "👋 Привет! Я бот-помощник по подбору настольных игр.\n\n"
        "Я помогу выбрать игру по типу компании или по жанру.\n"
        "Нажимай кнопки ниже в самом сообщении."
    )
    await update.message.reply_text(message, reply_markup=main_menu_keyboard())


async def types(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбери тип компании, и я предложу подходящие настолки:", reply_markup=types_keyboard())


async def genres(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбери жанр, и я предложу подходящие настольные игры:", reply_markup=genres_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        chat_id = query.message.chat_id
        text = query.message.text or ""
        data = query.data

        # Отправляем в чат сообщение, имитирующее выбор пользователя,
        # чтобы история переписки выглядела естественно.
        if data == "menu_types":
            await context.bot.send_message(chat_id=chat_id, text="🎲 По типу компании")
            await context.bot.send_message(chat_id=chat_id, text="Выбери тип компании, и я предложу подходящие настолки:", reply_markup=types_keyboard())
            return

        if data == "menu_genres":
            await context.bot.send_message(chat_id=chat_id, text="🧩 По жанрам")
            await context.bot.send_message(chat_id=chat_id, text="Выбери жанр, и я предложу подходящие настольные игры:", reply_markup=genres_keyboard())
            return

        if data == "menu_stats":
            await context.bot.send_message(chat_id=chat_id, text="📊 Моя статистика")
            count = get_recommendation_count(query.from_user.id)
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
                "Этот проект помогает подбирать настольные игры по типу компании и жанру.\n"
                "Бот хранит простую статистику запросов в JSON-файле и содержит встроенную базу популярных игр.\n\n"
                "Создан для быстрого и понятного подбора настолок в дружеской, семейной или соло-компании."
            )
            await context.bot.send_message(chat_id=chat_id, text=about_text, reply_markup=main_menu_keyboard())
            return

        if data == "menu_back":
            await context.bot.send_message(chat_id=chat_id, text="⬅️ Назад")
            await context.bot.send_message(chat_id=chat_id, text="Главное меню:", reply_markup=main_menu_keyboard())
            return

        if data.startswith("type_"):
            category_key = data.replace("type_", "")
            games = choose_random_games(find_games_by_type(category_key))
            increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎲 Рекомендации по типу: {TYPE_CATEGORIES.get(category_key, 'неизвестно')}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        if data.startswith("genre_"):
            genre_key = data.replace("genre_", "")
            genre_name = GENRE_CATEGORIES.get(genre_key, "")
            games = choose_random_games(find_games_by_genre(genre_name))
            increase_recommendation_count(query.from_user.id)
            await context.bot.send_message(chat_id=chat_id, text=text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧩 Рекомендации по жанру: {genre_name}\n\n{format_games(games)}",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            return

        await context.bot.send_message(chat_id=chat_id, text="Неизвестная команда меню. Попробуй вернуться в главное меню.", reply_markup=main_menu_keyboard())
    except Exception as error:
        logger.exception("Ошибка при обработке callback_query: %s", error)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Произошла ошибка при обработке запроса. Попробуй ещё раз.", reply_markup=main_menu_keyboard())


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Неизвестная команда. Используй /start, /types или /genres.", reply_markup=main_menu_keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Произошла ошибка в боте: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Внутренняя ошибка. Попробуй повторить действие чуть позже.", reply_markup=main_menu_keyboard())


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Переменная окружения TELEGRAM_BOT_TOKEN не найдена. Создай файл .env и добавь туда токен бота.")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("types", types))
    application.add_handler(CommandHandler("genres", genres))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен...")

    # В Python 3.14 у некоторых конфигураций может не быть текущего event loop.
    # Создаём его явно, чтобы python-telegram-bot мог запуститься корректно.
    asyncio.set_event_loop(asyncio.new_event_loop())
    application.run_polling()


if __name__ == "__main__":
    main()
