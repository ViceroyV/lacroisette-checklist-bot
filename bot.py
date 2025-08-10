import os
import logging
import traceback
import json
import secrets
import string
import time
import glob
import csv
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import asyncio

# ========== LOGGING SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "default_password")

# Render settings
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 10000))
WEBHOOK_PATH = "/webhook"
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_URL", ""))
REPORTS_DIR = "reports"
USER_ASSIGNMENTS_FILE = "user_assignments.json"

# Validate required parameters
if not TELEGRAM_TOKEN:
    logger.critical("❌ TELEGRAM_TOKEN environment variable is required!")
    exit(1)

# Extract API key from token
API_KEY = TELEGRAM_TOKEN.split(':')[1]
SECRET_TOKEN = API_KEY[:32]  # Use first 32 characters of API key

# Create reports directory if not exists
os.makedirs(REPORTS_DIR, exist_ok=True)

# Diagnostics
logger.info("===== BOT CONFIGURATION =====")
logger.info(f"TELEGRAM_TOKEN: {'set' if TELEGRAM_TOKEN else 'NOT SET!'}")
logger.info(f"ADMIN_IDS: {ADMIN_IDS}")
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
    CONFIRM_DELETE_TASK = State()
    CONFIRM_DELETE_CHECKLIST = State()
    VIEW_REPORTS = State()
    MANAGE_ASSIGNMENTS = State()
    SELECT_USER_TO_ASSIGN = State()
    SELECT_CHECKLIST_TO_ASSIGN = State()

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

# ========== USER ASSIGNMENTS ==========
def load_user_assignments():
    """Load user assignments from file"""
    try:
        with open(USER_ASSIGNMENTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_assignments():
    """Save user assignments to file"""
    with open(USER_ASSIGNMENTS_FILE, 'w') as f:
        json.dump(user_assignments, f, indent=2)
    logger.info("User assignments saved to file")

# Load user assignments
user_assignments = load_user_assignments()

# ========== BOT STATE ==========
user_sessions = {}
storage = MemoryStorage()

# ========== HELPER FUNCTIONS ==========
def generate_password(length=10):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def get_user_name(user_id):
    """Get user name from sessions or assignments"""
    if user_id in user_sessions:
        return user_sessions[user_id].get("name", f"User {user_id}")
    return f"User {user_id}"

def checklist_keyboard(role):
    """Create checklist selection keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cl_name in checklists[role].keys():
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=cl_name, callback_data=f"cl:{cl_name}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"delete_cl:{cl_name}")
        ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Add New Checklist", callback_data="add_checklist")
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Back to Roles", callback_data="back_to_roles")
    ])
    return keyboard

def tasks_keyboard(tasks):
    """Create tasks management keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for i, task in enumerate(tasks):
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"✏️ {i+1}. {task[:20]}...", callback_data=f"edit_task:{i}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"delete_task:{i}")
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

def reports_keyboard():
    """Create reports management keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 View Last 10 Reports", callback_data="view_reports")],
        [InlineKeyboardButton(text="📥 Download All Reports (CSV)", callback_data="download_reports")],
        [InlineKeyboardButton(text="🧹 Clear Reports", callback_data="clear_reports")],
        [InlineKeyboardButton(text="⬅️ Back to Admin Menu", callback_data="back_to_admin")]
    ])
    return keyboard

def assignments_keyboard():
    """Create assignments management keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Assign Checklist to User", callback_data="assign_user")],
        [InlineKeyboardButton(text="👥 View All Assignments", callback_data="view_assignments")],
        [InlineKeyboardButton(text="❌ Remove Assignment", callback_data="remove_assignment")],
        [InlineKeyboardButton(text="⬅️ Back to Admin Menu", callback_data="back_to_admin")]
    ])
    return keyboard

def save_report(user_id, user_name, role, cl_name, results):
    """Save report to file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{REPORTS_DIR}/report_{timestamp}_{user_id}.json"
    
    report_data = {
        "timestamp": time.time(),
        "date": datetime.now().isoformat(),
        "user_id": user_id,
        "user_name": user_name,
        "role": role,
        "checklist": cl_name,
        "results": results
    }
    
    with open(filename, 'w') as f:
        json.dump(report_data, f, indent=2)
    
    logger.info(f"Report saved: {filename}")
    return filename

def get_reports(limit=10):
    """Get list of reports sorted by date"""
    report_files = glob.glob(f"{REPORTS_DIR}/report_*.json")
    report_files.sort(key=os.path.getmtime, reverse=True)
    return report_files[:limit]

def generate_csv_report():
    """Generate CSV file with all reports"""
    csv_filename = f"{REPORTS_DIR}/all_reports_{int(time.time())}.csv"
    report_files = glob.glob(f"{REPORTS_DIR}/report_*.json")
    
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['date', 'user_id', 'user_name', 'role', 'checklist', 'task', 'status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for report_file in report_files:
            try:
                with open(report_file, 'r') as f:
                    report = json.load(f)
                    for task, status in report['results']:
                        writer.writerow({
                            'date': report['date'],
                            'user_id': report['user_id'],
                            'user_name': report['user_name'],
                            'role': report['role'],
                            'checklist': report['checklist'],
                            'task': task,
                            'status': status
                        })
            except Exception as e:
                logger.error(f"Error processing report {report_file}: {e}")
    
    return csv_filename

def clear_reports():
    """Clear all reports"""
    report_files = glob.glob(f"{REPORTS_DIR}/report_*.json")
    for file in report_files:
        try:
            os.remove(file)
        except Exception as e:
            logger.error(f"Error deleting report {file}: {e}")
    return len(report_files)

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
                "/manage_assignments - Manage user assignments\n"
                "/reports - Manage reports\n"
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
                data = await state.get_data()
                role = data.get('role')
                cl_name = data.get('checklist')
                
                if role and cl_name:
                    checklists[role][cl_name].append(text)
                    save_checklists()
                    await message.answer(f"✅ Task added to {cl_name}!")
                    await show_checklist_editor(message, state, role, cl_name)
                else:
                    await message.answer("❌ Error: Role or checklist not found!")
                
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.EDIT_TASK.state:
                data = await state.get_data()
                role = data.get('role')
                cl_name = data.get('checklist')
                task_index = data.get('task_index')
                
                if role and cl_name and task_index is not None:
                    if 0 <= task_index < len(checklists[role][cl_name]):
                        checklists[role][cl_name][task_index] = text
                        save_checklists()
                        await message.answer(f"✅ Task updated!")
                        await show_checklist_editor(message, state, role, cl_name)
                    else:
                        await message.answer("❌ Task index out of range!")
                else:
                    await message.answer("❌ Error: Missing data for task update!")
                
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.RENAME_CHECKLIST.state:
                data = await state.get_data()
                role = data.get('role')
                old_name = data.get('checklist')
                new_name = text
                
                if role and old_name:
                    # Rename checklist
                    if old_name in checklists[role]:
                        checklists[role][new_name] = checklists[role].pop(old_name)
                        save_checklists()
                        
                        # Update assignments if needed
                        for uid, assignment in user_assignments.items():
                            if assignment["role"] == role and assignment["checklist"] == old_name:
                                assignment["checklist"] = new_name
                        save_user_assignments()
                        
                        await message.answer(f"✅ Checklist renamed to {new_name}!")
                        await show_checklist_editor(message, state, role, new_name)
                    else:
                        await message.answer("❌ Checklist not found!")
                else:
                    await message.answer("❌ Error: Role or checklist name missing!")
                
                await state.set_state(None)
                return
                
            elif current_state == AdminStates.NEW_CHECKLIST.state:
                data = await state.get_data()
                role = data.get('role')
                cl_name = text
                
                if role:
                    # Create new checklist
                    if cl_name not in checklists[role]:
                        checklists[role][cl_name] = []
                        save_checklists()
                        await message.answer(f"✅ Checklist {cl_name} created!")
                        await show_checklist_editor(message, state, role, cl_name)
                    else:
                        await message.answer("❌ Checklist with this name already exists!")
                else:
                    await message.answer("❌ Error: Role not found!")
                
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
            user_name = text
            user_sessions[user_id]["name"] = user_name
            
            # Check if user has an assignment
            if str(user_id) in user_assignments:
                assignment = user_assignments[str(user_id)]
                role = assignment["role"]
                cl_name = assignment["checklist"]
                
                if role in checklists and cl_name in checklists[role]:
                    user_sessions[user_id].update({
                        "role": role,
                        "checklist": cl_name,
                        "tasks": checklists[role][cl_name],
                        "current_task": 0,
                        "results": [],
                        "step": "task"
                    })
                    
                    await send_task(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        user_id=user_id
                    )
                else:
                    await message.answer("❌ Your assigned checklist is no longer available. Please contact admin.")
            else:
                await message.answer("❌ You don't have an assigned checklist. Please contact admin.")
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

async def manage_assignments_handler(message: types.Message, state: FSMContext):
    """Handler for /manage_assignments command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have permission to use this command.")
        return
        
    await state.set_state(AdminStates.MANAGE_ASSIGNMENTS)
    keyboard = assignments_keyboard()
    await message.answer("👤 User Assignments Management:", reply_markup=keyboard)

async def reports_handler(message: types.Message, state: FSMContext):
    """Handler for /reports command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have permission to use this command.")
        return
        
    await state.set_state(AdminStates.VIEW_REPORTS)
    keyboard = reports_keyboard()
    await message.answer("📊 Reports Management:", reply_markup=keyboard)

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
    try:
        if role not in checklists or cl_name not in checklists[role]:
            await message.answer("❌ Checklist not found!")
            return
        
        tasks = checklists[role][cl_name]
        keyboard = tasks_keyboard(tasks)
        
        # Store current context
        await state.update_data(role=role, checklist=cl_name)
        
        # Try to edit message if possible, otherwise send new
        if isinstance(message, types.CallbackQuery):
            await message.message.edit_text(
                f"📝 Editing: {role} - {cl_name}\n\n"
                f"Tasks ({len(tasks)}):",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                f"📝 Editing: {role} - {cl_name}\n\n"
                f"Tasks ({len(tasks)}):",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error in show_checklist_editor: {e}")
        await message.answer("❌ Error loading checklist editor. Please try again.")

async def admin_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handler for admin callback queries"""
    try:
        logger.info(f"Admin callback: {callback.data}")
        
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
            await callback.message.edit_text(
                f"Select a checklist for {role}:",
                reply_markup=keyboard
            )
        
        # Checklist selection
        elif data.startswith("cl:"):
            cl_name = data.split(":")[1]
            role = (await state.get_data()).get('role')
            
            if role:
                await show_checklist_editor(callback, state, role, cl_name)
            else:
                await callback.message.answer("❌ Role not selected!")
        
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
            
            data = await state.get_data()
            role = data.get('role')
            cl_name = data.get('checklist')
            
            if role and cl_name and 0 <= task_index < len(checklists[role][cl_name]):
                task_text = checklists[role][cl_name][task_index]
                await callback.message.answer(
                    f"Current task text:\n{task_text}\n\n"
                    "Please enter the new text for this task:"
                )
            else:
                await callback.message.answer("❌ Task not found!")
            
        # Delete task confirmation
        elif data.startswith("delete_task:"):
            task_index = int(data.split(":")[1])
            await state.set_state(AdminStates.CONFIRM_DELETE_TASK)
            await state.update_data(task_index=task_index)
            
            data = await state.get_data()
            role = data.get('role')
            cl_name = data.get('checklist')
            
            if role and cl_name and 0 <= task_index < len(checklists[role][cl_name]):
                task_text = checklists[role][cl_name][task_index]
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"confirm_delete_task:{task_index}")],
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_delete")]
                ])
                
                await callback.message.answer(
                    f"⚠️ Are you sure you want to delete this task?\n\n{task_text}",
                    reply_markup=keyboard
                )
            else:
                await callback.message.answer("❌ Task not found!")
            
        # Confirm task deletion
        elif data.startswith("confirm_delete_task:"):
            task_index = int(data.split(":")[1])
            data = await state.get_data()
            role = data.get('role')
            cl_name = data.get('checklist')
            
            if role and cl_name and 0 <= task_index < len(checklists[role][cl_name]):
                deleted_task = checklists[role][cl_name].pop(task_index)
                save_checklists()
                await callback.message.answer(f"✅ Task deleted:\n{deleted_task}")
                await show_checklist_editor(callback, state, role, cl_name)
            else:
                await callback.message.answer("❌ Task not found!")
            
            await state.set_state(AdminStates.EDIT_CHECKLIST)
            
        # Delete checklist confirmation
        elif data.startswith("delete_cl:"):
            cl_name = data.split(":")[1]
            await state.set_state(AdminStates.CONFIRM_DELETE_CHECKLIST)
            await state.update_data(delete_cl_name=cl_name)
            
            data = await state.get_data()
            role = data.get('role')
            
            if role:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"confirm_delete_cl:{cl_name}")],
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_delete")]
                ])
                
                await callback.message.answer(
                    f"⚠️ Are you sure you want to delete the checklist '{cl_name}'?",
                    reply_markup=keyboard
                )
            else:
                await callback.message.answer("❌ Role not selected!")
            
        # Confirm checklist deletion
        elif data.startswith("confirm_delete_cl:"):
            cl_name = data.split(":")[1]
            data = await state.get_data()
            role = data.get('role')
            
            if role and cl_name in checklists.get(role, {}):
                checklists[role].pop(cl_name)
                save_checklists()
                
                # Remove assignments to this checklist
                for uid, assignment in list(user_assignments.items()):
                    if assignment["role"] == role and assignment["checklist"] == cl_name:
                        del user_assignments[uid]
                save_user_assignments()
                
                await callback.message.answer(f"✅ Checklist '{cl_name}' deleted!")
                
                # Return to role selection
                await state.set_state(AdminStates.SELECT_ROLE)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[])
                for role_name in checklists.keys():
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=role_name, callback_data=f"admin_role:{role_name}")
                    ])
                    
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="⬅️ Cancel", callback_data="admin_cancel")
                ])
                
                await callback.message.edit_text("Select a role to edit checklists:", reply_markup=keyboard)
            else:
                await callback.message.answer("❌ Checklist not found!")
            
        # Cancel delete operation
        elif data == "cancel_delete":
            data = await state.get_data()
            role = data.get('role')
            cl_name = data.get('checklist')
            
            if role and cl_name:
                await state.set_state(AdminStates.EDIT_CHECKLIST)
                await show_checklist_editor(callback, state, role, cl_name)
            else:
                await callback.message.answer("❌ Operation canceled.")
                await state.set_state(None)
        
        # Back to checklists
        elif data == "back_to_checklists":
            data = await state.get_data()
            role = data.get('role')
            
            if role:
                await state.set_state(AdminStates.SELECT_CHECKLIST)
                keyboard = checklist_keyboard(role)
                await callback.message.edit_text(
                    f"Select a checklist for {role}:",
                    reply_markup=keyboard
                )
            else:
                await callback.message.answer("❌ Role not selected!")
        
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
        
        # View reports
        elif data == "view_reports":
            reports = get_reports(10)
            if not reports:
                await callback.message.answer("📭 No reports available.")
                return
                
            response = "📋 Last 10 Reports:\n\n"
            for i, report_file in enumerate(reports, 1):
                try:
                    with open(report_file, 'r') as f:
                        report = json.load(f)
                        done_count = sum(1 for _, status in report['results'] if status == 'Done')
                        not_done_count = sum(1 for _, status in report['results'] if status != 'Done')
                        
                        response += (
                            f"{i}. {report['date']}\n"
                            f"👤 {report['user_name']} (ID: {report['user_id']})\n"
                            f"🏷️ {report['role']} - {report['checklist']}\n"
                            f"✅ Done: {done_count}\n"
                            f"❌ Not Done: {not_done_count}\n\n"
                        )
                except Exception as e:
                    logger.error(f"Error reading report {report_file}: {e}")
                    response += f"{i}. Error reading report\n\n"
            
            await callback.message.answer(response)
        
        # Download reports
        elif data == "download_reports":
            csv_file = generate_csv_report()
            await callback.message.answer_document(
                FSInputFile(csv_file),
                caption="📥 All reports in CSV format"
            )
        
        # Clear reports
        elif data == "clear_reports":
            deleted_count = clear_reports()
            await callback.message.answer(f"🧹 Deleted {deleted_count} reports!")
        
        # Back to admin menu
        elif data == "back_to_admin":
            await state.set_state(None)
            await callback.message.answer("🔙 Returned to main menu")
        
        # Cancel admin operation
        elif data == "admin_cancel":
            await state.set_state(None)
            await callback.message.answer("Admin operation cancelled.")
            
        # ========== ASSIGNMENT MANAGEMENT ==========
        elif data == "manage_assignments":
            await state.set_state(AdminStates.MANAGE_ASSIGNMENTS)
            keyboard = assignments_keyboard()
            await callback.message.edit_text("👤 User Assignments Management:", reply_markup=keyboard)
            
        elif data == "assign_user":
            await state.set_state(AdminStates.SELECT_USER_TO_ASSIGN)
            
            # Get all users that have started the bot
            known_users = set()
            for uid in user_sessions.keys():
                known_users.add(uid)
            for uid in user_assignments.keys():
                known_users.add(int(uid))
            
            if not known_users:
                await callback.message.answer("❌ No users found. Users must start the bot first.")
                return
                
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for uid in known_users:
                user_name = get_user_name(uid)
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=f"{user_name} (ID: {uid})", callback_data=f"assign_user:{uid}")
                ])
                
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_assignments")
            ])
            
            await callback.message.edit_text("Select user to assign checklist:", reply_markup=keyboard)
            
        elif data.startswith("assign_user:"):
            user_id = int(data.split(":")[1])
            await state.update_data(assign_user_id=user_id)
            await state.set_state(AdminStates.SELECT_ROLE)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for role in checklists.keys():
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=role, callback_data=f"assign_role:{role}")
                ])
                
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back", callback_data="assign_user")
            ])
            
            user_name = get_user_name(user_id)
            await callback.message.edit_text(
                f"Select role for {user_name}:",
                reply_markup=keyboard
            )
            
        elif data.startswith("assign_role:"):
            role = data.split(":")[1]
            data = await state.get_data()
            user_id = data.get('assign_user_id')
            
            if not user_id:
                await callback.message.answer("❌ User not selected!")
                return
                
            await state.update_data(assign_role=role)
            await state.set_state(AdminStates.SELECT_CHECKLIST_TO_ASSIGN)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for cl_name in checklists[role].keys():
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=cl_name, callback_data=f"assign_checklist:{cl_name}")
                ])
                
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back", callback_data=f"assign_user:{user_id}")
            ])
            
            user_name = get_user_name(user_id)
            await callback.message.edit_text(
                f"Select checklist for {user_name} ({role}):",
                reply_markup=keyboard
            )
            
        elif data.startswith("assign_checklist:"):
            cl_name = data.split(":")[1]
            data = await state.get_data()
            user_id = data.get('assign_user_id')
            role = data.get('assign_role')
            
            if not user_id or not role:
                await callback.message.answer("❌ Missing assignment data!")
                return
                
            # Save assignment
            user_assignments[str(user_id)] = {
                "role": role,
                "checklist": cl_name
            }
            save_user_assignments()
            
            user_name = get_user_name(user_id)
            await callback.message.answer(
                f"✅ Checklist assigned!\n"
                f"👤 User: {user_name}\n"
                f"🏷️ Role: {role}\n"
                f"📋 Checklist: {cl_name}"
            )
            
            # Return to assignments menu
            await state.set_state(AdminStates.MANAGE_ASSIGNMENTS)
            keyboard = assignments_keyboard()
            await callback.message.answer("👤 User Assignments Management:", reply_markup=keyboard)
            
        elif data == "view_assignments":
            if not user_assignments:
                await callback.message.answer("📭 No assignments found.")
                return
                
            response = "📋 Current Assignments:\n\n"
            for uid, assignment in user_assignments.items():
                user_name = get_user_name(int(uid))
                response += f"👤 {user_name} (ID: {uid})\n"
                response += f"🏷️ Role: {assignment['role']}\n"
                response += f"📋 Checklist: {assignment['checklist']}\n\n"
            
            await callback.message.answer(response)
            
        elif data == "remove_assignment":
            if not user_assignments:
                await callback.message.answer("📭 No assignments to remove.")
                return
                
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for uid, assignment in user_assignments.items():
                user_name = get_user_name(int(uid))
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"{user_name} - {assignment['role']} - {assignment['checklist']}",
                        callback_data=f"remove_assignment:{uid}"
                    )
                ])
                
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_assignments")
            ])
            
            await callback.message.edit_text("Select assignment to remove:", reply_markup=keyboard)
            
        elif data.startswith("remove_assignment:"):
            uid = data.split(":")[1]
            if uid in user_assignments:
                assignment = user_assignments.pop(uid)
                save_user_assignments()
                
                user_name = get_user_name(int(uid))
                await callback.message.answer(
                    f"✅ Assignment removed!\n"
                    f"👤 User: {user_name}\n"
                    f"🏷️ Role: {assignment['role']}\n"
                    f"📋 Checklist: {assignment['checklist']}"
                )
            else:
                await callback.message.answer("❌ Assignment not found!")
                
            # Return to assignments menu
            await state.set_state(AdminStates.MANAGE_ASSIGNMENTS)
            keyboard = assignments_keyboard()
            await callback.message.answer("👤 User Assignments Management:", reply_markup=keyboard)
            
        elif data == "back_to_assignments":
            await state.set_state(AdminStates.MANAGE_ASSIGNMENTS)
            keyboard = assignments_keyboard()
            await callback.message.edit_text("👤 User Assignments Management:", reply_markup=keyboard)
            
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

        if data.startswith("task:"):
            if user_id not in user_sessions or user_sessions[user_id].get("step") != "task":
                await callback.message.answer("❌ Session expired. Please restart with /start")
                return
                
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
        if user_id not in user_sessions or user_sessions[user_id].get("step") != "task":
            await bot.send_message(chat_id, "❌ Session expired. Please restart with /start")
            return
            
        session = user_sessions[user_id]
        task_text = session["tasks"][session["current_task"]]
        
        # Create response buttons
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
        report = f"📋 Checklist Report\n👤 Name: {session['name']}\nRole: {session['role']}\nChecklist: {session['checklist']}\n\n"
        
        for task, result in session["results"]:
            status = "✅ Done" if result == "Done" else "❌ Not Done"
            report += f"- {task} → {status}\n"
        
        # Save report
        save_report(
            user_id=user_id,
            user_name=session['name'],
            role=session['role'],
            cl_name=session['checklist'],
            results=session["results"]
        )
        
        await message.answer("✅ Checklist completed! Report saved.")
        
        try:
            # Send report to all admins
            for admin_id in ADMIN_IDS:
                await message.bot.send_message(
                    admin_id, 
                    report
                )
                logger.info(f"Report sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"Error sending report: {e}\n{traceback.format_exc()}")
            await message.answer("⚠️ Failed to send report to managers. Please notify admin directly.")
        
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
        
        dp = Dispatcher(storage=storage)
        
        # Register handlers
        dp.message.register(start_handler, Command("start"))
        dp.message.register(edit_checklists_handler, Command("edit_checklists"))
        dp.message.register(manage_assignments_handler, Command("manage_assignments"))
        dp.message.register(reports_handler, Command("reports"))
        dp.message.register(generate_password_handler, Command("generate_password"))
        dp.message.register(message_handler)
        
        # Callback handlers
        dp.callback_query.register(callback_handler)
        dp.callback_query.register(admin_callback_handler)
        
        # Startup actions
        dp.startup.register(on_startup)
        
        # Create aiohttp application
        app = web.Application()
        app["bot"] = bot
        
        # Register endpoints
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        
        # Webhook handler with timeout
        async def webhook_handler(request: web.Request) -> web.Response:
            try:
                logger.info(f"Incoming webhook request to: {request.path}")
                
                # Secret token verification
                secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                
                # Use globally defined SECRET_TOKEN
                if secret_token != SECRET_TOKEN:
                    logger.warning(f"Invalid secret token! Expected: {SECRET_TOKEN}, Got: {secret_token}")
                    return web.Response(status=403, text="Forbidden")
                
                # Process update with timeout
                try:
                    return await asyncio.wait_for(
                        SimpleRequestHandler(dispatcher=dp, bot=bot).handle(request),
                        timeout=10  # 10 seconds timeout
                    )
                except asyncio.TimeoutError:
                    logger.error("Request processing timed out")
                    return web.Response(status=504, text="Gateway Timeout")
                    
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