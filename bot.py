import os
import logging
import traceback
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

# ========== КОНФИГУРАЦИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "default_password")

# Настройки для Render
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = "/webhook"
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_URL", ""))

# Диагностика
logger.info("===== CONFIGURATION =====")
logger.info(f"TELEGRAM_TOKEN: {'set' if TELEGRAM_TOKEN else 'NOT SET!'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")
logger.info(f"BOT_PASSWORD: {'set' if BOT_PASSWORD else 'NOT SET!'}")
logger.info(f"BASE_WEBHOOK_URL: {BASE_WEBHOOK_URL or 'NOT SET!'}")
logger.info(f"Server will run on: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
logger.info("=========================")

# ========== ДАННЫЕ ЧЕК-ЛИСТОВ ==========
checklists = {
    "Bartender": {
        "Opening Shift": [
            "Get the keys and open the bar shutters. Clean shutters and locks.",
            "Turn on the lights in the bar area.",
            "Check that all bar equipment is working.",
            "Turn on background music.",
            "Fill ice bins with fresh ice.",
            "Prepare all bar tools (shakers, strainers, spoons, etc.).",
            "Restock bottles and ingredients.",
            "Check beer kegs and replace if needed.",
            "Wipe the bar counter and shelves.",
            "Prepare garnish trays (lemons, limes, herbs, etc.).",
            "Check and clean glasses.",
            "Ensure the cash register is ready and has enough change.",
            "Test the card payment terminal.",
            "Refill napkins, straws, and stirrers.",
            "Check fridges for drinks and refill if necessary.",
            "Make sure the menu is clean and complete."
        ],
        "Closing Shift": [
            "Remove and discard all leftover garnish.",
            "Wash and store all bar tools (shakers, spoons, strainers, etc.).",
            "Empty and clean ice bins.",
            "Wipe the bar counter and shelves.",
            "Check and note stock levels for the next day.",
            "Close beer taps and turn off the gas supply.",
            "Switch off all bar equipment.",
            "Clean fridges inside and outside.",
            "Lock alcohol storage.",
            "Turn off lights and music.",
            "Close and lock the bar shutters.",
            "Return keys to the manager."
        ]
    },
    "Cashier": {
        "Opening Shift": [
            "Get the keys and open the cashier station.",
            "Turn on the cashier lights.",
            "Switch on the cash register.",
            "Count the starting cash balance and record it.",
            "Check the payment terminal (card machine) is working.",
            "Make sure receipt paper is loaded.",
            "Prepare coins and small bills for change.",
            "Ensure the working area is clean and organized.",
            "Check the menu display and update if needed.",
            "Prepare order slips and pens."
        ],
        "Closing Shift": [
            "Count the final cash balance and record it.",
            "Compare with the starting balance and sales report.",
            "Close and log out from the cash register.",
            "Turn off the payment terminal (card machine).",
            "Remove and store receipt paper if needed.",
            "Clean and organize the cashier station.",
            "Lock the cash drawer.",
            "Turn off cashier lights.",
            "Close and lock the cashier station.",
            "Return keys to the manager."
        ]
    },
    "Manager": {
        "Opening Shift": [
            "Open the main entrance and turn off the alarm (if applicable).",
            "Turn on all restaurant lights.",
            "Check that all areas are clean and tidy (dining room, bar, kitchen, toilets).",
            "Make sure all equipment is working (coffee machine, fridges, POS, etc.).",
            "Confirm staff attendance and assign tasks for the shift.",
            "Review reservations for the day.",
            "Ensure menus are clean and complete.",
            "Check stock of key items (coffee, drinks, napkins, etc.).",
            "Coordinate with kitchen on specials and menu availability.",
            "Open doors for service and greet first guests if necessary."
        ],
        "Closing Shift": [
            "Check that all guests have left the premises.",
            "Ensure all cash from the cashier is counted and recorded.",
            "Verify sales reports from POS.",
            "Lock the cash in the safe.",
            "Confirm all areas are clean (dining room, bar, kitchen, toilets).",
            "Turn off all lights and equipment.",
            "Check that doors and windows are closed and locked.",
            "Activate the alarm (if applicable).",
            "Collect keys and store them securely.",
            "Complete the end-of-day report."
        ]
    },
    "Leader": {
        "Opening Shift": [
            "Arrive 15 minutes before shift start.",
            "Check staff attendance and appearance.",
            "Ensure all stations are ready for service.",
            "Review special offers and daily menu with staff.",
            "Distribute tasks between team members.",
            "Check that stock levels are adequate.",
            "Test POS terminals at all stations.",
            "Make sure uniforms are clean and neat.",
            "Walk through the restaurant to check readiness.",
            "Report any issues to the manager."
        ],
        "Closing Shift": [
            "Make sure all tables are cleared and cleaned.",
            "Check bar and kitchen are cleaned and equipment is off.",
            "Verify all doors and windows are closed.",
            "Ensure rubbish is taken out.",
            "Confirm final stock count for the day.",
            "Collect any lost and found items.",
            "Hand over keys to the manager.",
            "Write a short report about the shift."
        ]
    },
    "Waiter": {
        "Opening Shift": [
            "Set tables with cutlery, glasses, and napkins.",
            "Refill water bottles for service.",
            "Check menu condition and replace if damaged.",
            "Make sure the serving station is stocked.",
            "Wipe tables and chairs.",
            "Prepare condiment trays (salt, pepper, sauces).",
            "Test POS terminal.",
            "Make sure trays and service tools are clean.",
            "Check that the dining area is tidy."
        ],
        "Closing Shift": [
            "Clear and wipe all tables.",
            "Return cutlery, glasses, and plates to the kitchen.",
            "Clean condiment trays and store them.",
            "Wipe chairs and tables.",
            "Organize serving station for the next day.",
            "Empty rubbish bins.",
            "Turn off lights in the dining area.",
            "Store menus."
        ]
    },
    "Kitchen": {
        "Opening Shift": [
            "Turn on kitchen lights and equipment.",
            "Check fridges and freezers.",
            "Prepare ingredients for the day.",
            "Set up cooking stations.",
            "Ensure knives and tools are clean and sharp.",
            "Wash hands and wear gloves/apron.",
            "Check gas supply.",
            "Verify kitchen cleanliness."
        ],
        "Closing Shift": [
            "Turn off all kitchen equipment.",
            "Clean and sanitize all surfaces.",
            "Store leftover food properly.",
            "Empty rubbish bins.",
            "Wash and store all kitchen tools.",
            "Check fridge and freezer doors are closed.",
            "Turn off lights."
        ]
    },
    "Hostess": {
        "Opening Shift": [
            "Check the reservation list and table plan.",
            "Prepare the host stand (menus, reservation book, pens).",
            "Make sure entrance area is clean and tidy.",
            "Turn on entrance lights.",
            "Check uniform and appearance.",
            "Test the phone line.",
            "Prepare guest waiting area.",
            "Confirm special events or promotions with manager."
        ],
        "Closing Shift": [
            "Store menus and reservation book.",
            "Clean host stand.",
            "Turn off entrance lights.",
            "Ensure entrance doors are locked.",
            "Store lost and found items.",
            "Report to manager before leaving."
        ]
    },
    "Cleaner": {
        "Opening Shift": [
            "Sweep and mop floors in all areas.",
            "Clean toilets and restock supplies.",
            "Wipe tables, chairs, and counters.",
            "Empty rubbish bins.",
            "Check mirrors and glass doors for smudges.",
            "Refill soap and paper towels."
        ],
        "Closing Shift": [
            "Sweep and mop floors.",
            "Clean and disinfect toilets.",
            "Empty all rubbish bins and take trash out.",
            "Wipe tables and chairs.",
            "Check that cleaning tools are stored properly."
        ]
    },
    "Security": {
        "Opening Shift": [
            "Check CCTV system.",
            "Patrol the premises before opening.",
            "Ensure all emergency exits are clear.",
            "Test radios or communication devices.",
            "Confirm shift schedule with manager."
        ],
        "Closing Shift": [
            "Patrol the premises before locking.",
            "Check all doors and windows.",
            "Turn on alarm system.",
            "Lock main entrance.",
            "Record shift notes in logbook."
        ]
    },
    "Dishwasher": {
        "Opening Shift": [
            "Turn on dishwasher.",
            "Check detergents and refill if needed.",
            "Prepare drying racks.",
            "Ensure sinks are clean and ready."
        ],
        "Closing Shift": [
            "Turn off dishwasher and clean filters.",
            "Empty and clean sinks.",
            "Store all cleaned dishes.",
            "Mop dishwashing area."
        ]
    },
    "Maintenance": {
        "Opening Shift": [
            "Check all lights and replace bulbs if needed.",
            "Inspect toilets for plumbing issues.",
            "Ensure air conditioning works.",
            "Test all electrical outlets."
        ],
        "Closing Shift": [
            "Turn off non-essential equipment.",
            "Lock maintenance room.",
            "Note any issues for repair.",
            "Secure tools and supplies."
        ]
    }
}

# ========== СОСТОЯНИЕ БОТА ==========
user_sessions = {}

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_handler(message: types.Message):
    """Обработчик команды /start"""
    try:
        logger.info(f"Received /start from {message.from_user.id}")
        await message.answer("Welcome to La Croisette Checklist Bot.\nPlease enter the password:")
    except Exception as e:
        logger.error(f"Error in start_handler: {e}\n{traceback.format_exc()}")

async def message_handler(message: types.Message):
    """Обработчик текстовых сообщений"""
    try:
        logger.info(f"Message from {message.from_user.id}: {message.text[:50]}")
        user_id = message.from_user.id
        text = message.text.strip()

        if user_id not in user_sessions:
            if text == BOT_PASSWORD:
                user_sessions[user_id] = {"step": "name"}
                await message.answer("Password correct ✅\nPlease enter your name:")
            else:
                await message.answer("Incorrect password. Try again.")
            return

        if user_sessions[user_id]["step"] == "name":
            user_sessions[user_id]["name"] = text
            user_sessions[user_id]["step"] = "role"
            keyboard = InlineKeyboardMarkup()
            for role in checklists.keys():
                keyboard.add(InlineKeyboardButton(text=role, callback_data=f"role:{role}"))
            await message.answer("Select your role:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error in message_handler: {e}\n{traceback.format_exc()}")

async def callback_handler(callback: types.CallbackQuery):
    """Обработчик callback-запросов"""
    try:
        logger.info(f"Callback from {callback.from_user.id}: {callback.data}")
        user_id = callback.from_user.id
        data = callback.data

        if data.startswith("role:"):
            role = data.split(":")[1]
            user_sessions[user_id]["role"] = role
            user_sessions[user_id]["step"] = "checklist"
            keyboard = InlineKeyboardMarkup()
            for cl_name in checklists[role].keys():
                keyboard.add(InlineKeyboardButton(text=cl_name, callback_data=f"checklist:{cl_name}"))
            await callback.message.answer(f"Select checklist for {role}:", reply_markup=keyboard)

        elif data.startswith("checklist:"):
            cl_name = data.split(":")[1]
            role = user_sessions[user_id]["role"]
            tasks = checklists[role][cl_name]
            user_sessions[user_id]["tasks"] = tasks
            user_sessions[user_id]["current_task"] = 0
            user_sessions[user_id]["results"] = []
            await send_task(callback.message, user_id)

        elif data.startswith("task:"):
            result = data.split(":")[1]
            session = user_sessions[user_id]
            session["results"].append((session["tasks"][session["current_task"]], result))
            session["current_task"] += 1
            if session["current_task"] < len(session["tasks"]):
                await send_task(callback.message, user_id)
            else:
                await finish_checklist(callback.message, user_id)
    except Exception as e:
        logger.error(f"Error in callback_handler: {e}\n{traceback.format_exc()}")
        await callback.message.answer("❌ An error occurred. Please restart the bot with /start")

async def send_task(message, user_id):
    """Отправка задачи пользователю"""
    try:
        session = user_sessions[user_id]
        task_text = session["tasks"][session["current_task"]]
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✅ Done", callback_data="task:Done"),
            InlineKeyboardButton("❌ Not Done", callback_data="task:Not Done")
        )
        await message.answer(f"Task {session['current_task']+1}/{len(session['tasks'])}:\n{task_text}", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error in send_task: {e}\n{traceback.format_exc()}")

async def finish_checklist(message, user_id):
    """Завершение чек-листа и отправка отчета"""
    try:
        session = user_sessions[user_id]
        report = f"📋 Checklist Report\n👤 Name: {session['name']}\nRole: {session['role']}\n\n"
        for task, result in session["results"]:
            report += f"- {task} → {result}\n"
        await message.answer("Checklist completed ✅ Report sent to manager.")
        try:
            await message.bot.send_message(ADMIN_ID, report)
            logger.info(f"Report sent to admin {ADMIN_ID}")
        except Exception as e:
            logger.error(f"Error sending report: {e}\n{traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Error in finish_checklist: {e}\n{traceback.format_exc()}")

# ========== WEBHOOK НАСТРОЙКИ ==========
async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    try:
        logger.info("Running startup actions...")
        
        if BASE_WEBHOOK_URL:
            webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
            await bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            
            # Проверка установки вебхука
            webhook_info = await bot.get_webhook_info()
            logger.info(f"Webhook info: {webhook_info.url}, pending updates: {webhook_info.pending_update_count}")
        else:
            logger.warning("Skipping webhook setup: BASE_WEBHOOK_URL not set")
    except Exception as e:
        logger.error(f"Error in on_startup: {e}\n{traceback.format_exc()}")

async def health_check(request: web.Request) -> web.Response:
    """Проверка работоспособности сервера"""
    return web.Response(text="✅ Bot is running")

# ========== ЗАПУСК СЕРВЕРА ==========
def main():
    try:
        if not TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_TOKEN environment variable is required!")
            return
        
        bot = Bot(TELEGRAM_TOKEN)
        dp = Dispatcher()
        
        # Регистрация обработчиков
        dp.message.register(start_handler, Command("start"))
        dp.message.register(message_handler)
        dp.callback_query.register(callback_handler)
        
        # Действия при запуске
        dp.startup.register(on_startup)
        
        # Создаем aiohttp приложение
        app = web.Application()
        app["bot"] = bot
        
        # Регистрация эндпоинтов
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        
        # Регистрация обработчика вебхука с обработкой ошибок
        async def webhook_handler(request: web.Request) -> web.Response:
            try:
                # Логирование тела запроса для отладки
                body = await request.text()
                logger.debug(f"Incoming update: {body}")
                
                handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
                response = await handler.handle(request)
                return response
            except Exception as e:
                logger.error(f"Error in webhook handler: {e}\n{traceback.format_exc()}")
                return web.Response(status=500, text="Internal Server Error")
        
        app.router.add_post(WEBHOOK_PATH, webhook_handler)
        
        # Middleware для логирования запросов
        @web.middleware
        async def log_middleware(request: web.Request, handler):
            logger.info(f"Request: {request.method} {request.path}")
            try:
                response = await handler(request)
                logger.info(f"Response status: {response.status}")
                return response
            except Exception as e:
                logger.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
                return web.Response(text="Internal Server Error", status=500)
        
        app.middlewares.append(log_middleware)
        
        # Запуск сервера
        logger.info(f"Starting server on port {WEB_SERVER_PORT}")
        web.run_app(
            app,
            host=WEB_SERVER_HOST,
            port=WEB_SERVER_PORT,
            access_log=None  # Отключаем стандартное логирование aiohttp
        )
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    logger.info("===== STARTING BOT =====")
    main()