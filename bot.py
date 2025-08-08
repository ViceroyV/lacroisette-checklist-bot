import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# Получаем данные из переменных окружения
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PASSWORD = os.getenv("BOT_PASSWORD")

# Проверка наличия обязательных переменных
if not all([API_TOKEN, ADMIN_ID, PASSWORD]):
    missing = [var for var in ["TELEGRAM_TOKEN", "ADMIN_ID", "BOT_PASSWORD"] if not os.getenv(var)]
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

logging.basicConfig(level=logging.INFO)

# === Все чек-листы ===
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
# === Логика бота ===
user_sessions = {}

async def start_handler(message: types.Message):
    await message.answer("Welcome to La Croisette Checklist Bot.\nPlease enter the password:")

async def message_handler(message: types.Message):
    # ... [весь ваш обработчик сообщений] ...

async def callback_handler(callback: types.CallbackQuery):
    # ... [весь ваш обработчик колбэков] ...

async def send_task(message, user_id):
    # ... [ваш код отправки задачи] ...

async def finish_checklist(message, user_id):
    # ... [ваш код завершения чек-листа] ...

async def main():
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()
    
    dp.message.register(start_handler, Command("start"))
    dp.message.register(message_handler)
    dp.callback_query.register(callback_handler)

    logging.info("✅ Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())