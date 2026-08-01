import os
import html
import time
import sqlite3
import telebot
from telebot import types
from threading import Thread
from flask import Flask, request

# =============================================
# ТОКЕН БОТА (ЗАМЕНИТЕ НА ВАШ!)
# =============================================
TOKEN = "8805553209:AAH-cnePIF0OO_XxD6r0G-Ug7ymuW1dwGFc"
bot = telebot.TeleBot(TOKEN)

# =============================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER (ЗАПУСКАЕТСЯ ПЕРВЫМ)
# =============================================
app = Flask(__name__)


@app.route('/')
def home():
    return "✅ Бот работает!"


def run_flask():
    # Render передаёт порт через переменную окружения PORT.
    # Если её нет (локальный запуск) - используем 10000 как раньше.
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


# =============================================
# БАЗА ДАННЫХ
# =============================================
DB_PATH = 'finance.db'


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    conn = get_conn()
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
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO expenses (user_id, amount, category, note) VALUES (?, ?, ?, ?)",
        (user_id, amount, category, note)
    )
    conn.commit()
    conn.close()


def get_total_today(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= date('now')",
        (user_id,)
    )
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0


def get_total_week(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date >= date('now', '-7 days')",
        (user_id,)
    )
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0


def get_total_month(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')",
        (user_id,)
    )
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0


def get_stats_by_category(user_id, period='month'):
    conn = get_conn()
    cursor = conn.cursor()
    if period == 'today':
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses "
            "WHERE user_id = ? AND date >= date('now') "
            "GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    elif period == 'week':
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses "
            "WHERE user_id = ? AND date >= date('now', '-7 days') "
            "GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    else:
        cursor.execute(
            "SELECT category, SUM(amount), COUNT(*) FROM expenses "
            "WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now') "
            "GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,)
        )
    stats = cursor.fetchall()
    conn.close()
    return stats


def get_last_expenses(user_id, limit=10):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, amount, category, note, date FROM expenses "
        "WHERE user_id = ? ORDER BY date DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_expense(expense_id, user_id):
    # ВАЖНО: удаляем только если запись принадлежит этому user_id -
    # иначе один пользователь мог бы удалить чужой расход, зная/подобрав id.
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id)
    )
    conn.commit()
    conn.close()


# =============================================
# КАТЕГОРИИ
# =============================================
CATEGORIES = [
    "🍔 Еда",
    "🏠 Жильё",
    "🎮 Развлечения",
    "💊 Здоровье",
    "👕 Одежда",
    "💄 Красота",
    "💡 Коммуналка",
    "📱 Связь",
    "👧 Ника",
    "⛽ Бензин",
    "💳 Кредит",
    "🏖️ Отдых",
    "🏥 Медицина",
    "💅 Бьюти",
    "🚬 Сигареты",
    "⚡ Энергетики",
    "🔧 Другое",
]

# Разумный верхний предел суммы одного расхода (защита от inf/nan/огромных чисел)
MAX_AMOUNT = 10_000_000


# =============================================
# КЛАВИАТУРЫ
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
    # Используем ИНДЕКС категории в callback_data, а не сам текст -
    # так короче (укладываемся в лимит Telegram 64 байта) и надёжнее.
    buttons = [
        types.InlineKeyboardButton(cat, callback_data=f"cat_{i}")
        for i, cat in enumerate(CATEGORIES)
    ]
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

    # Отвечаем на callback сразу, чтобы у пользователя не крутились "часики" на кнопке
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if call.data == "add_expense":
        bot.edit_message_text(
            "💰 <b>Введи сумму расхода:</b>\n\n<i>Просто отправь число в чат (например, 150)</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=back_markup()
        )
        bot.register_next_step_handler(call.message, process_amount_step)

    elif call.data.startswith("cat_"):
        try:
            cat_index = int(call.data[4:])
            category = CATEGORIES[cat_index]
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "⚠️ Неизвестная категория")
            return
        bot.edit_message_text(
            f"📂 Категория: <b>{html.escape(category)}</b>\n\n"
            f"✏️ <i>Введи комментарий (или '-' чтобы пропустить):</i>",
            chat_id, message_id, parse_mode="HTML", reply_markup=back_markup()
        )
        bot.register_next_step_handler(call.message, process_note_step, category)

    elif call.data == "stats":
        today = get_total_today(user_id)
        week = get_total_week(user_id)
        month = get_total_month(user_id)
        text = (
            f"📊 <b>Статистика:</b>\n\n"
            f"📅 Сегодня: <b>{today} руб.</b>\n"
            f"📆 Неделя: <b>{week} руб.</b>\n"
            f"🗓 Месяц: <b>{month} руб.</b>\n\n"
            f"<i>Выбери период:</i>"
        )
        bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=stats_markup())

    elif call.data == "stat_today":
        show_category_stats(call, 'today', '📅 За сегодня')
    elif call.data == "stat_week":
        show_category_stats(call, 'week', '📆 За неделю')
    elif call.data == "stat_month":
        show_category_stats(call, 'month', '🗓 За месяц')

    elif call.data == "last":
        show_last_expenses(call)

    elif call.data.startswith("del_"):
        try:
            expense_id = int(call.data[4:])
        except ValueError:
            return
        # Передаём user_id - удаляем только СВОИ расходы
        delete_expense(expense_id, user_id)
        bot.answer_callback_query(call.id, "✅ Удалено!")
        show_last_expenses(call)

    elif call.data == "help":
        text = (
            "ℹ️ <b>Помощь:</b>\n\n"
            "➕ Добавить расход\n📊 Статистика\n📋 Последние записи\n\n"
            "<i>Удали запись, нажав на кнопку под ней.</i>"
        )
        bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=back_markup())

    elif call.data == "back_to_main":
        bot.edit_message_text(
            "👋 <b>Главное меню</b>", chat_id, message_id,
            parse_mode="HTML", reply_markup=main_menu_markup()
        )

    elif call.data == "cancel":
        bot.edit_message_text("❌ Отменено.", chat_id, message_id, reply_markup=main_menu_markup())


# =============================================
# ШАГИ ДОБАВЛЕНИЯ
# =============================================
user_amounts = {}


def process_amount_step(message):
    user_id = message.from_user.id

    if message.content_type != 'text' or not message.text:
        bot.send_message(message.chat.id, "⚠️ Введи число (например, 150):")
        bot.register_next_step_handler(message, process_amount_step)
        return

    try:
        amount = float(message.text.replace(",", "."))
    except (ValueError, OverflowError):
        bot.send_message(message.chat.id, "⚠️ Введи корректное число (например, 150):")
        bot.register_next_step_handler(message, process_amount_step)
        return

    # Защита от inf / nan / отрицательных / абсурдно больших значений
    if not (0 < amount < MAX_AMOUNT):
        bot.send_message(
            message.chat.id,
            f"⚠️ Сумма должна быть положительным числом меньше {MAX_AMOUNT:,}!".replace(",", " ")
        )
        bot.register_next_step_handler(message, process_amount_step)
        return

    user_amounts[user_id] = amount
    bot.send_message(
        message.chat.id, "📂 <b>Выбери категорию:</b>",
        parse_mode="HTML", reply_markup=categories_markup()
    )


def process_note_step(message, category):
    user_id = message.from_user.id
    amount = user_amounts.pop(user_id, 0)

    if amount <= 0:
        # Сессия истекла / была прервана - просим начать заново
        bot.send_message(
            message.chat.id,
            "⚠️ Сессия добавления истекла. Начни заново через меню.",
            reply_markup=main_menu_markup()
        )
        return

    if message.content_type == 'text' and message.text:
        raw_note = message.text.strip()
        note = "" if raw_note == "-" else raw_note
    else:
        note = ""

    add_expense(user_id, amount, category, note)

    # Экранируем всё, что пришло от пользователя, перед вставкой в HTML-разметку
    safe_note = html.escape(note)
    safe_category = html.escape(category)

    note_text = f"\n📝 <i>{safe_note}</i>" if safe_note else ""
    bot.send_message(
        message.chat.id,
        f"✅ <b>Записано!</b>\n\n💰 {amount} руб.\n📂 {safe_category}{note_text}",
        parse_mode="HTML", reply_markup=main_menu_markup()
    )


def show_category_stats(call, period, name):
    user_id = call.from_user.id
    stats = get_stats_by_category(user_id, period)
    total = (
        get_total_today(user_id) if period == 'today'
        else get_total_week(user_id) if period == 'week'
        else get_total_month(user_id)
    )
    text = f"📊 <b>{name}</b>\n━━━━━━━━━━\n💸 Всего: <b>{total} руб.</b>\n\n"
    if stats:
        for cat, summ, count in stats:
            pct = (summ / total * 100) if total > 0 else 0
            filled = max(0, min(20, int(pct / 5)))
            bar = "█" * filled + "░" * (20 - filled)
            safe_cat = html.escape(cat)
            text += f"{safe_cat}\n┣ {summ} руб. ({pct:.1f}%)\n┣ {bar}\n┗ {count} зап.\n\n"
    else:
        text += "📭 Нет записей."
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=back_markup())


def show_last_expenses(call):
    user_id = call.from_user.id
    rows = get_last_expenses(user_id)
    if not rows:
        bot.edit_message_text(
            "📭 <b>Пусто.</b>", call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=back_markup()
        )
        return
    text = "📋 <b>Последние записи:</b>\n━━━━━━━━━━\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for exp_id, amount, category, note, date in rows:
        safe_category = html.escape(category)
        safe_note = html.escape(note) if note else ""
        note_text = f" — {safe_note}" if safe_note else ""
        text += f"▫️ <b>{amount} руб.</b> — {safe_category}{note_text}\n   📅 {date[:16]}\n"
        # Кнопка с эмодзи и суммой - текст короткий, category в button label не влияет на лимит callback_data
        btn_label = f"🗑 Удалить: {amount}р. {category}"[:64]
        markup.add(types.InlineKeyboardButton(btn_label, callback_data=f"del_{exp_id}"))
    text += "\n<i>Нажми на кнопку чтобы удалить:</i>"
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)


@bot.message_handler(func=lambda msg: True)
def handle_text(msg):
    if msg.text != "/start":
        bot.send_message(msg.chat.id, "🤔 Используй кнопки меню. /start — главное меню.", reply_markup=main_menu_markup())
# =============================================
# ЗАПУСК ЧЕРЕЗ WEBHOOK (Правильный способ для Render)
# =============================================

# УКАЖИ ЗДЕСЬ СВОЙ ДОМЕН ИЗ PANNELI RENDER!
# Пример: "https://my-bot.onrender.com" (БЕЗ слэша на конце)
RENDER_DOMAIN = "https://finance-bot-1-x0n2.onrender.com"

WEBHOOK_URL_PATH = f"/{TOKEN}"

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Unsupported Media Type', 415

if __name__ == '__main__':
    webhook_url = f"{RENDER_DOMAIN}{WEBHOOK_URL_PATH}"
    
    print(f"✅ Устанавливаю webhook: {webhook_url}")
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    
    port = int(os.environ.get("PORT", 10000))
    print(f"✅ Запуск сервера на порту {port}...")
    
    app.run(host='0.0.0.0', port=port)


