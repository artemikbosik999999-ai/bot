#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import asyncio
import random
import redis
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatMemberStatus, ChatType

# =================== КОНСТАНТЫ ===================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "7119681628"))
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "artem_bori")

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

FARM_COMMANDS = {
    "кактус": {"emoji": "🌵", "min": 10, "max": 50},
    "ферма": {"emoji": "🚜", "min": 15, "max": 60},
    "шахта": {"emoji": "⛏️", "min": 20, "max": 70},
    "сад": {"emoji": "🌻", "min": 12, "max": 55},
    "охота": {"emoji": "🏹", "min": 25, "max": 80},
}

# =================== БАЗА ДАННЫХ ===================
class Database:
    def __init__(self):
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
                self.redis.ping()
                print("✅ Redis подключен")
            except:
                self.memory_db = {}
                self.redis = None
        else:
            self.memory_db = {}
            self.redis = None
    
    def get_user_data(self, user_id: int) -> Dict[str, Any]:
        if self.redis:
            data = self.redis.get(f"user:{user_id}")
            return json.loads(data) if data else self._default_user_data()
        else:
            return self.memory_db.get(user_id, self._default_user_data())
    
    def save_user_data(self, user_id: int, data: Dict[str, Any]):
        if self.redis:
            self.redis.set(f"user:{user_id}", json.dumps(data))
        else:
            self.memory_db[user_id] = data
    
    def update_chat_stats(self, chat_id: int, chat_title: str = None, chat_type: str = None):
        chat_data = self.get_chat_data(chat_id)
        if chat_title: chat_data['title'] = chat_title
        if chat_type: chat_data['type'] = chat_type
        chat_data['last_activity'] = datetime.now().isoformat()
        chat_data['message_count'] = chat_data.get('message_count', 0) + 1
        self.save_chat_data(chat_id, chat_data)
    
    def get_all_chats(self) -> Dict[int, Dict[str, Any]]:
        if self.redis:
            chats = {}
            for key in self.redis.keys("chat:*"):
                chat_id = int(key.split(":")[1])
                chats[chat_id] = json.loads(self.redis.get(key))
            return chats
        else:
            return {k: v for k, v in self.memory_db.items() if isinstance(k, str) and k.startswith("chat_")}
    
    def _default_user_data(self):
        return {
            'balance': 0.0, 'star_power': 0, 'productivity': 1.31, 'luck': 1.0,
            'temp_luck': None, 'temp_luck_value': None, 'temp_luck_end': None,
            'subscription': None, 'subscription_end': None, 'is_permanent': False,
            'cooldowns': {}, 'total_earned': 0, 'is_banned': False,
            'channel_check': False, 'event_bonus': None,
        }
    
    def _default_chat_data(self):
        return {'title': None, 'type': None, 'last_activity': datetime.now().isoformat(), 'message_count': 0, 'created_at': datetime.now().isoformat()}
    
    def get_chat_data(self, chat_id: int) -> Dict[str, Any]:
        if self.redis:
            data = self.redis.get(f"chat:{chat_id}")
            return json.loads(data) if data else self._default_chat_data()
        else:
            return self.memory_db.get(f"chat_{chat_id}", self._default_chat_data())
    
    def save_chat_data(self, chat_id: int, data: Dict[str, Any]):
        if self.redis:
            self.redis.set(f"chat:{chat_id}", json.dumps(data))
        else:
            self.memory_db[f"chat_{chat_id}"] = data
    
    def update_balance(self, user_id: int, amount: float):
        data = self.get_user_data(user_id)
        data['balance'] = round(data['balance'] + amount, 2)
        if amount > 0: data['total_earned'] = round(data.get('total_earned', 0) + amount, 2)
        self.save_user_data(user_id, data)
    
    def set_cooldown(self, user_id: int, command: str, hours: int = 2):
        data = self.get_user_data(user_id)
        data.setdefault('cooldowns', {})
        data['cooldowns'][command] = (datetime.now() + timedelta(hours=hours)).isoformat()
        self.save_user_data(user_id, data)
    
    def get_cooldown(self, user_id: int, command: str) -> Optional[datetime]:
        data = self.get_user_data(user_id)
        cooldown_str = data.get('cooldowns', {}).get(command)
        if cooldown_str:
            cd = datetime.fromisoformat(cooldown_str)
            return cd if datetime.now() < cd else None
        return None
    
    def check_gold(self, user_id: int) -> bool:
        data = self.get_user_data(user_id)
        if data.get('subscription') != 'gold': return False
        if data.get('is_permanent'): return True
        sub_end = data.get('subscription_end')
        return datetime.now() < datetime.fromisoformat(sub_end) if sub_end else False
    
    def get_effective_luck(self, user_id: int) -> float:
        data = self.get_user_data(user_id)
        luck = data.get('luck', 1.0)
        
        # Временная удача
        if data.get('temp_luck') and data.get('temp_luck_end'):
            end = datetime.fromisoformat(data['temp_luck_end'])
            if datetime.now() < end:
                luck = max(luck, data.get('temp_luck_value', 1.0))
        
        # Бонус эвента
        event_bonus = data.get('event_bonus')
        if event_bonus and event_bonus.get('end_time'):
            end = datetime.fromisoformat(event_bonus['end_time'])
            if datetime.now() < end:
                luck = round(luck * event_bonus.get('value', 1.0), 2)
        
        return luck
    
    def buy_gold(self, user_id: int) -> bool:
        data = self.get_user_data(user_id)
        if data['balance'] < 1500: return False
        data['balance'] = round(data['balance'] - 1500, 2)
        data['subscription'] = 'gold'
        data['subscription_end'] = (datetime.now() + timedelta(days=30)).isoformat()
        self.save_user_data(user_id, data)
        return True
    
    def give_gold(self, user_id: int, days: int = 30, permanent: bool = False):
        data = self.get_user_data(user_id)
        data['subscription'] = 'gold'
        if permanent:
            data['is_permanent'] = True
            data['subscription_end'] = None
        else:
            data['is_permanent'] = False
            data['subscription_end'] = (datetime.now() + timedelta(days=days)).isoformat()
        self.save_user_data(user_id, data)
    
    def set_luck(self, user_id: int, luck: float):
        data = self.get_user_data(user_id)
        data['luck'] = max(1.0, min(100.0, luck))
        self.save_user_data(user_id, data)
    
    def set_temp_luck(self, user_id: int, luck: float, minutes: int = 5):
        data = self.get_user_data(user_id)
        data['temp_luck'] = True
        data['temp_luck_value'] = max(1.0, min(100.0, luck))
        data['temp_luck_end'] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        self.save_user_data(user_id, data)
    
    def set_event_bonus(self, user_id: int, event_id: int, bonus_value: float, end_time: datetime):
        data = self.get_user_data(user_id)
        data['event_bonus'] = {'event_id': event_id, 'value': bonus_value, 'end_time': end_time.isoformat()}
        self.save_user_data(user_id, data)
    
    def get_all_users(self):
        if self.redis:
            users = {}
            for key in self.redis.keys("user:*"):
                user_id = int(key.split(":")[1])
                users[user_id] = json.loads(self.redis.get(key))
            return users
        else:
            return {k: v for k, v in self.memory_db.items() if isinstance(k, int)}

# =================== ИНИЦИАЛИЗАЦИЯ ===================
db = Database()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
active_event = None
event_participants = {}

# =================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===================
async def is_chat_admin(user_id: int, chat_id: int) -> bool:
    if chat_id > 0: return False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except:
        return False

async def check_channel_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.BANNED]
    except:
        return False

def format_time(end_time: Optional[datetime]) -> str:
    if not end_time: return "∞"
    if datetime.now() >= end_time: return "истекла"
    delta = end_time - datetime.now()
    if delta.days > 0: return f"{delta.days}д {delta.seconds//3600}ч"
    if delta.seconds >= 3600: return f"{delta.seconds//3600}ч {delta.seconds%3600//60}м"
    return f"{delta.seconds//60}м"

# =================== ОСНОВНЫЕ КОМАНДЫ ===================
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    if db.get_user_data(user_id).get('is_banned'):
        await message.answer("⛔ Вы забанены!")
        return
    
    if message.chat.type == ChatType.PRIVATE:
        text = "🤖 *Farm Bot*\n\n📢 Подпишись на канал и добавь бота в группу!"
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="📢 Канал", url=f"https://t.me/{CHANNEL_USERNAME}"))
        keyboard.row(InlineKeyboardButton(text="➕ В группу", url="https://t.me/farmirobot?startgroup=true"))
        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
        return
    
    if user_id != OWNER_ID and not db.get_user_data(user_id).get('channel_check'):
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="📢 Канал", url=f"https://t.me/{CHANNEL_USERNAME}"))
        keyboard.row(InlineKeyboardButton(text="✅ Проверить", callback_data="verify_sub"))
        await message.answer("🔒 Подпишись на канал!", reply_markup=keyboard.as_markup())
        return
    
    user_data = db.get_user_data(user_id)
    text = (
        f"🎮 *Farm Bot*\n\n"
        f"💰 Баланс: {user_data['balance']:.2f} ¢\n"
        f"✨ Сила: {user_data['star_power']}\n"
        f"🍀 Удача: {db.get_effective_luck(user_id):.1f}x\n\n"
        f"🌵 *Фарм команды:*\nкактус ферма шахта сад охота\n(кулдаун 2 часа)"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="📊 Профиль", callback_data="profile"),
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")
    )
    if user_id == OWNER_ID:
        keyboard.row(InlineKeyboardButton(text="👑 Владелец", callback_data="owner_panel"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    user_id = message.from_user.id
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("📊 Профиль только в группах!")
        return
    
    user_data = db.get_user_data(user_id)
    luck = db.get_effective_luck(user_id)
    
    text = (
        f"📊 *Профиль*\n\n"
        f"💰 Баланс: {user_data['balance']:.2f} ¢\n"
        f"✨ Сила: {user_data['star_power']}\n"
        f"⏳ Урожайность: {user_data['productivity']:.2f}\n"
        f"🍀 Удача: {luck:.1f}x\n\n"
        f"⏰ *Кулдауны:*\n"
    )
    
    for cmd in FARM_COMMANDS:
        cd = db.get_cooldown(user_id, cmd)
        text += f"• {cmd}: {format_time(cd) if cd else '✅ готово'}\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🌵 Кактус", callback_data="farm_cactus"),
        InlineKeyboardButton(text="🚜 Ферма", callback_data="farm_farm")
    )
    keyboard.row(
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")
    )
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("shop"))
async def shop_cmd(message: Message):
    user_id = message.from_user.id
    user_data = db.get_user_data(user_id)
    has_gold = db.check_gold(user_id)
    
    text = (
        "🛒 *Магазин*\n\n"
        "✨ *Сила звёздности (100 ¢)*\n+0.5 ¢ к награде\n\n"
        "⏳ *Урожайность (150 ¢)*\n×1.1 к наградам\n\n"
        "🍀 *Удача (200 ¢)*\n+0.1x к удаче\n\n"
        "🎖️ *GOLD подписка (1500 ¢)*\n+20% к наградам на 30 дней\n\n"
        f"💰 Ваш баланс: {user_data['balance']:.2f} ¢\n"
        f"🍀 Удача: {db.get_effective_luck(user_id):.1f}x"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✨ Сила +1", callback_data="buy_star"),
        InlineKeyboardButton(text="⏳ Урожайность", callback_data="buy_prod")
    )
    keyboard.row(
        InlineKeyboardButton(text="🍀 Удача +0.1", callback_data="buy_luck"),
        InlineKeyboardButton(text="🎖️ GOLD", callback_data="buy_gold")
    )
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("events"))
async def events_cmd(message: Message):
    global active_event
    text = "🎪 *Эвенты*\n\n"
    
    if active_event:
        parts = len(event_participants.get(active_event['id'], []))
        time_left = format_time(active_event['end_time'])
        text += (
            f"🚀 *Активный эвент!*\n"
            f"🎯 {active_event['type']}\n"
            f"💰 {active_event['reward']} ¢\n"
            f"👥 {parts} участников\n"
            f"⏳ {time_left}"
        )
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🎪 Присоединиться", callback_data=f"join_event_{active_event['id']}"))
    else:
        text += "📭 Нет активных эвентов\n\n🚀 Запускают админы с GOLD"
        keyboard = InlineKeyboardBuilder()
        if await is_chat_admin(message.from_user.id, message.chat.id) and db.check_gold(message.from_user.id):
            keyboard.row(InlineKeyboardButton(text="🚀 Запустить", callback_data="event_start"))
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu"))
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

# =================== ФАРМ КОМАНДЫ ===================
@dp.message(lambda msg: msg.text and msg.text.lower() in FARM_COMMANDS)
async def farm_command(message: Message):
    user_id = message.from_user.id
    cmd = message.text.lower()
    
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("⛔ Фарм только в группах!")
        return
    
    if db.get_user_data(user_id).get('is_banned'):
        await message.answer("⛔ Вы забанены!")
        return
    
    cd = db.get_cooldown(user_id, cmd)
    if cd:
        await message.reply(f"⏳ {cmd} на кулдауне!\nВернитесь через {format_time(cd)}")
        return
    
    user_data = db.get_user_data(user_id)
    cmd_info = FARM_COMMANDS[cmd]
    
    # Расчет награды
    luck = db.get_effective_luck(user_id)
    base_reward = random.randint(cmd_info["min"], cmd_info["max"])
    
    # Учет удачи (30% шанс)
    if random.random() < 0.3:
        base_reward = int(base_reward * (1 + (luck - 1.0) * 0.1))
    
    # Бонусы
    reward = base_reward + user_data['star_power'] * 0.5
    reward *= user_data['productivity']
    if db.check_gold(user_id): reward *= 1.2
    
    # Рандомный бонус (26% шанс)
    if random.random() < 0.26:
        reward += random.randint(5, 15)
    
    reward = round(reward, 2)
    db.update_balance(user_id, reward)
    db.set_cooldown(user_id, cmd, 2)
    
    response = (
        f"{cmd_info['emoji']} {cmd.upper()} ✅ *ЗАЧЁТ!*\n\n"
        f"💰 *+{reward:.2f} ¢*\n"
        f"💳 Баланс: {db.get_user_data(user_id)['balance']:.2f} ¢\n\n"
        f"⏳ Возвращайтесь через 2 часа"
    )
    
    await message.reply(response, parse_mode="Markdown")

# =================== CALLBACK ОБРАБОТЧИКИ ===================
@dp.callback_query(lambda c: c.data == "verify_sub")
async def verify_sub_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await check_channel_subscription(user_id):
        user_data = db.get_user_data(user_id)
        user_data['channel_check'] = True
        db.save_user_data(user_id, user_data)
        await callback_query.message.edit_text("✅ Подписка подтверждена!")
    else:
        await callback_query.answer("❌ Вы не подписаны!", show_alert=True)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("farm_"))
async def farm_button_callback(callback_query: CallbackQuery):
    cmd_map = {"cactus": "кактус", "farm": "ферма", "mine": "шахта", "garden": "сад", "hunt": "охота"}
    cmd = callback_query.data.replace("farm_", "")
    if cmd not in cmd_map: return
    
    user_id = callback_query.from_user.id
    cmd_name = cmd_map[cmd]
    
    if callback_query.message.chat.type == ChatType.PRIVATE:
        await callback_query.answer("⛔ Фарм только в группах!", show_alert=True)
        return
    
    cd = db.get_cooldown(user_id, cmd_name)
    if cd:
        await callback_query.answer(f"⏳ {cmd_name} на кулдауне!", show_alert=True)
        return
    
    user_data = db.get_user_data(user_id)
    cmd_info = FARM_COMMANDS[cmd_name]
    
    # Расчет награды (аналогично текстовой команде)
    luck = db.get_effective_luck(user_id)
    base_reward = random.randint(cmd_info["min"], cmd_info["max"])
    
    if random.random() < 0.3:
        base_reward = int(base_reward * (1 + (luck - 1.0) * 0.1))
    
    reward = base_reward + user_data['star_power'] * 0.5
    reward *= user_data['productivity']
    if db.check_gold(user_id): reward *= 1.2
    
    if random.random() < 0.26:
        reward += random.randint(5, 15)
    
    reward = round(reward, 2)
    db.update_balance(user_id, reward)
    db.set_cooldown(user_id, cmd_name, 2)
    
    response = (
        f"{cmd_info['emoji']} {cmd_name.upper()} ✅ *ЗАЧЁТ!*\n\n"
        f"💰 *+{reward:.2f} ¢*\n"
        f"💳 Баланс: {db.get_user_data(user_id)['balance']:.2f} ¢"
    )
    
    await callback_query.message.answer(response, parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data in ["buy_star", "buy_prod", "buy_luck", "buy_gold"])
async def buy_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.data
    user_data = db.get_user_data(user_id)
    
    if action == "buy_star":
        if user_data['balance'] >= 100:
            db.update_balance(user_id, -100)
            user_data['star_power'] += 1
            db.save_user_data(user_id, user_data)
            text = "✅ *Сила звёздности +1!*"
        else:
            text = "❌ Недостаточно средств! (100 ¢)"
    
    elif action == "buy_prod":
        if user_data['balance'] >= 150:
            db.update_balance(user_id, -150)
            user_data['productivity'] = round(user_data['productivity'] * 1.1, 2)
            db.save_user_data(user_id, user_data)
            text = f"✅ *Урожайность увеличена!* ({user_data['productivity']})"
        else:
            text = "❌ Недостаточно средств! (150 ¢)"
    
    elif action == "buy_luck":
        if user_data['balance'] >= 200:
            db.update_balance(user_id, -200)
            current_luck = user_data.get('luck', 1.0)
            new_luck = round(current_luck + 0.1, 1)
            db.set_luck(user_id, new_luck)
            text = f"✅ *Удача увеличена!* ({new_luck:.1f}x)"
        else:
            text = "❌ Недостаточно средств! (200 ¢)"
    
    elif action == "buy_gold":
        if user_data['balance'] >= 1500:
            if db.buy_gold(user_id):
                text = "✅ *GOLD подписка активирована!*"
            else:
                text = "❌ Ошибка!"
        else:
            text = "❌ Недостаточно средств! (1500 ¢)"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "start_menu")
async def start_callback(callback_query: CallbackQuery):
    await start_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "profile")
async def profile_callback(callback_query: CallbackQuery):
    await profile_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "shop")
async def shop_callback(callback_query: CallbackQuery):
    await shop_cmd(callback_query.message)
    await callback_query.answer()

# =================== ЭВЕНТЫ ===================
@dp.callback_query(lambda c: c.data == "event_start")
async def event_start_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    global active_event
    if active_event:
        await callback_query.answer("❌ Уже есть активный эвент!", show_alert=True)
        return
    
    if not await is_chat_admin(user_id, chat_id):
        await callback_query.answer("❌ Только админы!", show_alert=True)
        return
    
    if not db.check_gold(user_id):
        await callback_query.answer("❌ Нужна GOLD подписка!", show_alert=True)
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
        'chat_id': chat_id, 'creator': user_id,
        'bonus_value': bonus
    }
    event_participants[event_id] = []
    
    text = f"🎪 *Новый эвент!*\n\n🎯 {etype}\n💰 {reward} ¢\n⏳ 1 час\n\n*Присоединяйтесь!*"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 Присоединиться", callback_data=f"join_event_{event_id}"))
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    event_participants[event_id].append(user_id)
    await callback_query.answer("✅ Эвент запущен!")

@dp.callback_query(lambda c: c.data.startswith("join_event_"))
async def join_event_callback(callback_query: CallbackQuery):
    global active_event
    if not active_event:
        await callback_query.answer("❌ Нет активных эвентов!", show_alert=True)
        return
    
    event_id = int(callback_query.data.replace("join_event_", ""))
    if event_id != active_event['id']:
        await callback_query.answer("❌ Эвент завершен!", show_alert=True)
        return
    
    user_id = callback_query.from_user.id
    if user_id in event_participants.get(active_event['id'], []):
        await callback_query.answer("✅ Вы уже участвуете!", show_alert=True)
        return
    
    event_participants[active_event['id']].append(user_id)
    
    # Бонус удачи для мега эвента
    if active_event.get('bonus_value', 1.0) > 1.0:
        db.set_event_bonus(user_id, active_event['id'], active_event['bonus_value'], active_event['end_time'])
    
    parts = len(event_participants[active_event['id']])
    await callback_query.answer(f"🎉 Вы присоединились! ({parts} участников)", show_alert=True)
    
    text = (
        f"🎪 *Эвент*\n\n"
        f"🎯 {active_event['type']}\n"
        f"💰 {active_event['reward']} ¢\n"
        f"👥 {parts} участников\n"
        f"⏳ {format_time(active_event['end_time'])}"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 Присоединиться", callback_data=f"join_event_{active_event['id']}"))
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

# =================== ПАНЕЛЬ ВЛАДЕЛЬЦА ===================
@dp.message(Command("owner"))
async def owner_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    text = (
        "👑 *Панель владельца*\n\n"
        "💰 *Управление балансами:*\n"
        "/give <id> <сумма> - выдать деньги\n"
        "/set <id> <сумма> - установить баланс\n\n"
        "🎖️ *Управление подписками:*\n"
        "/gold <id> <дни> - выдать GOLD\n"
        "/gold_forever <id> - вечная GOLD\n\n"
        "🍀 *Управление удачей:*\n"
        "/luck <id> <значение> - удача\n"
        "/temp_luck <id> <зн> <мин> - временная\n\n"
        "📢 *Рассылка:*\n"
        "/broadcast <текст> - отправить всем\n\n"
        "🎪 *Эвенты:*\n"
        "/owner_event - запустить эвент"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="refresh_stats"),
        InlineKeyboardButton(text="📋 Список чатов", callback_data="all_chats_list")
    )
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    all_users = db.get_all_users()
    all_chats = db.get_all_chats()
    total_balance = sum(user.get('balance', 0) for user in all_users.values())
    gold_users = sum(1 for user in all_users.values() if user.get('subscription') == 'gold')
    
    text = (
        "📊 *Статистика бота*\n\n"
        f"👥 Пользователей: {len(all_users)}\n"
        f"💬 Чатов: {len(all_chats)}\n"
        f"💰 Общий баланс: {total_balance:.2f} ¢\n"
        f"🎖️ GOLD подписок: {gold_users}\n"
        f"⏰ Активных эвентов: {1 if active_event else 0}"
    )
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("chats"))
async def chats_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    all_chats = db.get_all_chats()
    text = "📋 *Список чатов*\n\n"
    
    for i, (chat_id, chat_data) in enumerate(list(all_chats.items())[:10]):
        title = chat_data.get('title', f"Чат {chat_id}")
        text += f"{i+1}. {title[:30]}\n"
    
    if len(all_chats) > 10:
        text += f"\n...и еще {len(all_chats) - 10} чатов"
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "refresh_stats")
async def refresh_stats_callback(callback_query: CallbackQuery):
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
    await callback_query.answer("✅ Обновлено!")

@dp.callback_query(lambda c: c.data == "all_chats_list")
async def all_chats_list_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    all_chats = db.get_all_chats()
    text = "📋 *Список чатов*\n\n"
    
    for i, (chat_id, chat_data) in enumerate(list(all_chats.items())[:20]):
        title = chat_data.get('title', f"Чат {chat_id}")
        last_active = datetime.fromisoformat(chat_data.get('last_activity', datetime.now().isoformat()))
        delta = datetime.now() - last_active
        if delta.days > 0: ago = f"{delta.days}д"
        elif delta.seconds >= 3600: ago = f"{delta.seconds//3600}ч"
        else: ago = f"{delta.seconds//60}м"
        
        text += f"{i+1}. {title[:25]} ({ago} назад)\n"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")
    await callback_query.answer()

@dp.message(Command("give"))
async def give_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.update_balance(user_id, amount)
        await message.answer(f"✅ Выдано {amount} ¢")
    except:
        await message.answer("❌ Использование: /give <id> <сумма>")

@dp.message(Command("gold"))
async def give_gold(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id = int(args[0])
        days = int(args[1]) if len(args) > 1 else 30
        db.give_gold(user_id, days)
        await message.answer(f"✅ GOLD на {days} дней выдана")
    except:
        await message.answer("❌ Использование: /gold <id> <дни>")

@dp.message(Command("luck"))
async def set_luck_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, luck_value = int(args[0]), float(args[1])
        luck_value = max(1.0, min(100.0, luck_value))
        db.set_luck(user_id, luck_value)
        await message.answer(f"✅ Удача {luck_value:.1f}x установлена")
    except:
        await message.answer("❌ Использование: /luck <id> <значение>")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    
    if not command.args:
        await message.answer("❌ Укажите текст!")
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

# =================== ФОНОВЫЕ ЗАДАЧИ ===================
async def check_events_task():
    """Завершение эвентов"""
    while True:
        global active_event
        if active_event and datetime.now() >= active_event['end_time']:
            eid = active_event['id']
            parts = event_participants.get(eid, [])
            
            if parts:
                reward = active_event['reward']
                for uid in parts:
                    db.update_balance(uid, reward)
                    db.get_user_data(uid)['event_bonus'] = None  # Удаляем бонус
                
                try:
                    await bot.send_message(
                        active_event['chat_id'],
                        f"🎉 *Эвент завершен!*\n\n💰 {reward} ¢ каждому\n👥 {len(parts)} участников",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            active_event = None
            if eid in event_participants:
                del event_participants[eid]
        
        await asyncio.sleep(60)

# =================== ЗАПУСК ===================
async def main():
    print("=" * 50)
    print("🚀 Farm Bot запускается...")
    print(f"👑 Владелец: {OWNER_ID}")
    print(f"📢 Канал: @{CHANNEL_USERNAME}")
    print("=" * 50)
    
    # Фоновая задача
    asyncio.create_task(check_events_task())
    
    try:
        bot_info = await bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
        print("🔄 Ожидание сообщений...")
        
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
