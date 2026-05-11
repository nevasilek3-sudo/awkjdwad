import os
import json
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from threading import Thread

# --- Configuration ---
# IMPORTANT: For production deployment on Render.com,
# it is highly recommended to set these as environment variables
# in your Render.com service settings for security reasons.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8735831453:AAFxz__CSMFDBsl4L_VkR7DctBan8AmATv8")
CHAT_ID = os.environ.get("CHAT_ID", "7111158209")
BASE_URL = os.environ.get("BASE_URL", "YOUR_RENDER_APP_URL_HERE") # e.g., "https://my-minecraft-bot.onrender.com"
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

WHITELIST_FILE = "whitelist.json"

def load_whitelist():
    if not os.path.exists(WHITELIST_FILE):
        return {}
    with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_whitelist(whitelist_data):
    with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(whitelist_data, f, indent=4, ensure_ascii=False)

# --- Flask App for Minecraft Client Communication ---
app = Flask(__name__)

# In-memory store for clients awaiting approval.
# Stores client_id -> { 'pc_name': '...', 'hwid': '...', 'processor': '...', 'gpu': '...', 'ram': '...', 'response_queue': asyncio.Queue() }
# response_queue will be used to hold the accept/deny decision for the client.
pending_clients = {}

@app.route('/minecraft_data', methods=['POST'])
async def minecraft_data():
    data = request.json
    pc_name = data.get('pc_name')
    hwid = data.get('hwid')
    processor = data.get('processor')
    gpu = data.get('gpu')
    ram = data.get('ram')
    client_id = hwid # Using HWID as a unique client identifier for now

    print(f"Received data from Minecraft client ({pc_name}): {data}")

    whitelist = load_whitelist()
    if hwid in whitelist:
        # Update HWID if it was a placeholder
        if whitelist[hwid]['hwid'].startswith("TEMP_HWID_"):
            whitelist[hwid]['hwid'] = hwid
            save_whitelist(whitelist)
        
        message = (
            f"Зарегистрированный клиент подключился: *{pc_name}* (в вайтлисте)\n"
            f"HWID: `{hwid}`\n"
            f"Процессор: `{processor}`\n"
            f"Видеокарта: `{gpu}`\n"
            f"ОЗУ: `{ram}`"
        )
        await bot_application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
        return jsonify({"status": "success", "action": "accept"})

    # Store client data and create a response queue
    response_queue = asyncio.Queue()
    pending_clients[client_id] = {
        'pc_name': pc_name,
        'hwid': hwid,
        'processor': processor,
        'gpu': gpu,
        'ram': ram,
        'response_queue': response_queue,
        'pc_name': pc_name, # Also store pc_name for easier lookup
        'hwid': hwid # Also store hwid for easier lookup
    }

    # Send info to Telegram
    message = (
        f"Новый клиент подключился: *{pc_name}*\n"
        f"HWID: `{hwid}`\n"
        f"Процессор: `{processor}`\n"
        f"Видеокарта: `{gpu}`\n"
        f"ОЗУ: `{ram}`\n\n"
        f"Подтвердить запуск: /accept {hwid}\n"
        f"Отклонить запуск: /deny {hwid}"
    )
    await bot_application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')

    print(f"Waiting for approval for client {pc_name} ({hwid})...")
    # Wait for response from Telegram
    response_action = await response_queue.get() # This will block until /accept or /deny is called

    print(f"Received response for client {pc_name}: {response_action}")
    del pending_clients[client_id] # Remove from pending after decision

    return jsonify({"status": "success", "action": response_action})

# --- Telegram Bot ---
bot_application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'Привет, {update.effective_user.first_name}! Я готов к работе.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Вот список доступных команд:\n'
        '/start - Начать взаимодействие\n'
        '/help - Показать это сообщение\n'
        '/accept <hwid> - Подтвердить запуск клиента\n'
        '/deny <hwid> - Отклонить запуск клиента\n'
        '/whitelist add <pc_name> - Добавить ПК в вайтлист\n'
        '/whitelist rem <pc_name> - Удалить ПК из вайтлиста\n'
        '/pccrash <pc_name> - Закрыть explorer.exe на ПК\n'
        '/sound pizda <pc_name> - Воспроизвести звук на ПК'
    )

async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID:
        await update.message.reply_text("Вы не авторизованы для использования этой команды.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Неверный формат команды. Используйте: /whitelist add <pc_name> или /whitelist rem <pc_name>")
        return

    action = context.args[0].lower()
    pc_name = " ".join(context.args[1:])

    whitelist = load_whitelist()

    if action == "add":
        # Check if the pc_name is already associated with an HWID in the whitelist
        existing_hwid_for_pc_name = next((hwid for hwid, data in whitelist.items() if data.get('pc_name') == pc_name), None)
        
        if existing_hwid_for_pc_name:
            await update.message.reply_text(f"ПК *{pc_name}* уже в вайтлисте с HWID `{existing_hwid_for_pc_name}`.", parse_mode='Markdown')
        else:
            # Try to find if this PC name is currently in pending clients to get its real HWID
            client_data_from_pending = next((data for data in pending_clients.values() if data.get('pc_name') == pc_name), None)

            if client_data_from_pending:
                hwid_to_add = client_data_from_pending['hwid']
                whitelist[hwid_to_add] = {'pc_name': pc_name, 'hwid': hwid_to_add}
                save_whitelist(whitelist)
                await update.message.reply_text(f"ПК *{pc_name}* (HWID: `{hwid_to_add}`) добавлен в вайтлист.", parse_mode='Markdown')
            else:
                # If not found in pending, add with a placeholder HWID for now.
                # The actual HWID will be updated when the client connects.
                temp_hwid = f"TEMP_HWID_{pc_name.replace(' ', '_')}"
                whitelist[temp_hwid] = {'pc_name': pc_name, 'hwid': temp_hwid} # Placeholder
                save_whitelist(whitelist)
                await update.message.reply_text(f"ПК *{pc_name}* добавлен в вайтлист. HWID будет обновлен при первом подключении.", parse_mode='Markdown')

    elif action == "rem":
        removed = False
        # Search by pc_name and remove the corresponding entry
        hwids_to_remove = [hwid for hwid, data in whitelist.items() if data.get('pc_name') == pc_name]
        for hwid in hwids_to_remove:
            del whitelist[hwid]
            removed = True
        
        if removed:
            save_whitelist(whitelist)
            await update.message.reply_text(f"ПК *{pc_name}* удален из вайтлиста.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ПК *{pc_name}* не найден в вайтлисте.", parse_mode='Markdown')
    else:
        await update.message.reply_text("Неизвестное действие. Используйте 'add' или 'rem'.")

async def pccrash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID:
        await update.message.reply_text("Вы не авторизованы для использования этой команды.")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите имя ПК. Пример: /pccrash MyPC")
        return

    pc_name = " ".join(context.args)
    # TODO: Implement sending a command to the Minecraft client to close explorer.exe
    await update.message.reply_text(f"Команда на закрытие explorer.exe отправлена ПК *{pc_name}* (функционал еще не реализован на стороне клиента).", parse_mode='Markdown')

async def sound_pizda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID:
        await update.message.reply_text("Вы не авторизованы для использования этой команды.")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите имя ПК. Пример: /sound pizda MyPC")
        return

    pc_name = " ".join(context.args)
    # TODO: Implement sending a command to the Minecraft client to play sound and show image
    await update.message.reply_text(f"Команда на воспроизведение звука и показ картинки отправлена ПК *{pc_name}* (функционал еще не реализован на стороне клиента).", parse_mode='Markdown')

bot_application.add_handler(CommandHandler("start", start))
bot_application.add_handler(CommandHandler("help", help_command))
bot_application.add_handler(CommandHandler("accept", accept_command))
bot_application.add_handler(CommandHandler("deny", deny_command))
bot_application.add_handler(CommandHandler("whitelist", whitelist_command))
bot_application.add_handler(CommandHandler("pccrash", pccrash_command))
bot_application.add_handler(CommandHandler("sound", sound_pizda_command))

async def setup_webhook():
    await bot_application.bot.set_webhook(url=WEBHOOK_URL)
    print(f"Telegram webhook set to: {WEBHOOK_URL}")

@app.route(WEBHOOK_PATH, methods=['POST'])
async def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot_application.bot)
    await bot_application.update_queue.put(update)
    return "ok"

# Function to run the bot application in a separate thread/event loop
def run_bot_async():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_application.initialize())
    loop.run_until_complete(setup_webhook())
    loop.run_forever()

if __name__ == '__main__':
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID or "YOUR_RENDER_APP_URL_HERE" in BASE_URL:
        print("Configuration error: TELEGRAM_BOT_TOKEN, CHAT_ID, or BASE_URL is not set properly.")
        print("Please ensure environment variables are set or default values are updated.")
        exit(1)

    # Start the Telegram bot in a separate thread
    bot_thread = Thread(target=run_bot_async)
    bot_thread.start()

    # Run the Flask app
    print("Flask app starting...")
    app.run(host='0.0.0.0', port=os.environ.get("PORT", 5000))
