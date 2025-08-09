import os
import logging
import traceback
import json
import secrets
import string
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

# ========== LOGGING SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "default_password")

# Render settings
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 10000))
WEBHOOK_PATH = "/webhook"
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_URL", ""))

# Validate required parameters
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_TOKEN environment variable is required!")
    exit(1)

# Extract API key from token
API_KEY = TELEGRAM_TOKEN.split(':')[1]
SECRET_TOKEN = API_KEY[:32]  # Use first 32 characters of API key

# Diagnostics
logger.info("===== BOT CONFIGURATION =====")
logger.info(f"TELEGRAM_TOKEN: {'set' if TELEGRAM_TOKEN else 'NOT SET!'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")
logger.info(f"BOT_PASSWORD: {'set' if BOT_PASSWORD else 'NOT SET!'}")
logger.info(f"BASE_WEBHOOK_URL: {BASE_WEBHOOK_URL or 'NOT SET!'}")
logger.info(f"Server will run on: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
logger.info(f"SECRET_TOKEN: {SECRET_TOKEN}")
logger.info("=============================")

# ========== ADMIN STATES ==========
class AdminStates(StatesGroup):
    SELECT_ROLE = State()
    SELECT_CHECKLIST = State()
    EDIT_CHECKLIST = State()
    ADD_TASK = State()
    EDIT_TASK = State()
    DELETE_TASK = State()
    RENAME_CHECKLIST = State()
    NEW_CHECKLIST = State()
    GENERATE_PASSWORD = State()

# ========== CHECKLIST DATA ==========
def load_checklists():
    """Load checklists from file or use default"""
    try:
        with open('checklists.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default checklists if file doesn't exist
        return {
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
            }
        }

def save_checklists():
    """Save checklists to file"""
    with open('checklists.json', 'w') as f:
        json.dump(checklists, f, indent=2)
    logger.info("Checklists saved to file")

# Load initial checklists
checklists = load_checklists()

# ========== BOT STATE ==========
user_sessions = {}

# ========== HELPER FUNCTIONS ==========
def generate_password(length=10):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def is_admin(user_id):
    """Check if user is admin"""
    return user_id == ADMIN_ID

def checklist_keyboard(role):
    """Create checklist selection keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cl_name in checklists[role].keys():
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=cl_name, callback_data=f"cl:{cl_name}")
        ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Add New Checklist", callback_data="add_checklist")
    ])
    return keyboard

def tasks_keyboard(tasks):
    """Create tasks management keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for i, task in enumerate(tasks):
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"✏️ {i+1}. {task[:20]}...", callback_data=f"edit_task:{i}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="✅ Add New Task", callback_data="add_task")
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="📝 Rename Checklist", callback_data="rename_checklist")
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Back to Checklists", callback_data="back_to_checklists")
    ])
    return keyboard

# ========== COMMAND HANDLERS ==========
async def start_handler(message: types.Message):
    """Handler for /start command"""
    try:
        logger.info(f"Received /start from {message.from_user.id}")
        
        # Reset session on each /start
        user_id = message.from_user.id
        if user_id in user_sessions:
            del user_sessions[user_id]
            
        # Admin specific commands
        if is_admin(user_id):
            await message.answer(
                "🚀 Welcome Admin!\n"
                "You can use the following commands:\n"
                "/start - Show this message\n"
                "/edit_checklists - Edit checklists\n"
                "/generate_password - Generate new password\n"
                "\nPlease enter the password to use the bot:"
            )
        else:
            await message.answer("🚀 Welcome to La Croisette Checklist Bot!\nPlease enter the password:")
    except Exception as e:
        logger.error(f"Error in start_handler: {e}\n{traceback.format_exc()}")
        await message.answer("❌ Bot error. Please try again later.")

async def message_handler(message: types.Message, state: FSMContext):
    """Handler for text messages"""
    try:
        logger.info(f"Message from {message.from_user.id}: {message.text[:50]}")
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Check if we're in an admin state
        current_state = await state.get_state()
        if current_state:
            if current_state == AdminStates.ADD_TASK.state:
                role = (await state.get_data())['role']
                cl_name = (await state.get_data())['checklist']
                checklists[role][cl_name].append(text)
                save_checklists()
                await message.answer(f"✅ Task added to {cl_name}!")
                await show_checklist_editor(message, state, role, cl_name)
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.EDIT_TASK.state:
                data = await state.get_data()
                role = data['role']
                cl_name = data['checklist']
                task_index = data['task_index']
                checklists[role][cl_name][task_index] = text
                save_checklists()
                await message.answer(f"✅ Task updated!")
                await show_checklist_editor(message, state, role, cl_name)
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.RENAME_CHECKLIST.state:
                data = await state.get_data()
                role = data['role']
                old_name = data['checklist']
                new_name = text
                
                # Rename checklist
                if old_name in checklists[role]:
                    checklists[role][new_name] = checklists[role].pop(old_name)
                    save_checklists()
                    await message.answer(f"✅ Checklist renamed to {new_name}!")
                    await show_checklist_editor(message, state, role, new_name)
                else:
                    await message.answer("❌ Checklist not found!")
                
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.NEW_CHECKLIST.state:
                data = await state.get_data()
                role = data['role']
                cl_name = text
                
                # Create new checklist
                if cl_name not in checklists[role]:
                    checklists[role][cl_name] = []
                    save_checklists()
                    await message.answer(f"✅ Checklist {cl_name} created!")
                    await show_checklist_editor(message, state, role, cl_name)
                else:
                    await message.answer("❌ Checklist with this name already exists!")
                
                await state.set_state(None)
                return

        # Normal user flow
        if user_id not in user_sessions:
            if text == BOT_PASSWORD:
                user_sessions[user_id] = {"step": "name"}
                await message.answer("✅ Password accepted! Please enter your name:")
            else:
                await message.answer("❌ Incorrect password. Please try again.")
            return

        if user_sessions[user_id]["step"] == "name":
            user_sessions[user_id]["name"] = text
            user_sessions[user_id]["step"] = "role"
            
            # Create role selection buttons
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for role in checklists.keys():
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=role, callback_data=f"role:{role}")
                ])
                
            await message.answer("Select your role:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error in message_handler: {e}\n{traceback.format_exc()}")
        await message.answer("❌ Error processing your message. Please try /start again.")

# ========== ADMIN COMMANDS ==========
async def edit_checklists_handler(message: types.Message, state: FSMContext):
    """Handler for /edit_checklists command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have permission to use this command.")
        return
        
    await state.set_state(AdminStates.SELECT_ROLE)
    
    # Create role selection buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for role in checklists.keys():
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=role, callback_data=f"admin_role:{role}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Cancel", callback_data="admin_cancel")
    ])
        
    await message.answer("Select a role to edit checklists:", reply_markup=keyboard)

async def generate_password_handler(message: types.Message, state: FSMContext):
    """Handler for /generate_password command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have permission to use this command.")
        return
        
    await state.set_state(AdminStates.GENERATE_PASSWORD)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔒 Generate New Password", callback_data="gen_pass_confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")
    ]])
    
    await message.answer(
        "⚠️ This will generate a new password for all users.\n"
        "Current users will need to re-authenticate.\n\n"
        "Are you sure you want to generate a new password?",
        reply_markup=keyboard
    )

# ========== ADMIN EDITING FLOW ==========
async def show_checklist_editor(message, state, role, cl_name):
    """Show checklist editor interface"""
    tasks = checklists[role][cl_name]
    keyboard = tasks_keyboard(tasks)
    
    await message.answer(
        f"📝 Editing: {role} - {cl_name}\n\n"
        f"Tasks ({len(tasks)}):",
        reply_markup=keyboard
    )
    
    # Store current context
    await state.update_data(role=role, checklist=cl_name)

async def admin_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handler for admin callback queries"""
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Access denied")
            return
            
        await callback.answer()
        data = callback.data
        
        # Admin role selection
        if data.startswith("admin_role:"):
            role = data.split(":")[1]
            await state.set_state(AdminStates.SELECT_CHECKLIST)
            await state.update_data(role=role)
            
            keyboard = checklist_keyboard(role)
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back to Roles", callback_data="back_to_roles")
            ])
            
            await callback.message.edit_text(
                f"Select a checklist for {role}:",
                reply_markup=keyboard
            )
        
        # Checklist selection
        elif data.startswith("cl:"):
            cl_name = data.split(":")[1]
            role = (await state.get_data())['role']
            await show_checklist_editor(callback.message, state, role, cl_name)
        
        # Add new checklist
        elif data == "add_checklist":
            await state.set_state(AdminStates.NEW_CHECKLIST)
            await callback.message.answer("Please enter the name for the new checklist:")
        
        # Add new task
        elif data == "add_task":
            await state.set_state(AdminStates.ADD_TASK)
            await callback.message.answer("Please enter the new task text:")
        
        # Rename checklist
        elif data == "rename_checklist":
            await state.set_state(AdminStates.RENAME_CHECKLIST)
            await callback.message.answer("Please enter the new name for this checklist:")
        
        # Edit task
        elif data.startswith("edit_task:"):
            task_index = int(data.split(":")[1])
            await state.set_state(AdminStates.EDIT_TASK)
            await state.update_data(task_index=task_index)
            
            role = (await state.get_data())['role']
            cl_name = (await state.get_data())['checklist']
            task_text = checklists[role][cl_name][task_index]
            
            await callback.message.answer(
                f"Current task text:\n{task_text}\n\n"
                "Please enter the new text for this task:"
            )
        
        # Back to checklists
        elif data == "back_to_checklists":
            role = (await state.get_data())['role']
            await state.set_state(AdminStates.SELECT_CHECKLIST)
            
            keyboard = checklist_keyboard(role)
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back to Roles", callback_data="back_to_roles")
            ])
            
            await callback.message.edit_text(
                f"Select a checklist for {role}:",
                reply_markup=keyboard
            )
        
        # Back to roles
        elif data == "back_to_roles":
            await state.set_state(AdminStates.SELECT_ROLE)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for role in checklists.keys():
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=role, callback_data=f"admin_role:{role}")
                ])
            
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Cancel", callback_data="admin_cancel")
            ])
                
            await callback.message.edit_text(
                "Select a role to edit checklists:",
                reply_markup=keyboard
            )
        
        # Generate password confirmation
        elif data == "gen_pass_confirm":
            global BOT_PASSWORD
            new_password = generate_password()
            BOT_PASSWORD = new_password
            
            # In a real app, you would save this to a persistent storage
            await callback.message.answer(
                f"✅ New password generated:\n<code>{new_password}</code>\n\n"
                "Please save this password. Users will need it to authenticate.",
                parse_mode="HTML"
            )
            await state.set_state(None)
        
        # Cancel admin operation
        elif data == "admin_cancel":
            await state.set_state(None)
            await callback.message.answer("Admin operation cancelled.")
            
    except Exception as e:
        logger.error(f"Error in admin_callback_handler: {e}\n{traceback.format_exc()}")
        await callback.message.answer("❌ Admin operation error. Please try again.")

# ========== USER FLOW HANDLERS ==========
async def callback_handler(callback: types.CallbackQuery):
    """Handler for user callback queries"""
    try:
        await callback.answer()
        user_id = callback.from_user.id
        data = callback.data

        if data.startswith("role:"):
            role = data.split(":")[1]
            user_sessions[user_id]["role"] = role
            user_sessions[user_id]["step"] = "checklist"
            
            # Create checklist selection buttons
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for cl_name in checklists[role].keys():
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=cl_name, callback_data=f"checklist:{cl_name}")
                ])
                
            await callback.message.answer(f"Select checklist for {role}:", reply_markup=keyboard)

        elif data.startswith("checklist:"):
            cl_name = data.split(":")[1]
            role = user_sessions[user_id]["role"]
            tasks = checklists[role][cl_name]
            user_sessions[user_id]["tasks"] = tasks
            user_sessions[user_id]["current_task"] = 0
            user_sessions[user_id]["results"] = []
            await send_task(
                bot=callback.bot, 
                chat_id=callback.message.chat.id, 
                user_id=user_id
            )

        elif data.startswith("task:"):
            result = data.split(":")[1]
            session = user_sessions[user_id]
            session["results"].append((session["tasks"][session["current_task"]], result))
            session["current_task"] += 1
            
            if session["current_task"] < len(session["tasks"]):
                await send_task(
                    bot=callback.bot, 
                    chat_id=callback.message.chat.id, 
                    user_id=user_id
                )
            else:
                await finish_checklist(callback.message, user_id)
    except Exception as e:
        logger.error(f"Error in callback_handler: {e}\n{traceback.format_exc()}")
        await callback.message.answer("❌ Processing error. Please restart with /start command.")

async def send_task(bot: Bot, chat_id: int, user_id: int):
    """Send task to user using bot instance"""
    try:
        if user_id not in user_sessions:
            await bot.send_message(chat_id, "❌ Session expired. Please restart with /start")
            return
            
        session = user_sessions[user_id]
        task_text = session["tasks"][session["current_task"]]
        
        # Create response buttons with NAMED arguments (FIXED)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Done", callback_data="task:Done"),
            InlineKeyboardButton(text="❌ Not Done", callback_data="task:Not Done")
        ]])
        
        await bot.send_message(
            chat_id=chat_id,
            text=f"Task {session['current_task']+1}/{len(session['tasks'])}:\n{task_text}", 
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in send_task: {e}\n{traceback.format_exc()}")
        await bot.send_message(chat_id, "❌ Error loading tasks. Please try again later.")

async def finish_checklist(message, user_id):
    """Complete checklist and send report"""
    try:
        session = user_sessions[user_id]
        report = f"📋 Checklist Report\n👤 Name: {session['name']}\nRole: {session['role']}\n\n"
        
        for task, result in session["results"]:
            status = "✅ Done" if result == "Done" else "❌ Not Done"
            report += f"- {task} → {status}\n"
        
        await message.answer("✅ Checklist completed! Report sent to manager.")
        
        try:
            # Send report to admin
            await message.bot.send_message(
                ADMIN_ID, 
                report
            )
            logger.info(f"Report sent to admin {ADMIN_ID}")
        except Exception as e:
            logger.error(f"Error sending report: {e}\n{traceback.format_exc()}")
            await message.answer("⚠️ Failed to send report to manager. Please notify admin directly.")
        
        # Cleanup session
        if user_id in user_sessions:
            del user_sessions[user_id]
    except Exception as e:
        logger.error(f"Error in finish_checklist: {e}\n{traceback.format_exc()}")
        await message.answer("❌ Error completing checklist. Please contact support.")

# ========== WEBHOOK SETUP ==========
async def on_startup(bot: Bot):
    """Actions on bot startup"""
    try:
        logger.info("Running startup actions...")
        
        # Remove old webhook
        await bot.delete_webhook()
        logger.info("Old webhook removed")
        
        if BASE_WEBHOOK_URL:
            webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
            
            # Use globally defined SECRET_TOKEN
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                secret_token=SECRET_TOKEN
            )
            logger.info(f"Webhook set to: {webhook_url}")
            logger.info(f"Secret token: {SECRET_TOKEN}")
            
            # Verify webhook setup
            webhook_info = await bot.get_webhook_info()
            logger.info(f"Webhook info: {webhook_info.url}, pending updates: {webhook_info.pending_update_count}")
            
            # Additional diagnostics
            if webhook_info.url != webhook_url:
                logger.error(f"Webhook mismatch! Expected: {webhook_url}, Actual: {webhook_info.url}")
            else:
                logger.info("Webhook verified ✅")
        else:
            logger.warning("Skipping webhook setup: BASE_WEBHOOK_URL not set")
    except Exception as e:
        logger.error(f"Error in on_startup: {e}\n{traceback.format_exc()}")

async def health_check(request: web.Request) -> web.Response:
    """Server health check"""
    return web.Response(text="✅ Bot is running")

# ========== SERVER STARTUP ==========
def main():
    try:
        logger.info(f"Environment: PORT={os.getenv('PORT')}, RENDER_EXTERNAL_URL={os.getenv('RENDER_EXTERNAL_URL')}")
        
        # Create bot with HTML parsing by default
        bot = Bot(
            TELEGRAM_TOKEN, 
            default=DefaultBotProperties(parse_mode="HTML")
        )
        
        dp = Dispatcher()
        
        # Register handlers
        dp.message.register(start_handler, Command("start"))
        dp.message.register(edit_checklists_handler, Command("edit_checklists"))
        dp.message.register(generate_password_handler, Command("generate_password"))
        dp.message.register(message_handler)
        
        # Callback handlers
        dp.callback_query.register(callback_handler)
        dp.callback_query.register(admin_callback_handler, F.data.startswith("admin_") | F.data.startswith("cl:") | 
                                 F.data.startswith("edit_task:") | F.data.startswith("gen_pass_") | 
                                 F.data == "add_task" | F.data == "add_checklist" | 
                                 F.data == "rename_checklist" | F.data == "back_to_checklists" |
                                 F.data == "back_to_roles" | F.data == "admin_cancel")
        
        # Startup actions
        dp.startup.register(on_startup)
        
        # Create aiohttp application
        app = web.Application()
        app["bot"] = bot
        
        # Register endpoints
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        
        # Webhook handler
        async def webhook_handler(request: web.Request) -> web.Response:
            try:
                logger.info(f"Incoming webhook request to: {request.path}")
                
                # Secret token verification
                secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                
                # Use globally defined SECRET_TOKEN
                if secret_token != SECRET_TOKEN:
                    logger.warning(f"Invalid secret token! Expected: {SECRET_TOKEN}, Got: {secret_token}")
                    return web.Response(status=403, text="Forbidden")
                
                # Process update
                return await SimpleRequestHandler(
                    dispatcher=dp,
                    bot=bot,
                ).handle(request)
            except Exception as e:
                logger.error(f"Critical error in webhook handler: {e}\n{traceback.format_exc()}")
                return web.Response(status=500, text="Internal Server Error")
        
        app.router.add_post(WEBHOOK_PATH, webhook_handler)
        
        # Logging middleware
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
        
        # Start server
        logger.info(f"🚀 Starting server on {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        web.run_app(
            app,
            host=WEB_SERVER_HOST,
            port=WEB_SERVER_PORT,
            access_log=None
        )
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    logger.info("===== STARTING BOT APPLICATION =====")
    main()