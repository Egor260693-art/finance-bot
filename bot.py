import os
import html
import time
import logging
import psycopg2
from psycopg2 import pool
import telebot
from telebot import types
from flask import Flask, request

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =============================================
# ТОКЕН БОТА
# =============================================
TOKEN = "НОВЫЙ_ТОКЕН_ОТ_BOTFATHER"
bot = telebot.TeleBot(TOKEN, threaded=False)

# =============================================
# ВЕБ-СЕРВЕР
# =============================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Бот работает!"

# =============================================
# БАЗА ДАННЫХ PostgreSQL
# =============================================
DATABASE_URL = os.environ.get('DATABASE_URL')

# Создаем пул соединений
connection_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=DATABASE_URL
)

def get_conn():
    return connection_pool.getconn()

def release_conn(conn):
    connection_pool.putconn(conn)

def init_db():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                note TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)

init_db()

def add_expense(user_id, amount, category, note=""):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO expenses (user_id, amount, category, note) VALUES (%s, %s, %s, %s)",
            (user_id, amount, category, note)
        )
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)

def get_total_today(user_id):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(amount) FROM expenses WHERE user_id = %s AND date::date = CURRENT_DATE",
            (user_id,)
        )
        total = cursor.fetchone()[0]
        cursor.close()
        return total if total else 0
    finally:
        release_conn(conn)

def get_total_week(user_id):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(amount) FROM expenses WHERE user_id = %s AND date >= CURRENT_DATE - INTERVAL '7 days'",
            (user_id,)
        )
        total = cursor.fetchone()[0]
        cursor.close()
        return total if total else 0
    finally:
        release_conn(conn)

def get_total_month(user_id):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(amount) FROM expenses WHERE user_id = %s AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE) AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE)",
            (user_id,)
        )
        total = cursor.fetchone()[0]
        cursor.close()
        return total if total else 0
    finally:
        release_conn(conn)

def get_stats_by_category(user_id, period='month'):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        if period == 'today':
            cursor.execute(
                "SELECT category, SUM(amount), COUNT(*) FROM expenses "
                "WHERE user_id = %s AND date::date = CURRENT_DATE "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (user_id,)
            )
        elif period == 'week':
            cursor.execute(
                "SELECT category, SUM(amount), COUNT(*) FROM expenses "
                "WHERE user_id = %s AND date >= CURRENT_DATE - INTERVAL '7 days' "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT category, SUM(amount), COUNT(*) FROM expenses "
                "WHERE user_id = %s AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE) AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE) "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (user_id,)
            )
        stats = cursor.fetchall()
        cursor.close()
        return stats
    finally:
        release_conn(conn)

def get_last_expenses(user_id, limit=10):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, amount, category, note, date FROM expenses "
            "WHERE user_id = %s ORDER BY date DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        release_conn(conn)

def delete_expense(expense_id, user_id):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM expenses WHERE id = %s AND user_id = %s",
            (expense_id, user_id)
        )
        conn.commit()
        cursor.close()
    finally:
        release_conn(conn)

# =============================================
# КАТЕГОРИИ
# =============================================
CATEGORIES = [
    "🍔 Еда",
    "🏠 Жильё",
    " Развлечения",
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
    " Сигареты",
    "⚡ Энергетики",
    "🔧 Другое",
]

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
    markup.add(types.InlineKeyboardButton(" Назад в меню", callback_data="back_to_main"))
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

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if call.data == "add_expense":
        bot.edit_message_text(
            " <b>Введи сумму расхода:</b>\n\n<i>Просто отправь число в чат (например, 150)</i>",
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
        stats = get_stats_by_category(user_id, 'month')
        total = get_total_month(user_id)
        
        text = f"📊 <b>Статистика за месяц:</b>\n\n"
        
        if stats:
            for cat, summ, count in stats:
                safe_cat = html.escape(cat)
                text += f"{safe_cat}: <b>{summ} руб.</b>\n"
        else:
            text += "📭 Нет записей за месяц.\n"
        
        text += f"\n━━━━━━━━━━\n💸 <b>Всего: {total} руб.</b>\n\n"
        text += "<i>Выбери период:</i>"
        
        bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=stats_markup())

    elif call.data == "stat_today":
        show_category_stats(call, 'today', ' За сегодня')
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
            " <b>Пусто.</b>", call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=back_markup()
        )
        return
    text = "📋 <b>Последние записи:</b>\n━━━━━━━━━━\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for exp_id, amount, category, note, date in rows:
        safe_category = html.escape(category)
        safe_note = html.escape(note) if note else ""
        note_text = f" — {safe_note}" if safe_note else ""
        text += f"▫️ <b>{amount} руб.</b> — {safe_category}{note_text}\n   📅 {str(date)[:16]}\n"
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
# ЗАПУСК WEBHOOK
# =============================================
RENDER_DOMAIN = "https://finance-bot-1-x0n2.onrender.com"
WEBHOOK_URL_PATH = f"/{TOKEN}"

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    logging.info(" Получено обновление от Telegram")
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        logging.info(f"✅ Update ID: {update.update_id}")
        bot.process_new_updates([update])
        return '', 200
    else:
        logging.error("❌ Неверный Content-Type")
        return 'Unsupported Media Type', 415

if __name__ == '__main__':
    webhook_url = f"{RENDER_DOMAIN}{WEBHOOK_URL_PATH}"
    
    logging.info(f"✅ Устанавливаю webhook: {webhook_url}")
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"✅ Запуск сервера на порту {port}...")
    
    app.run(host='0.0.0.0', port=port)
