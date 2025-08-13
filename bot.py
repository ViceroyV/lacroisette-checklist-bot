# ========== ADMIN STATES ==========
class AdminStates(StatesGroup):
    # ... существующие состояния ...
    MANAGE_ROLES = State()  # Новое состояние для управления ролями
    ADD_ROLE = State()
    RENAME_ROLE = State()
    CONFIRM_DELETE_ROLE = State()

# ... остальной код без изменений ...

# ========== COMMAND HANDLERS ==========
async def edit_checklists_handler(message: types.Message, state: FSMContext):
    """Handler for /edit_checklists command"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ You don't have permission to use this command.")
        return
        
    # Вместо перехода к выбору роли сразу, переходим к управлению ролями
    await state.set_state(AdminStates.MANAGE_ROLES)
    keyboard = manage_roles_keyboard()
    await message.answer("👤 Role Management:", reply_markup=keyboard)

# ... остальной код без изменений ...

# ========== HELPER FUNCTIONS ==========
def manage_roles_keyboard():
    """Create role management keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for role in sorted(checklists.keys()):  # Сортируем роли для порядка
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=role, callback_data=f"select_role:{role}")
        ])
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="✏️ Rename", callback_data=f"rename_role:{role}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_role:{role}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Add New Role", callback_data="add_role")
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="back_to_admin")
    ])
    return keyboard

# ... остальной код без изменений ...

# ========== ADMIN CALLBACK HANDLER ==========
async def admin_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handler for admin callback queries"""
    try:
        # ... существующий код ...
        
        # Управление ролями
        elif data == ("add_role"):
            await state.set_state(AdminStates.ADD_ROLE)
            await callback.message.answer("Please enter the name for the new role:")
            
        elif data.startswith("rename_role:"):
            role = data.split(":")[1]
            await state.set_state(AdminStates.RENAME_ROLE)
            await state.update_data(old_role=role)
            await callback.message.answer(f"Please enter the new name for the role '{role}':")
            
        elif data.startswith("delete_role:"):
            role = data.split(":")[1]
            await state.set_state(AdminStates.CONFIRM_DELETE_ROLE)
            await state.update_data(delete_role=role)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"confirm_delete_role:{role}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_delete")]
            ])
            
            await callback.message.answer(
                f"⚠️ Are you sure you want to delete the role '{role}' and all its checklists?",
                reply_markup=keyboard
            )
            
        elif data.startswith("confirm_delete_role:"):
            role = data.split(":")[1]
            
            if role in checklists:
                # Удаляем роль и все связанные чек-листы
                del checklists[role]
                save_checklists()
                
                # Удаляем все назначения для этой роли
                for uid, assignment in list(user_assignments.items()):
                    if assignment["role"] == role:
                        del user_assignments[uid]
                save_user_assignments()
                
                await callback.message.answer(f"✅ Role '{role}' and all its checklists have been deleted.")
            else:
                await callback.message.answer("❌ Role not found!")
                
            # Возвращаемся к управлению ролями
            await state.set_state(AdminStates.MANAGE_ROLES)
            keyboard = manage_roles_keyboard()
            await callback.message.answer("👤 Role Management:", reply_markup=keyboard)
            
        # Выбор роли для редактирования
        elif data.startswith("select_role:"):
            role = data.split(":")[1]
            await state.set_state(AdminStates.SELECT_CHECKLIST)
            await state.update_data(role=role)
            
            keyboard = checklist_keyboard(role)
            await callback.message.edit_text(
                f"Select a checklist for {role}:",
                reply_markup=keyboard
            )
            
        # ... остальной существующий код ...
        
    except Exception as e:
        logger.error(f"Error in admin_callback_handler: {e}\n{traceback.format_exc()}")
        await callback.message.answer("❌ Admin operation error. Please try again.")

# ========== MESSAGE HANDLER ==========
async def message_handler(message: types.Message, state: FSMContext):
    """Handler for text messages"""
    try:
        # ... существующий код ...
        
        # Обработка новых состояний для управления ролями
        current_state = await state.get_state()
        
        # Добавление новой роли
        if current_state == AdminStates.ADD_ROLE.state:
            new_role = text.strip()
            
            if new_role in checklists:
                await message.answer("❌ Role already exists!")
            else:
                checklists[new_role] = {}
                save_checklists()
                await message.answer(f"✅ Role '{new_role}' created!")
                await state.set_state(AdminStates.MANAGE_ROLES)
                keyboard = manage_roles_keyboard()
                await message.answer("👤 Role Management:", reply_markup=keyboard)
        
        # Переименование роли
        elif current_state == AdminStates.RENAME_ROLE.state:
            new_role_name = text.strip()
            data = await state.get_data()
            old_role = data.get('old_role')
            
            if old_role not in checklists:
                await message.answer("❌ Original role not found!")
            elif new_role_name in checklists:
                await message.answer("❌ Role with this name already exists!")
            else:
                # Переносим данные в новую роль
                checklists[new_role_name] = checklists.pop(old_role)
                save_checklists()
                
                # Обновляем назначения
                for uid, assignment in user_assignments.items():
                    if assignment["role"] == old_role:
                        assignment["role"] = new_role_name
                save_user_assignments()
                
                await message.answer(f"✅ Role renamed from '{old_role}' to '{new_role_name}'!")
                await state.set_state(AdminStates.MANAGE_ROLES)
                keyboard = manage_roles_keyboard()
                await message.answer("👤 Role Management:", reply_markup=keyboard)
        
        # ... остальной существующий код ...
        
    except Exception as e:
        logger.error(f"Error in message_handler: {e}\n{traceback.format_exc()}")
        await message.answer("❌ Error processing your message. Please try /start again.")