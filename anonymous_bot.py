import logging
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# НАСТРОЙКИ
BOT_TOKEN = "8496144555:AAGW9zAVmwijEke9P15_AentN24jzNktCac"
GROUP_ID = -1002988616762
ADMIN_IDS = [5485217196, 6763156697]

# БАЗА ДАННЫХ
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('support_bot.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                admin_id INTEGER,
                warnings INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                user_message_id INTEGER,
                group_message_id INTEGER,
                user_id INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flood (
                user_id INTEGER PRIMARY KEY,
                message_count INTEGER DEFAULT 0,
                last_message TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
    
    def create_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, admin_id) VALUES (?, ?)',
            (user_id, ADMIN_IDS[0])
        )
        self.conn.commit()
    
    def assign_admin(self, user_id, admin_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE users SET admin_id = ? WHERE user_id = ?',
            (admin_id, user_id)
        )
        self.conn.commit()
    
    def get_assigned_admin(self, user_id):
        user = self.get_user(user_id)
        return user[1] if user else None
    
    def add_warning(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE users SET warnings = warnings + 1 WHERE user_id = ?',
            (user_id,)
        )
        self.conn.commit()
        return self.get_warnings(user_id)
    
    def remove_warning(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE users SET warnings = warnings - 1 WHERE user_id = ? AND warnings > 0',
            (user_id,)
        )
        self.conn.commit()
        return self.get_warnings(user_id)
    
    def get_warnings(self, user_id):
        user = self.get_user(user_id)
        return user[2] if user else 0
    
    def ban_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def unban_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def is_banned(self, user_id):
        user = self.get_user(user_id)
        return bool(user[3]) if user else False
    
    def save_message(self, user_message_id, group_message_id, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO messages VALUES (?, ?, ?)',
            (user_message_id, group_message_id, user_id)
        )
        self.conn.commit()
    
    def get_user_message_id(self, group_message_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT user_message_id, user_id FROM messages WHERE group_message_id = ?',
            (group_message_id,)
        )
        return cursor.fetchone()
    
    def get_group_message_id(self, user_message_id, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT group_message_id FROM messages WHERE user_message_id = ? AND user_id = ?',
            (user_message_id, user_id)
        )
        result = cursor.fetchone()
        return result[0] if result else None
    
    def update_flood(self, user_id):
        cursor = self.conn.cursor()
        now = datetime.now()
        
        cursor.execute('SELECT * FROM flood WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.execute(
                'INSERT INTO flood (user_id, message_count, last_message) VALUES (?, 1, ?)',
                (user_id, now)
            )
            self.conn.commit()
            return 1, False
        
        message_count, last_message = result[1], result[2]
        time_diff = (now - datetime.fromisoformat(last_message)).total_seconds()
        
        if time_diff < 10:
            message_count += 1
        else:
            message_count = 1
        
        cursor.execute(
            'UPDATE flood SET message_count = ?, last_message = ? WHERE user_id = ?',
            (message_count, now, user_id)
        )
        self.conn.commit()
        
        return message_count, message_count >= 5

db = Database()

# НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(level=logging.INFO)

# КОМАНДЫ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "Приветствую тебя, напиши админам о своей проблеме, а так же прочти закреп👆"
    )

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    
    reply_msg = update.message.reply_to_message
    
    # ИЩЕМ user_id ИЗ БАЗЫ ДАННЫХ
    result = db.get_user_message_id(reply_msg.message_id)
    if not result:
        await update.message.reply_text("❌ Не могу определить пользователя")
        return
    
    user_message_id, user_id = result
    
    # ПРОВЕРКА ТЕГОВ - админ должен быть закреплен за клиентом
    assigned_admin = db.get_assigned_admin(user_id)
    if assigned_admin != update.effective_user.id:
        await update.message.reply_text("❌ Вы не закреплены за этим клиентом")
        return
    
    reason = " ".join(context.args) if context.args else "Не указана"
    warnings_count = db.add_warning(user_id)
    
    # Сообщение в группе
    await update.message.reply_text(f"⚠️ Пользователю выдано предупреждение №{warnings_count}/3")
    
    # Сообщение пользователю
    await context.bot.send_message(
        user_id,
        f"🔔 Вы получили предупреждение №{warnings_count} из 3. Причина: {reason}"
    )
    
    # Автобан после 3 варнов
    if warnings_count >= 3:
        db.ban_user(user_id)
        await context.bot.send_message(user_id, "❌ Вы в черном списке ❌")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    
    reply_msg = update.message.reply_to_message
    
    # ИЩЕМ user_id ИЗ БАЗЫ ДАННЫХ
    result = db.get_user_message_id(reply_msg.message_id)
    if not result:
        await update.message.reply_text("❌ Не могу определить пользователя")
        return
    
    user_message_id, user_id = result
    
    # ПРОВЕРКА ТЕГОВ
    assigned_admin = db.get_assigned_admin(user_id)
    if assigned_admin != update.effective_user.id:
        await update.message.reply_text("❌ Вы не закреплены за этим клиентом")
        return
    
    warnings_count = db.remove_warning(user_id)
    await update.message.reply_text(f"✅ Снято предупреждение. Теперь: {warnings_count}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    
    reply_msg = update.message.reply_to_message
    
    # ИЩЕМ user_id ИЗ БАЗЫ ДАННЫХ
    result = db.get_user_message_id(reply_msg.message_id)
    if not result:
        await update.message.reply_text("❌ Не могу определить пользователя")
        return
    
    user_message_id, user_id = result
    
    db.ban_user(user_id)
    await context.bot.send_message(user_id, "❌ Вы в черном списке ❌")
    await update.message.reply_text("✅ Пользователь забанен")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    
    reply_msg = update.message.reply_to_message
    
    # ИЩЕМ user_id ИЗ БАЗЫ ДАННЫХ
    result = db.get_user_message_id(reply_msg.message_id)
    if not result:
        await update.message.reply_text("❌ Не могу определить пользователя")
        return
    
    user_message_id, user_id = result
    
    db.unban_user(user_id)
    await context.bot.send_message(user_id, "✅ Можешь писать своему админу")
    await update.message.reply_text("✅ Пользователь разбанен")

async def rass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /rass (текст рассылки)")
        return
    
    broadcast_text = " ".join(context.args)
    
    # Получаем всех пользователей из базы
    cursor = db.conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    
    sent_count = 0
    error_count = 0
    
    for user in users:
        user_id = user[0]
        try:
            await context.bot.send_message(user_id, broadcast_text)
            sent_count += 1
        except:
            error_count += 1
    
    await update.message.reply_text(
        f"✅ Рассылка завершена!\n"
        f"📤 Отправлено: {sent_count}\n"
        f"❌ Ошибок: {error_count}"
    )

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    cursor = db.conn.cursor()
    
    # Общее количество пользователей
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Забаненные
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = cursor.fetchone()[0]
    
    # Активные (не забаненные)
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 0')
    active_users = cursor.fetchone()[0]
    
    # Пользователи с варнами
    cursor.execute('SELECT COUNT(*) FROM users WHERE warnings > 0')
    warned_users = cursor.fetchone()[0]
    
    # Админы онлайн (примерно)
    online_admins = len(ADMIN_IDS)
    
    stats_text = (
        f"📊 СТАТИСТИКА БОТА:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Активных: {active_users}\n"
        f"❌ Забаненных: {banned_users}\n"
        f"⚠️ С варнами: {warned_users}\n"
        f"🟢 Админов онлайн: {online_admins}\n\n"
        f"🔄 Бот работает стабильно"
    )
    
    await update.message.reply_text(stats_text)

# ОБРАБОТЧИКИ СООБЩЕНИЙ
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if db.is_banned(user_id):
        return
    
    # ЗАЩИТА ОТ ФЛУДА
    message_count, is_flooding = db.update_flood(user_id)
    if is_flooding:
        db.ban_user(user_id)
        await context.bot.send_message(user_id, "❌ Вы в черном списке за флуд ❌")
        return
    
    db.create_user(user_id)
    
    # Пересылаем сообщение в группу
    try:
        forwarded_msg = await update.message.forward(GROUP_ID)
        db.save_message(update.message.message_id, forwarded_msg.message_id, user_id)
    except Exception as e:
        print(f"Ошибка пересылки: {e}")

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.message.reply_to_message:
        return
    
    reply_msg = update.message.reply_to_message
    result = db.get_user_message_id(reply_msg.message_id)
    
    if not result:
        return
    
    user_message_id, user_id = result
    
    if db.is_banned(user_id):
        await update.message.reply_text("❌ Этот пользователь забанен")
        return
    
    # АВТОЗАКРЕПЛЕНИЕ АДМИНА ПРИ ОТВЕТЕ
    current_admin = db.get_assigned_admin(user_id)
    if not current_admin or current_admin != update.effective_user.id:
        db.assign_admin(user_id, update.effective_user.id)
    
    # Пересылаем ответ пользователю ПОЛНОСТЬЮ АНОНИМНО
    try:
        # ВСЕГДА копируем сообщение как от бота
        if update.message.text:
            sent_msg = await context.bot.send_message(
                chat_id=user_id,
                text=update.message.text
            )
        elif update.message.photo:
            sent_msg = await context.bot.send_photo(
                chat_id=user_id,
                photo=update.message.photo[-1].file_id,
                caption=update.message.caption
            )
        elif update.message.video:
            sent_msg = await context.bot.send_video(
                chat_id=user_id,
                video=update.message.video.file_id,
                caption=update.message.caption
            )
        elif update.message.document:
            sent_msg = await context.bot.send_document(
                chat_id=user_id,
                document=update.message.document.file_id,
                caption=update.message.caption
            )
        elif update.message.voice:
            sent_msg = await context.bot.send_voice(
                chat_id=user_id,
                voice=update.message.voice.file_id
            )
        elif update.message.sticker:
            sent_msg = await context.bot.send_sticker(
                chat_id=user_id,
                sticker=update.message.sticker.file_id
            )
        elif update.message.audio:
            sent_msg = await context.bot.send_audio(
                chat_id=user_id,
                audio=update.message.audio.file_id,
                caption=update.message.caption
            )
        elif update.message.animation:
            sent_msg = await context.bot.send_animation(
                chat_id=user_id,
                animation=update.message.animation.file_id
            )
        else:
            # Для неизвестных типов - отправляем текстом
            sent_msg = await context.bot.send_message(
                chat_id=user_id,
                text="📨 Сообщение от админа"
            )
        
        db.save_message(sent_msg.message_id, update.message.message_id, user_id)
        
    except Exception as e:
        await update.message.reply_text("❌ Не удалось отправить сообщение")
        print(f"Ошибка: {e}")

# СКВОЗНОЕ РЕДАКТИРОВАНИЕ
async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    edited_msg = update.edited_message
    
    if edited_msg.chat.id == GROUP_ID:
        result = db.get_user_message_id(edited_msg.message_id)
        if result:
            user_message_id, user_id = result
            new_text = edited_msg.text or edited_msg.caption
            if new_text:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=user_message_id,
                        text=new_text
                    )
                except:
                    pass
    else:
        group_message_id = db.get_group_message_id(edited_msg.message_id, edited_msg.chat.id)
        if group_message_id:
            new_text = edited_msg.text or edited_msg.caption
            if new_text:
                try:
                    await context.bot.edit_message_text(
                        chat_id=GROUP_ID,
                        message_id=group_message_id,
                        text=new_text
                    )
                except:
                    pass

# ЗАПУСК БОТА
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("unwarn", unwarn))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("rass", rass))
    application.add_handler(CommandHandler("stat", stat))
    
    # Сообщения
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_private_message
    ))
    application.add_handler(MessageHandler(
        filters.Chat(GROUP_ID) & ~filters.COMMAND,
        handle_group_message
    ))
    
    # Редактирование
    application.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE,
        handle_edited_message
    ))
    
    # Запуск
    print("🚀 Бот запущен! ПОЛНАЯ анонимность!")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
