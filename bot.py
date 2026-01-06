# =================== ПАНЕЛЬ ВЛАДЕЛЬЦА ===================
@dp.message(Command("owner"))
async def owner_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    # Разные панели для ЛС и групп
    if message.chat.type == ChatType.PRIVATE:
        # В ЛС - подробная панель с кнопками
        text = (
            "👑 *Панель владельца*\n\n"
            "📊 *Статистика и мониторинг:*\n"
            "/stats - статистика бота\n"
            "/chats - список всех чатов\n\n"
            "💰 *Управление балансами:*\n"
            "/give <id> <сумма> - выдать деньги\n"
            "/set <id> <сумма> - установить баланс\n\n"
            "🎖️ *Управление подписками:*\n"
            "/gold <id> <дни> - выдать GOLD\n"
            "/gold_forever <id> - вечная GOLD\n"
            "/remove_gold <id> - удалить подписку\n\n"
            "🍀 *Управление удачей:*\n"
            "/luck <id> <значение> - удача\n"
            "/temp_luck <id> <значение> <минуты> - временная\n"
            "/luck_all <значение> - удача всем\n"
            "/luck_reset_all - сбросить удачу всем\n\n"
            "⚙️ *Администрация:*\n"
            "/ban <id> - забанить\n"
            "/unban <id> - разбанить\n"
            "/resetcd <id> - сбросить кулдауны\n\n"
            "📢 *Рассылка:*\n"
            "/broadcast <текст> - отправить всем\n\n"
            "🎪 *Эвенты:*\n"
            "/owner_event - запустить эвент\n"
            "/stop_event - остановить эвент"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="refresh_stats"),
            InlineKeyboardButton(text="📋 Список чатов", callback_data="all_chats_list")
        )
        
        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    else:
        # В группах - упрощенная панель
        text = (
            "👑 *Панель владельца*\n\n"
            "💰 *Управление балансами:*\n"
            "/give <id> <сумма> - выдать деньги\n"
            "/set <id> <сумма> - установить баланс\n\n"
            "🎖️ *Управление подписками:*\n"
            "/gold <id> <дни> - выдать GOLD\n"
            "/gold_forever <id> - вечная GOLD\n"
            "/remove_gold <id> - удалить подписку\n\n"
            "🍀 *Управление удачей:*\n"
            "/luck <id> <значение> - установить удачу\n"
            "/temp_luck <id> <значение> <минуты> - временная удача\n"
            "/luck_all <значение> - удача всем\n"
            "/luck_reset_all - сбросить удачу всем\n\n"
            "⚙️ *Администрация:*\n"
            "/ban <id> - забанить\n"
            "/unban <id> - разбанить\n"
            "/resetcd <id> - сбросить кулдауны\n\n"
            "📢 *Рассылка:*\n"
            "/broadcast <текст> - отправить всем\n\n"
            "🎪 *Эвенты:*\n"
            "/owner_event - запустить эвент\n"
            "/stop_event - остановить эвент"
        )
        
        await message.answer(text, parse_mode="Markdown")

# =================== СТАТИСТИКА БОТА ===================
@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    """Статистика бота - доступна только владельцу"""
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    all_users = db.get_all_users()
    total_balance = sum(user.get('balance', 0) for user in all_users.values())
    total_earned = sum(user.get('total_earned', 0) for user in all_users.values())
    gold_users = sum(1 for user in all_users.values() if user.get('subscription') == 'gold')
    
    text = (
        f"📊 *Статистика бота*\n\n"
        f"👥 *Пользователи:* {len(all_users)}\n"
        f"🎖️ *С GOLD:* {gold_users}\n"
        f"💰 *Общий баланс:* {total_balance:.2f} ¢\n"
        f"💸 *Всего заработано:* {total_earned:.2f} ¢\n"
        f"🎪 *Активных эвентов:* {1 if active_event else 0}"
    )
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "refresh_stats")
async def refresh_stats_callback(callback_query: CallbackQuery):
    """Обновить статистику"""
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    message = Message(
        message_id=callback_query.message.message_id,
        date=datetime.now(),
        chat=callback_query.message.chat,
        from_user=callback_query.from_user,
        text=""
    )
    await stats_cmd(message)
    await callback_query.answer("✅ Статистика обновлена!")

@dp.message(Command("chats"))
async def chats_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    # Простой список чатов
    text = "📋 *Список чатов*\n\n"
    text += "ℹ️ Для просмотра всех чатов используйте команду в ЛС бота"
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "all_chats_list")
async def all_chats_list_callback(callback_query: CallbackQuery):
    """Показать список всех чатов"""
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    # Простой ответ
    text = "📋 *Список всех чатов*\n\n"
    text += "ℹ️ Для просмотра всех чатов используйте команду /chats в ЛС бота"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")
    await callback_query.answer()

# =================== КОМАНДЫ ВЛАДЕЛЬЦА ===================
@dp.message(Command("give"))
async def give_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.update_balance(user_id, amount)
        await message.answer(f"✅ Выдано {amount} ¢ пользователю {user_id}")
    except:
        await message.answer("❌ Использование: /give <id> <сумма>")

@dp.message(Command("set"))
async def set_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        user_data = db.get_user_data(user_id)
        user_data['balance'] = round(amount, 2)
        db.save_user_data(user_id, user_data)
        await message.answer(f"✅ Баланс установлен: {amount} ¢ для {user_id}")
    except:
        await message.answer("❌ Использование: /set <id> <сумма>")

@dp.message(Command("gold"))
async def give_gold(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        args = command.args.split()
        user_id = int(args[0])
        days = int(args[1]) if len(args) > 1 else 30
        db.give_gold(user_id, days)
        await message.answer(f"✅ GOLD на {days} дней выдана пользователю {user_id}")
    except:
        await message.answer("❌ Использование: /gold <id> <дни>")

@dp.message(Command("gold_forever"))
async def gold_forever(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        user_id = int(command.args)
        db.give_gold(user_id, permanent=True)
        await message.answer(f"✅ Вечная GOLD выдана пользователю {user_id}")
    except:
        await message.answer("❌ Использование: /gold_forever <id>")

@dp.message(Command("remove_gold"))
async def remove_gold_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        user_id = int(command.args)
        user_data = db.get_user_data(user_id)
        user_data['subscription'] = None
        user_data['subscription_end'] = None
        user_data['is_permanent'] = False
        db.save_user_data(user_id, user_data)
        await message.answer(f"✅ GOLD удалена у пользователя {user_id}")
    except:
        await message.answer("❌ Использование: /remove_gold <id>")

@dp.message(Command("ban"))
async def ban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        user_id = int(command.args)
        user_data = db.get_user_data(user_id)
        user_data['is_banned'] = True
        db.save_user_data(user_id, user_data)
        await message.answer(f"⛔ Пользователь {user_id} забанен")
    except:
        await message.answer("❌ Использование: /ban <id>")

@dp.message(Command("unban"))
async def unban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        user_id = int(command.args)
        user_data = db.get_user_data(user_id)
        user_data['is_banned'] = False
        db.save_user_data(user_id, user_data)
        await message.answer(f"✅ Пользователь {user_id} разбанен")
    except:
        await message.answer("❌ Использование: /unban <id>")

@dp.message(Command("resetcd"))
async def reset_cd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        user_id = int(command.args)
        user_data = db.get_user_data(user_id)
        user_data['cooldowns'] = {}
        db.save_user_data(user_id, user_data)
        await message.answer(f"✅ Кулдауны сброшены у пользователя {user_id}")
    except:
        await message.answer("❌ Использование: /resetcd <id>")

@dp.message(Command("luck"))
async def set_luck_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        args = command.args.split()
        user_id, luck_value = int(args[0]), float(args[1])
        luck_value = max(1.0, min(100.0, luck_value))
        db.set_luck(user_id, luck_value)
        await message.answer(f"✅ Удача {luck_value:.1f}x установлена пользователю {user_id}")
    except:
        await message.answer("❌ Использование: /luck <id> <значение>")

@dp.message(Command("temp_luck"))
async def set_temp_luck_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        args = command.args.split()
        user_id, luck_value, minutes = int(args[0]), float(args[1]), int(args[2])
        db.set_temp_luck(user_id, luck_value, minutes)
        await message.answer(f"✅ Временная удача {luck_value:.1f}x на {minutes} мин установлена пользователю {user_id}")
    except:
        await message.answer("❌ Использование: /temp_luck <id> <значение> <минуты>")

@dp.message(Command("luck_all"))
async def set_luck_all_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    try:
        luck_value = float(command.args)
        all_users = db.get_all_users()
        for user_id, user_data in all_users.items():
            user_data['luck'] = max(1.0, min(100.0, luck_value))
            db.save_user_data(user_id, user_data)
        await message.answer(f"✅ Удача {luck_value:.1f}x установлена всем пользователям ({len(all_users)} чел.)")
    except:
        await message.answer("❌ Использование: /luck_all <значение>")

@dp.message(Command("luck_reset_all"))
async def reset_luck_all_cmd(message: Message):
    if message.from_user.id != OWNER_ID: 
        return
    
    all_users = db.get_all_users()
    for user_id, user_data in all_users.items():
        user_data['luck'] = 1.0
        db.save_user_data(user_id, user_data)
    
    await message.answer(f"✅ Удача сброшена у всех пользователей ({len(all_users)} чел.)")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: 
        return
    
    if not command.args:
        await message.answer("❌ Укажите текст для рассылки!\n/broadcast <текст>")
        return
    
    broadcast_text = command.args
    all_users = db.get_all_users()
    sent = 0
    
    await message.answer(f"📢 Рассылка началась ({len(all_users)} пользователей)...")
    
    for user_id in all_users.keys():
        try:
            await bot.send_message(user_id, f"📢 *Сообщение от администратора:*\n\n{broadcast_text}", parse_mode="Markdown")
            sent += 1
            if sent % 10 == 0:
                await asyncio.sleep(1)
        except:
            pass
    
    await message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}/{len(all_users)}")

@dp.message(Command("owner_event"))
async def owner_event_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    global active_event
    if active_event:
        await message.answer("❌ Уже есть активный эвент!")
        return
    
    event_types = [
        ("🎯 Обычный", 100, 300, 1.0),
        ("🚀 Средний", 300, 600, 1.0),
        ("💎 Мега", 600, 1000, 1.2)
    ]
    etype, emin, emax, bonus = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    
    active_event = {
        'id': event_id, 'type': etype, 'reward': reward,
        'end_time': datetime.now() + timedelta(hours=1),
        'chat_id': message.chat.id, 'creator': OWNER_ID,
        'bonus_value': bonus
    }
    event_participants[event_id] = []
    
    text = f"🎪 *Владелец запустил эвент!*\n\n🎯 {etype}\n💰 {reward} ¢\n⏳ 1 час\n\n*Присоединяйтесь!*"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 Присоединиться", callback_data=f"join_event_{event_id}"))
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    event_participants[event_id].append(OWNER_ID)

@dp.message(Command("stop_event"))
async def stop_event_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    global active_event
    if not active_event:
        await message.answer("❌ Нет активных эвентов!")
        return
    
    active_event = None
    await message.answer("✅ Эвент остановлен!")

# =================== CALLBACK ДЛЯ ПАНЕЛИ ВЛАДЕЛЬЦА ===================
@dp.callback_query(lambda c: c.data == "owner_panel")
async def owner_panel_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    message = Message(
        message_id=callback_query.message.message_id,
        date=datetime.now(),
        chat=callback_query.message.chat,
        from_user=callback_query.from_user,
        text=""
    )
    
    await owner_cmd(message)
    await callback_query.answer()
