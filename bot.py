import os
# =============================================
# ПРИНУДИТЕЛЬНО ОТКЛЮЧАЕМ ВСЕ ПРОКСИ (ДО ВСЕХ ИМПОРТОВ)
# =============================================
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ftp_proxy', 'FTP_PROXY']:
    os.environ.pop(key, None)

import telebot
from telebot import apihelper
from telebot import types
import sqlite3
from datetime import datetime

# =============================================
# ЯВНО ОТКЛЮЧАЕМ ПРОКСИ В БИБЛИОТЕКЕ
# =============================================
apihelper.proxy = None

# =============================================
# ТОКЕН БОТА (ЗАМЕНИТЕ НА НОВЫЙ!)
# =============================================
TOKEN = "8805553209:AAH-cnePIF0OO_XxD6r0G-Ug7ymuW1dwGFc"
bot = telebot.TeleBot(TOKEN)

# =============================================
# БАЗА ДАННЫХ
# =============================================
def init_db():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            note TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def add_expense(user_id, amount, category, note=""):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO expenses (user_id, amount, category, note) VALUES (?, ?, ?, ?)",
        (user_id, amount, category, note)
    )
    conn.commit()
    conn.close()

def get_total_today(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= date('now')", (user_id,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0

def get_total_month(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')", (user_id,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0

def get_total_week(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= date('now', '-7 days')", (user_id,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0

def get_stats_by_category(user_id, period='month'):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    if period == 'today':
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses WHERE user_id = ? AND date >= date('now') GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    elif period == 'week':
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses WHERE user_id = ? AND date >= date('now', '-7 days') GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    else:
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now') GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    stats = cursor.fetchall()
    conn.close()
    return stats

def get_last_expenses(user_id, limit=10):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, category, note, date FROM expenses WHERE user_id = ? ORDER BY date DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_expense(expense_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

# =============================================
# КАТЕГОРИИ
# =============================================
CATEGORIES = [
    "🍔 Еда",
    "🚌 Транспорт",
    "🏠 Жильё",
    "🎮 Развлечения",
    "💊 Здоровье",
    "📚 Образование",
    "👕 Одежда",
    "💄 Красота",
    "🐱 Питомцы",
    "🎁 Подарки",
    "💻 Техника",
    "💡 Коммуналка",
    "📱 Связь",
    "🏃 Спорт",
    "✈️ Путешествия",
    "🔧 Другое"
]

# =============================================
# КЛАВИАТУРЫ (INLINE-КНОПКИ)
# =============================================
def main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить расход", callback_data="add_expense"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        types.InlineKeyboardButton("📋 Последние записи", callback_data="last"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup

def categories_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for cat in CATEGORIES:
        buttons.append(types.InlineKeyboardButton(cat, callback_data=f"cat_{cat}"))
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cancel"))
    return markup

def stats_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("📅 Сегодня", callback_data="stat_today"),
        types.InlineKeyboardButton("📆 Неделя", callback_data="stat_week"),
        types.InlineKeyboardButton("🗓 Месяц", callback_data="stat_month"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    return markup

def back_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main"))
    return markup

# =============================================
# КОМАНДА /start
# =============================================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 <b>Добро пожаловать в FinanceBot!</b>\n\n"
        "Я помогу тебе следить за финансами легко и удобно.\n\n"
        "<i>Выбери действие:</i>",
        parse_mode="HTML",
        reply_markup=main_menu_markup()
    )

# =============================================
# ОБРАБОТКА INLINE-КНОПОК
# =============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # --- ДОБАВЛЕНИЕ РАСХОДА ---
    if call.data == "add_expense":
        bot.edit_message_text(
            "💰 <b>Введи сумму расхода:</b>\n\n"
            "<i>Просто отправь число в чат (например, 150 или 99.90)</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=back_markup()
        )
        bot.register_next_step_handler(call.message, process_amount_step)

    # --- ВЫБОР КАТЕГОРИИ ---
    elif call.data.startswith("cat_"):
        category = call.data[4:]
        bot.edit_message_text(
            f"📂 Категория: <b>{category}</b>\n\n"
            "✏️ <i>Введи комментарий (или отправь '-' чтобы пропустить):</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=back_markup()
        )
        bot.register_next_step_handler(call.message, process_note_step, category, call)

    # --- СТАТИСТИКА ---
    elif call.data == "stats":
        today = get_total_today(user_id)
        week = get_total_week(user_id)
        month = get_total_month(user_id)
        text = (
            "📊 <b>Статистика расходов:</b>\n\n"
            f"📅 Сегодня: <b>{today} руб.</b>\n"
            f"📆 За неделю: <b>{week} руб.</b>\n"
            f"🗓 За месяц: <b>{month} руб.</b>\n\n"
            "<i>Выбери период для детализации:</i>"
        )
        bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=stats_markup())

    elif call.data == "stat_today":
        show_category_stats(call, 'today', '📅 За сегодня')
    elif call.data == "stat_week":
        show_category_stats(call, 'week', '📆 За неделю')
    elif call.data == "stat_month":
        show_category_stats(call, 'month', '🗓 За месяц')

    # --- ПОСЛЕДНИЕ ЗАПИСИ ---
    elif call.data == "last":
        show_last_expenses(call)

    # --- УДАЛЕНИЕ ЗАПИСИ ---
    elif call.data.startswith("del_"):
        expense_id = int(call.data[4:])
        delete_expense(expense_id)
        bot.answer_callback_query(call.id, "✅ Запись удалена!")
        show_last_expenses(call)

    # --- ПОМОЩЬ ---
    elif call.data == "help":
        text = (
            "ℹ️ <b>Как пользоваться ботом:</b>\n\n"
            "1️⃣ Нажми <b>«Добавить расход»</b> и следуй инструкциям.\n"
            "2️⃣ Смотри <b>«Статистику»</b> за день, неделю и месяц.\n"
            "3️⃣ Просматривай и удаляй <b>«Последние записи»</b>.\n\n"
            "🔒 Все данные хранятся в базе. Никто, кроме тебя, их не увидит.\n\n"
            "<i>Бот работает полностью бесплатно!</i>"
        )
        bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=back_markup())

    # --- НАЗАД В МЕНЮ ---
    elif call.data == "back_to_main":
        bot.edit_message_text(
            "👋 <b>Главное меню</b>\n\n<i>Выбери действие:</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=main_menu_markup()
        )

    # --- ОТМЕНА ---
    elif call.data == "cancel":
        bot.edit_message_text(
            "❌ Действие отменено.",
            chat_id, message_id, reply_markup=main_menu_markup()
        )

# =============================================
# ШАГИ ДОБАВЛЕНИЯ РАСХОДА
# =============================================
user_amounts = {}

def process_amount_step(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            bot.send_message(message.chat.id, "⚠️ Сумма должна быть положительной. Попробуй ещё раз:")
            bot.register_next_step_handler(message, process_amount_step)
            return
        user_amounts[user_id] = amount
        bot.send_message(
            message.chat.id,
            "📂 <b>Выбери категорию:</b>",
            parse_mode="HTML",
            reply_markup=categories_markup()
        )
    except:
        bot.send_message(message.chat.id, "⚠️ Это не число. Введи сумму цифрами (например, 150 или 99.90):")
        bot.register_next_step_handler(message, process_amount_step)

def process_note_step(message, category, call=None):
    user_id = message.from_user.id
    amount = user_amounts.get(user_id, 0)
    note = "" if message.text.strip() == "-" else message.text.strip()

    add_expense(user_id, amount, category, note)

    note_text = f"\n📝 <i>{note}</i>" if note else ""
    bot.send_message(
        message.chat.id,
        f"✅ <b>Записано!</b>\n\n"
        f"💰 Сумма: <b>{amount} руб.</b>\n"
        f"📂 Категория: <b>{category}</b>{note_text}",
        parse_mode="HTML",
        reply_markup=main_menu_markup()
    )

# =============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================
def show_category_stats(call, period, period_name):
    user_id = call.from_user.id
    stats = get_stats_by_category(user_id, period)

    if period == 'today':
        total = get_total_today(user_id)
    elif period == 'week':
        total = get_total_week(user_id)
    else:
        total = get_total_month(user_id)

    text = f"📊 <b>Статистика: {period_name}</b>\n"
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"💸 Всего: <b>{total} руб.</b>\n\n"

    if stats:
        for cat, summ, count in stats:
            percent = (summ / total * 100) if total > 0 else 0
            bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
            text += f"{cat}\n"
            text += f"┣ {summ} руб. ({percent:.1f}%)\n"
            text += f"┣ {bar}\n"
            text += f"┗ {count} зап.\n\n"
    else:
        text += "📭 Записей за этот период нет."

    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=back_markup()
    )

def show_last_expenses(call):
    user_id = call.from_user.id
    rows = get_last_expenses(user_id)

    if not rows:
        bot.edit_message_text(
            "📭 <b>Записей пока нет.</b>",
            call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=back_markup()
        )
        return

    text = "📋 <b>Последние записи:</b>\n━━━━━━━━━━━━━━━\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)

    for exp_id, amount, category, note, date in rows:
        note_text = f" — {note}" if note else ""
        date_short = date[:16] if len(date) > 16 else date
        text += f"▫️ <b>{amount} руб.</b> — {category}{note_text}\n"
        text += f"   📅 {date_short}\n"
        markup.add(types.InlineKeyboardButton(f"🗑 Удалить: {amount}р. {category}", callback_data=f"del_{exp_id}"))

    text += "\n<i>Нажми на кнопку ниже чтобы удалить запись:</i>"
    markup.add(types.InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main"))

    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=markup
    )

# =============================================
# ОБРАБОТКА ОБЫЧНЫХ СООБЩЕНИЙ
# =============================================
@bot.message_handler(func=lambda msg: True)
def handle_text(msg):
    if msg.text == "/start":
        return
    bot.send_message(
        msg.chat.id,
        "🤔 Используй кнопки в меню для навигации.\n"
        "Напиши /start чтобы вернуться в главное меню.",
        reply_markup=main_menu_markup()
    )

# =============================================
# ЗАПУСК БОТА
# =============================================
print("✅ Бот запущен и готов к работе!")
print("📱 Открой Telegram и напиши /start своему боту!")
bot.polling(none_stop=True)