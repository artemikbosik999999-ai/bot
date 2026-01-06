import os
import json
import asyncio
import random
import redis
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatMemberStatus, ChatType

# =================== КОНСТАНТЫ ===================
# Безопасная загрузка из настроек Bothost
OWNER_ID = int(os.environ.get("OWNER_ID", "7119681628"))
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "artem_bori")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Проверка токена
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    print("Добавьте в настройках Bothost:")
    print("BOT_TOKEN = ваш_токен_бота")
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
        # Bothost дает REDIS_URL
        redis_url = os.environ.get("REDIS_URL")
        
        if redis_url:
            try:
                self.redis = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis.ping()
                print("✅ Redis Bothost подключен")
            except Exception as e:
                print(f"⚠️ Redis ошибка: {e}, использую память")
                self.memory_db = {}
                self.redis = None
        else:
            try:
                self.redis = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis.ping()
                print("✅ Локальный Redis подключен")
            except:
                print("⚠️ Redis не найден, использую память")
                self.memory_db = {}
                self.redis = None
    
    def _get_key(self, user_id: int) -> str:
        return f"user:{user_id}"
    
    def get_user_data(self, user_id: int) -> Dict[str, Any]:
        if self.redis:
            data = self.redis.get(self._get_key(user_id))
            return json.loads(data) if data else self._default_user_data()
        else:
            return self.memory_db.get(user_id, self._default_user_data())
    
    def save_user_data(self, user_id: int, data: Dict[str, Any]):
        if self.redis:
            self.redis.set(self._get_key(user_id), json.dumps(data))
        else:
            self.memory_db[user_id] = data
    
    def _default_user_data(self):
        return {
            'balance': 0.0,
            'star_power': 0,
            'productivity': 1.31,
            'luck': 1.0,
            'temp_luck': None,
            'temp_luck_value': None,
            'temp_luck_end': None,
            'subscription': None,
            'subscription_end': None,
            'is_permanent': False,
            'cooldowns': {},
            'total_earned': 0,
            'is_banned': False,
            'channel_check': False,
            'event_bonus': None,  # {event_id: bonus_value, end_time: isoformat}
        }
    
    def update_balance(self, user_id: int, amount: float):
        data = self.get_user_data(user_id)
        data['balance'] = round(data['balance'] + amount, 2)
        if amount > 0:
            data['total_earned'] = round(data.get('total_earned', 0) + amount, 2)
        self.save_user_data(user_id, data)
    
    def set_balance(self, user_id: int, amount: float):
        data = self.get_user_data(user_id)
        data['balance'] = round(amount, 2)
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
            cooldown_end = datetime.fromisoformat(cooldown_str)
            if datetime.now() < cooldown_end:
                return cooldown_end
        return None
    
    def clear_cooldowns(self, user_id: int):
        data = self.get_user_data(user_id)
        data['cooldowns'] = {}
        self.save_user_data(user_id, data)
    
    def buy_gold(self, user_id: int) -> bool:
        """Купить GOLD подписку за 1500 ¢"""
        data = self.get_user_data(user_id)
        if data['balance'] < 1500:
            return False
        data['balance'] = round(data['balance'] - 1500, 2)
        data['subscription'] = 'gold'
        data['subscription_end'] = (datetime.now() + timedelta(days=30)).isoformat()
        self.save_user_data(user_id, data)
        return True
    
    def give_gold(self, user_id: int, days: int = 30, permanent: bool = False):
        """Выдать GOLD подписку"""
        data = self.get_user_data(user_id)
        data['subscription'] = 'gold'
        if permanent:
            data['is_permanent'] = True
            data['subscription_end'] = None
        else:
            data['is_permanent'] = False
            data['subscription_end'] = (datetime.now() + timedelta(days=days)).isoformat()
        self.save_user_data(user_id, data)
    
    def remove_gold(self, user_id: int):
        """Удалить GOLD подписку"""
        data = self.get_user_data(user_id)
        data['subscription'] = None
        data['subscription_end'] = None
        data['is_permanent'] = False
        self.save_user_data(user_id, data)
    
    def check_gold(self, user_id: int) -> bool:
        """Проверить активна ли GOLD подписка"""
        data = self.get_user_data(user_id)
        if data.get('subscription') != 'gold':
            return False
        if data.get('is_permanent'):
            return True
        sub_end = data.get('subscription_end')
        if sub_end:
            return datetime.now() < datetime.fromisoformat(sub_end)
        return False
    
    def set_luck(self, user_id: int, luck: float):
        """Установить постоянную удачу пользователю (1.0 - 100.0)"""
        data = self.get_user_data(user_id)
        # Ограничиваем удачу от 1.0 до 100.0
        luck = max(1.0, min(100.0, luck))
        data['luck'] = round(luck, 2)
        self.save_user_data(user_id, data)
    
    def get_effective_luck(self, user_id: int) -> float:
        """Получить эффективную удачу (постоянную + временную + бонус эвента)"""
        data = self.get_user_data(user_id)
        base_luck = data.get('luck', 1.0)
        
        # Проверяем временную удачу
        if data.get('temp_luck') and data.get('temp_luck_end'):
            temp_end = datetime.fromisoformat(data['temp_luck_end'])
            if datetime.now() < temp_end:
                temp_luck = data.get('temp_luck_value', 1.0)
                base_luck = max(base_luck, temp_luck)  # Берем максимальную удачу
        
        # Проверяем бонус от эвента
        event_bonus = data.get('event_bonus')
        if event_bonus and event_bonus.get('end_time'):
            bonus_end = datetime.fromisoformat(event_bonus['end_time'])
            if datetime.now() < bonus_end:
                # Бонус умножается на базовую удачу
                bonus_value = event_bonus.get('value', 1.0)
                base_luck = round(base_luck * bonus_value, 2)
        
        return base_luck
    
    def set_temp_luck(self, user_id: int, luck: float, minutes: int = 5):
        """Установить временную удачу на N минут"""
        data = self.get_user_data(user_id)
        luck = max(1.0, min(100.0, luck))
        data['temp_luck'] = True
        data['temp_luck_value'] = round(luck, 2)
        data['temp_luck_end'] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        self.save_user_data(user_id, data)
    
    def remove_temp_luck(self, user_id: int):
        """Удалить временную удачу"""
        data = self.get_user_data(user_id)
        data['temp_luck'] = None
        data['temp_luck_value'] = None
        data['temp_luck_end'] = None
        self.save_user_data(user_id, data)
    
    def get_temp_luck_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о временной удаче"""
        data = self.get_user_data(user_id)
        if data.get('temp_luck') and data.get('temp_luck_end'):
            end_time = datetime.fromisoformat(data['temp_luck_end'])
            if datetime.now() < end_time:
                return {
                    'value': data['temp_luck_value'],
                    'end_time': end_time
                }
        return None
    
    def set_event_bonus(self, user_id: int, event_id: int, bonus_value: float, end_time: datetime):
        """Установить бонус от эвента"""
        data = self.get_user_data(user_id)
        data['event_bonus'] = {
            'event_id': event_id,
            'value': bonus_value,
            'end_time': end_time.isoformat()
        }
        self.save_user_data(user_id, data)
    
    def remove_event_bonus(self, user_id: int):
        """Удалить бонус от эвента"""
        data = self.get_user_data(user_id)
        data['event_bonus'] = None
        self.save_user_data(user_id, data)
    
    def get_event_bonus_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о бонусе от эвента"""
        data = self.get_user_data(user_id)
        event_bonus = data.get('event_bonus')
        if event_bonus and event_bonus.get('end_time'):
            end_time = datetime.fromisoformat(event_bonus['end_time'])
            if datetime.now() < end_time:
                return {
                    'event_id': event_bonus['event_id'],
                    'value': event_bonus['value'],
                    'end_time': end_time
                }
        return None
    
    def has_active_event_bonus(self, user_id: int) -> bool:
        """Проверить есть ли активный бонус от эвента"""
        return self.get_event_bonus_info(user_id) is not None
    
    def set_luck_all(self, luck: float):
        """Установить удачу ВСЕМ пользователям"""
        users = self.get_all_users()
        for user_id, data in users.items():
            data['luck'] = max(1.0, min(100.0, luck))
            self.save_user_data(user_id, data)
        return len(users)
    
    def remove_luck_all(self):
        """Сбросить удачу у ВСЕХ пользователей до 1.0"""
        users = self.get_all_users()
        for user_id, data in users.items():
            data['luck'] = 1.0
            data['temp_luck'] = None
            data['temp_luck_value'] = None
            data['temp_luck_end'] = None
            data['event_bonus'] = None
            self.save_user_data(user_id, data)
        return len(users)
    
    def get_user_luck_info(self, user_id: int) -> Dict[str, Any]:
        """Получить полную информацию об удаче пользователя"""
        data = self.get_user_data(user_id)
        temp_info = self.get_temp_luck_info(user_id)
        event_bonus_info = self.get_event_bonus_info(user_id)
        
        info = {
            'base_luck': data.get('luck', 1.0),
            'has_temp_luck': False,
            'temp_luck_value': None,
            'temp_luck_end': None,
            'has_event_bonus': False,
            'event_bonus_value': None,
            'event_bonus_end': None,
            'effective_luck': self.get_effective_luck(user_id)
        }
        
        if temp_info:
            info.update({
                'has_temp_luck': True,
                'temp_luck_value': temp_info['value'],
                'temp_luck_end': temp_info['end_time']
            })
        
        if event_bonus_info:
            info.update({
                'has_event_bonus': True,
                'event_bonus_value': event_bonus_info['value'],
                'event_bonus_end': event_bonus_info['end_time']
            })
        
        return info
    
    def set_channel_check(self, user_id: int, passed: bool = True):
        data = self.get_user_data(user_id)
        data['channel_check'] = passed
        self.save_user_data(user_id, data)
    
    def get_channel_check(self, user_id: int) -> bool:
        return self.get_user_data(user_id).get('channel_check', False)
    
    def ban_user(self, user_id: int, ban: bool = True):
        data = self.get_user_data(user_id)
        data['is_banned'] = ban
        self.save_user_data(user_id, data)
    
    def is_banned(self, user_id: int) -> bool:
        return self.get_user_data(user_id).get('is_banned', False)
    
    def get_all_users(self):
        if self.redis:
            users = {}
            for key in self.redis.keys("user:*"):
                user_id = int(key.split(":")[1])
                users[user_id] = json.loads(self.redis.get(key))
            return users
        else:
            return self.memory_db.copy()

# =================== ИНИЦИАЛИЗАЦИЯ ===================
db = Database()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
active_event = None
event_participants = {}

# =================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===================
async def is_chat_admin(user_id: int, chat_id: int) -> bool:
    if chat_id > 0:  # Личные сообщения
        return False
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
    if not end_time:
        return "∞ (вечная)"
    if datetime.now() >= end_time:
        return "истекла"
    delta = end_time - datetime.now()
    
    if delta.days > 0:
        return f"{delta.days}д {delta.seconds//3600}ч"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return f"{hours}ч {minutes}м"
    else:
        minutes = delta.seconds // 60
        seconds = delta.seconds % 60
        return f"{minutes}м {seconds}с"

def format_minutes(minutes: int) -> str:
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}ч {mins}м"
    return f"{minutes}м"

def get_sub_status(user_data: dict) -> str:
    if user_data.get('subscription') != 'gold':
        return "⭕ Нет подписки"
    if user_data.get('is_permanent'):
        return "✨ GOLD ∞ (вечная)"
    sub_end = user_data.get('subscription_end')
    if sub_end:
        end = datetime.fromisoformat(sub_end)
        if datetime.now() < end:
            days = (end - datetime.now()).days
            return f"✨ GOLD ({days} дней)"
    return "⭕ Подписка истекла"

# =================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ===================
@dp.message(Command("check"))
async def check_channel(message: Message):
    text = (
        "🔒 *Для работы бота нужна подписка на канал разработчика*\n\n"
        "📢 Подпишись на канал и нажми '✅ ПРОВЕРИТЬ'"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=f"https://t.me/{CHANNEL_USERNAME}"))
    keyboard.row(InlineKeyboardButton(text="✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="verify_sub"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "verify_sub")
async def verify_sub_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if await check_channel_subscription(user_id):
        db.set_channel_check(user_id, True)
        
        # После проверки показываем приветствие с кнопкой добавления в группу
        text = (
            "✅ *Подписка подтверждена!*\n\n"
            "🤖 *Привет! Я Фермер Бот!*\n\n"
            "💎 *Добавь меня в группу и становись богачом!*\n\n"
            "💰 *Что я умею:*\n"
            "• 5 фарм-команд\n"
            "• Магазин улучшений\n"
            "• Эвенты с наградами\n"
            "• Система удачи\n"
            "• GOLD подписка\n\n"
            "🚀 *Нажми кнопку ниже чтобы добавить бота в группу:*"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="➕ ДОБАВИТЬ БОТА В ГРУППУ", url="https://t.me/farmirobot?startgroup=true"))
        keyboard.row(
            InlineKeyboardButton(text="🚀 НАЧАТЬ", callback_data="start_menu"),
            InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help_menu")
        )
        
        await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    else:
        text = (
            "❌ *Вы не подписаны!*\n\n"
            "📢 *Подпишитесь на канал:* @artem_bori\n"
            "*и нажмите '🔄 ПРОВЕРИТЬ' снова*"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=f"https://t.me/{CHANNEL_USERNAME}"))
        keyboard.row(InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ", callback_data="verify_sub"))
        
        await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    
    await callback_query.answer()

# =================== ОСНОВНЫЕ КОМАНДЫ ===================
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    
    if db.is_banned(user_id):
        await message.answer("⛔ Вы забанены!")
        return
    
    # Проверяем, что это не личные сообщения
    if message.chat.type == ChatType.PRIVATE:
        # В личных сообщениях показываем приветствие с кнопкой добавления в группу
        text = (
            "🤖 *Привет! Я Фермер Бот!*\n\n"
            "📢 *Для начала работы:*\n"
            "1️⃣ Подпишись на канал разработчика\n"
            "2️⃣ Добавь меня в группу\n"
            "3️⃣ Становись богачом! 💰\n\n"
            "🚀 *Бот работает только в группах и чатах!*"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=f"https://t.me/{CHANNEL_USERNAME}"))
        keyboard.row(InlineKeyboardButton(text="➕ ДОБАВИТЬ БОТА В ГРУППУ", url="https://t.me/farmirobot?startgroup=true"))
        
        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
        return
    
    # В группах проверяем подписку
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await check_channel(message)
        return
    
    user_data = db.get_user_data(user_id)
    luck_info = db.get_user_luck_info(user_id)
    
    # Главное меню с кнопками
    text = (
        f"🎮 *Farm Bot*\n\n"
        f"💰 *Баланс:* {user_data['balance']:.2f} ¢\n"
        f"✨ *Сила:* {user_data['star_power']}\n"
        f"⏳ *Урожайность:* {user_data['productivity']:.2f}\n"
        f"🍀 *Удача:* {luck_info['effective_luck']:.1f}x\n\n"
        "🌵 *Фарм команды:*\n"
        "кактус ферма шахта сад охота\n"
        "(кулдаун 2 часа)"
    )
    
    # Добавляем информацию о бонусе эвента
    if luck_info.get('has_event_bonus'):
        time_left = format_time(luck_info['event_bonus_end'])
        text += f"\n\n✨ *Активен бонус от эвента: +{(luck_info['event_bonus_value'] - 1) * 100:.0f}% к удаче!*\n⏳ *Осталось:* {time_left}"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="📊 Профиль", callback_data="profile"),
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")
    )
    keyboard.row(
        InlineKeyboardButton(text="🎪 Эвенты", callback_data="events"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")
    )
    
    # Кнопка только для владельца
    if user_id == OWNER_ID:
        keyboard.row(InlineKeyboardButton(text="👑 Панель владельца", callback_data="owner_panel"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, что это не личные сообщения
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("🤖 Профиль доступен только в группах и чатах!")
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь на канал! /check")
        return
    
    user_data = db.get_user_data(user_id)
    luck_info = db.get_user_luck_info(user_id)
    sub_status = get_sub_status(user_data)
    
    # Формируем информацию об удаче
    luck_text = f"🍀 *Удача:* {luck_info['effective_luck']:.1f}x"
    
    if luck_info['has_temp_luck']:
        time_left = format_time(luck_info['temp_luck_end'])
        luck_text += f" (временная {luck_info['temp_luck_value']:.1f}x, осталось: {time_left})"
    
    if luck_info.get('has_event_bonus'):
        bonus_percent = (luck_info['event_bonus_value'] - 1) * 100
        time_left = format_time(luck_info['event_bonus_end'])
        luck_text += f"\n✨ *Бонус от эвента:* +{bonus_percent:.0f}% к удаче\n⏳ *Осталось:* {time_left}"
    
    text = (
        f"📊 *Профиль*\n\n"
        f"💰 *Баланс:* {user_data['balance']:.2f} ¢\n"
        f"✨ *Сила:* {user_data['star_power']}\n"
        f"⏳ *Урожайность:* {user_data['productivity']:.2f}\n"
        f"{luck_text}\n"
        f"🎖️ *Подписка:* {sub_status}\n"
        f"📢 *Канал:* {'✅' if db.get_channel_check(user_id) else '❌'}\n\n"
        "⏰ *Кулдауны:*\n"
    )
    
    for cmd in FARM_COMMANDS:
        cd = db.get_cooldown(user_id, cmd)
        if cd:
            text += f"• {cmd}: {format_time(cd)}\n"
        else:
            text += f"• {cmd}: ✅ готово\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🌵 Кактус", callback_data="farm_cactus"),
        InlineKeyboardButton(text="🚜 Ферма", callback_data="farm_farm"),
        InlineKeyboardButton(text="⛏️ Шахта", callback_data="farm_mine")
    )
    keyboard.row(
        InlineKeyboardButton(text="🌻 Сад", callback_data="farm_garden"),
        InlineKeyboardButton(text="🏹 Охота", callback_data="farm_hunt")
    )
    keyboard.row(
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="🎪 Эвенты", callback_data="events")
    )
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu"))
    
    is_admin = await is_chat_admin(user_id, message.chat.id)
    if is_admin and db.check_gold(user_id):
        keyboard.row(InlineKeyboardButton(text="🚀 Запустить эвент", callback_data="event_start"))
    
    # Кнопка панели только для владельца
    if user_id == OWNER_ID:
        keyboard.row(InlineKeyboardButton(text="👑 Панель владельца", callback_data="owner_panel"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("shop"))
async def shop_cmd(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, что это не личные сообщения
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("🤖 Магазин доступен только в группах и чатах!")
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь! /check")
        return
    
    user_data = db.get_user_data(user_id)
    has_gold = db.check_gold(user_id)
    luck_info = db.get_user_luck_info(user_id)
    
    text = (
        "🛒 *Магазин*\n\n"
        "✨ *Сила звёздности (100 ¢)*\n"
        "+0.5 ¢ к каждой награде\n\n"
        "⏳ *Урожайность (150 ¢)*\n"
        "×1.1 к наградам\n\n"
        "🍀 *Удача (200 ¢)*\n"
        "+0.1x к удаче\n\n"
        "🎖️ *GOLD подписка (1500 ¢)*\n"
        "+20% к наградам на 30 дней\n"
    )
    
    if has_gold:
        text += f"• У вас: {get_sub_status(user_data)}\n"
    
    text += f"\n💰 *Ваш баланс:* {user_data['balance']:.2f} ¢"
    text += f"\n🍀 *Текущая удача:* {luck_info['effective_luck']:.1f}x"
    
    # Добавляем информацию о бонусе эвента
    if luck_info.get('has_event_bonus'):
        bonus_percent = (luck_info['event_bonus_value'] - 1) * 100
        time_left = format_time(luck_info['event_bonus_end'])
        text += f"\n\n✨ *У вас активен бонус от эвента: +{bonus_percent:.0f}% к удаче!*\n⏳ *Осталось:* {time_left}"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✨ Сила +1", callback_data="buy_star"),
        InlineKeyboardButton(text="⏳ Урожайность", callback_data="buy_prod")
    )
    keyboard.row(
        InlineKeyboardButton(text="🍀 Удача +0.1", callback_data="buy_luck"),
        InlineKeyboardButton(text="🎖️ " + ("Продлить GOLD" if has_gold else "Купить GOLD"), callback_data="buy_gold")
    )
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("events"))
async def events_cmd(message: Message):
    user_id = message.from_user.id
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь! /check")
        return
    
    global active_event
    
    text = "🎪 *Эвенты*\n\n"
    
    if active_event:
        parts = len(event_participants.get(active_event['id'], []))
        time_left = format_time(active_event['end_time'])
        text += (
            f"🚀 *Активный эвент!*\n"
            f"🎯 *{active_event['type']}*\n"
            f"💰 *{active_event['reward']} ¢*\n"
        )
        
        # Добавляем описание особенностей для мега эвента
        if "Мега" in active_event['type']:
            bonus_value = active_event.get('bonus_value', 1.2)
            bonus_percent = (bonus_value - 1) * 100
            text += f"✨ *Особенность:* Участники получают +{bonus_percent:.0f}% к удаче до конца эвента!\n"
        
        text += f"👥 *{parts} участников*\n"
        text += f"⏳ *{time_left}*\n\n"
        text += f"🆔 *ID:* {active_event['id']}"
    else:
        text += (
            "📭 *Нет активных эвентов*\n\n"
            "✨ *Как запустить:*\n"
            "1. GOLD подписка\n"
            "2. Быть админом чата\n"
            "3. Нажать 'Запустить эвент'\n\n"
            "💰 *Награды:*\n"
            "• 🎯 Обычный: 100-300 ¢\n"
            "• 🚀 Средний: 300-600 ¢\n"
            "• 💎 Мега: 600-1000 ¢ + бонус удачи!"
        )
    
    keyboard = InlineKeyboardBuilder()
    
    if active_event:
        keyboard.row(InlineKeyboardButton(text="🎪 Присоединиться", callback_data=f"join_event_{active_event['id']}"))
    else:
        is_admin = await is_chat_admin(user_id, message.chat.id)
        if is_admin and db.check_gold(user_id):
            keyboard.row(InlineKeyboardButton(text="🚀 Запустить эвент", callback_data="event_start"))
    
    keyboard.row(InlineKeyboardButton(text="📊 Профиль", callback_data="profile"))
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        "❓ *Помощь*\n\n"
        "🌵 *Фарм команды:*\n"
        "кактус, ферма, шахта, сад, охота\n"
        "(кулдаун 2 часа)\n\n"
        "📋 *Основные команды:*\n"
        "/start - начало\n"
        "/profile - профиль\n"
        "/shop - магазин\n"
        "/events - эвенты\n"
        "/check - подписка на канал\n\n"
        "🎪 *Эвенты:*\n"
        "Запускают админы с GOLD\n"
        "Участвовать может любой\n"
        "💎 *Мега эвент даёт +20% к удаче до конца эвента!*\n\n"
        "🎖️ *GOLD подписка:*\n"
        "+20% к наградам\n"
        "1500 ¢ / 30 дней\n\n"
        "🍀 *Удача:*\n"
        "Влияет на размер наград\n"
        "Можно купить в магазине\n"
        "Можно получить от эвентов"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🚀 Начать", callback_data="start_menu"),
        InlineKeyboardButton(text="📊 Профиль", callback_data="profile")
    )
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

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
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="💰 Выдать деньги", callback_data="owner_give"),
        InlineKeyboardButton(text="🎖️ Выдать GOLD", callback_data="owner_gold")
    )
    keyboard.row(
        InlineKeyboardButton(text="🍀 Управление удачей", callback_data="owner_luck_menu"),
        InlineKeyboardButton(text="📢 Рассылка", callback_data="owner_broadcast")
    )
    keyboard.row(
        InlineKeyboardButton(text="⛔ Забанить", callback_data="owner_ban"),
        InlineKeyboardButton(text="✅ Разбанить", callback_data="owner_unban")
    )
    keyboard.row(
        InlineKeyboardButton(text="🎪 Эвент", callback_data="owner_event"),
        InlineKeyboardButton(text="🔄 Сбросить кд", callback_data="owner_resetcd")
    )
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@dp.message(Command("give"))
async def give_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.update_balance(user_id, amount)
        new = db.get_user_data(user_id)['balance']
        await message.answer(f"✅ Выдано {amount} ¢\nНовый баланс: {new} ¢")
    except:
        await message.answer("❌ Ошибка! Использование: /give <id> <сумма>")

@dp.message(Command("set"))
async def set_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.set_balance(user_id, amount)
        await message.answer(f"✅ Баланс установлен: {amount} ¢")
    except:
        await message.answer("❌ Ошибка! Использование: /set <id> <сумма>")

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
        await message.answer("❌ Ошибка! Использование: /gold <id> <дни>")

@dp.message(Command("gold_forever"))
async def gold_forever(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.give_gold(user_id, permanent=True)
        await message.answer(f"✅ Вечная GOLD выдана")
    except:
        await message.answer("❌ Ошибка! Использование: /gold_forever <id>")

@dp.message(Command("remove_gold"))
async def remove_gold_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.remove_gold(user_id)
        await message.answer(f"✅ GOLD удалена")
    except:
        await message.answer("❌ Ошибка! Использование: /remove_gold <id>")

@dp.message(Command("ban"))
async def ban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.ban_user(user_id, True)
        await message.answer(f"⛔ Пользователь забанен")
    except:
        await message.answer("❌ Ошибка! Использование: /ban <id>")

@dp.message(Command("unban"))
async def unban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.ban_user(user_id, False)
        await message.answer(f"✅ Пользователь разбанен")
    except:
        await message.answer("❌ Ошибка! Использование: /unban <id>")

@dp.message(Command("resetcd"))
async def reset_cd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.clear_cooldowns(user_id)
        await message.answer(f"✅ Кулдауны сброшены")
    except:
        await message.answer("❌ Ошибка! Использование: /resetcd <id>")

# =================== УПРАВЛЕНИЕ УДАЧЕЙ ===================
@dp.message(Command("luck"))
async def set_luck_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id = int(args[0])
        luck_value = float(args[1])
        
        if luck_value < 1.0 or luck_value > 100.0:
            await message.answer("❌ Удача должна быть от 1.0 до 100.0!")
            return
            
        db.set_luck(user_id, luck_value)
        await message.answer(f"✅ Постоянная удача установлена: {luck_value:.1f}x\nДля пользователя: {user_id}")
    except:
        await message.answer("❌ Ошибка! Использование: /luck <id> <значение> (1.0-100.0)")

@dp.message(Command("temp_luck"))
async def set_temp_luck_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id = int(args[0])
        luck_value = float(args[1])
        minutes = int(args[2]) if len(args) > 2 else 5
        
        if luck_value < 1.0 or luck_value > 100.0:
            await message.answer("❌ Удача должна быть от 1.0 до 100.0!")
            return
            
        if minutes < 1 or minutes > 1440:
            await message.answer("❌ Минуты должны быть от 1 до 1440 (24 часа)!")
            return
        
        db.set_temp_luck(user_id, luck_value, minutes)
        
        luck_info = db.get_user_luck_info(user_id)
        base_luck = luck_info['base_luck']
        effective_luck = luck_info['effective_luck']
        
        await message.answer(
            f"✅ Временная удача установлена!\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"🍀 Удача: {luck_value:.1f}x\n"
            f"⏳ Длительность: {format_minutes(minutes)}\n"
            f"📊 Базовая удача: {base_luck:.1f}x\n"
            f"🎯 Эффективная удача: {effective_luck:.1f}x"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка! Использование: /temp_luck <id> <значение> [минуты]\nПример: /temp_luck 123456789 10.0 5")

@dp.message(Command("luck_all"))
async def set_luck_all_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        if not command.args:
            await message.answer("❌ Укажите значение удачи!\n/luck_all <значение>")
            return
        
        luck_value = float(command.args)
        
        if luck_value < 1.0 or luck_value > 100.0:
            await message.answer("❌ Удача должна быть от 1.0 до 100.0!")
            return
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(text="✅ Да, установить всем", callback_data=f"luck_all_confirm_{luck_value}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="owner_panel")
        )
        
        await message.answer(
            f"⚠️ *ВНИМАНИЕ!*\n\n"
            f"Вы собираетесь установить удачу {luck_value:.1f}x ВСЕМ пользователям.\n\n"
            f"❓ Подтвердить действие?",
            reply_markup=keyboard.as_markup()
        )
    except:
        await message.answer("❌ Ошибка! Использование: /luck_all <значение> (1.0-100.0)")

@dp.message(Command("luck_reset_all"))
async def reset_luck_all_cmd(message: Message):
    if message.from_user.id != OWNER_ID: return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Да, сбросить всем", callback_data="luck_reset_all_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="owner_panel")
    )
    
    await message.answer(
        f"⚠️ *ВНИМАНИЕ!*\n\n"
        f"Вы собираетесь сбросить удачу у ВСЕХ пользователей до 1.0x.\n\n"
        f"❓ Подтвердить действие?",
        reply_markup=keyboard.as_markup()
    )

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    
    if not command.args:
        await message.answer("❌ Укажите текст для рассылки!\n/broadcast <текст>")
        return
    
    broadcast_text = command.args
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Да, отправить всем", callback_data=f"broadcast_confirm_{message.message_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="owner_panel")
    )
    
    await message.answer(
        f"📢 *Рассылка для всех пользователей:*\n\n"
        f"{broadcast_text}\n\n"
        f"❓ Отправить всем пользователям?",
        reply_markup=keyboard.as_markup()
    )

# =================== ЭВЕНТЫ ===================
@dp.message(Command("event_start"))
async def event_start_cmd(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь! /check")
        return
    
    if not await is_chat_admin(user_id, chat_id):
        await message.answer("❌ Только админы чата!")
        return
    
    if not db.check_gold(user_id):
        await message.answer("❌ Нужна GOLD подписка! /shop")
        return
    
    global active_event
    if active_event:
        await message.answer("❌ Уже есть активный эвент!")
        return
    
    event_types = [
        ("🎯 Обычный", 100, 300, "Обычный эвент", 1.0),  # Без бонуса
        ("🚀 Средний", 300, 600, "Средний эвент", 1.0), # Без бонуса
        ("💎 Мега", 600, 1000, "Мега эвент с бонусом удачи!", 1.2)  # +20% бонус
    ]
    etype, emin, emax, edesc, bonus_value = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    end_time = datetime.now() + timedelta(hours=1)
    
    active_event = {
        'id': event_id,
        'type': etype,
        'reward': reward,
        'end_time': end_time,
        'chat_id': chat_id,
        'creator': user_id,
        'description': edesc,
        'bonus_value': bonus_value
    }
    event_participants[event_id] = []
    
    text = (
        f"🎪 *Новый эвент!*\n\n"
        f"🎯 *{etype}*\n"
        f"💰 *{reward} ¢*\n"
        f"⏳ *1 час*\n"
        f"📝 *{edesc}*\n"
        f"🆔 *{event_id}*\n\n"
        f"*Присоединиться:* нажмите кнопку ниже"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_event_{event_id}"))
    
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    event_participants[event_id].append(user_id)

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
        ("🎯 Обычный", 100, 300, "Обычный эвент", 1.0),
        ("🚀 Средний", 300, 600, "Средний эвент", 1.0),
        ("💎 Мега", 600, 1000, "Мега эвент с бонусом удачи!", 1.2)
    ]
    etype, emin, emax, edesc, bonus_value = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    end_time = datetime.now() + timedelta(hours=1)
    
    active_event = {
        'id': event_id,
        'type': etype,
        'reward': reward,
        'end_time': end_time,
        'chat_id': message.chat.id,
        'creator': OWNER_ID,
        'description': edesc,
        'bonus_value': bonus_value
    }
    event_participants[event_id] = []
    
    text = (
        f"🎪 *Владелец запустил эвент!*\n\n"
        f"🎯 *{etype}*\n"
        f"💰 *{reward} ¢*\n"
        f"⏳ *1 час*\n"
        f"📝 *{edesc}*\n"
        f"🆔 *{event_id}*\n\n"
        f"*Присоединиться:* нажмите кнопку ниже"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_event_{event_id}"))
    
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

@dp.message(Command("join"))
async def join_event_cmd(message: Message, command: CommandObject):
    global active_event
    
    if not active_event:
        await message.answer("❌ Нет активных эвентов!")
        return
    
    if not command.args:
        await message.answer(f"Использование: /join {active_event['id']}")
        return
    
    if int(command.args) != active_event['id']:
        await message.answer("❌ Неверный ID эвента!")
        return
    
    user_id = message.from_user.id
    
    if active_event['creator'] != OWNER_ID and active_event.get('chat_id') != message.chat.id:
        await message.answer("❌ Этот эвент в другом чате!")
        return
    
    if user_id in event_participants.get(active_event['id'], []):
        await message.answer("✅ Вы уже участвуете!")
        return
    
    event_participants[active_event['id']].append(user_id)
    parts = len(event_participants[active_event['id']])
    time_left = format_time(active_event['end_time'])
    
    # Если это эвент с бонусом, даём бонус удачи до конца эвента
    bonus_value = active_event.get('bonus_value', 1.0)
    if bonus_value > 1.0:
        db.set_event_bonus(user_id, active_event['id'], bonus_value, active_event['end_time'])
        bonus_percent = (bonus_value - 1) * 100
        bonus_text = f"\n✨ *Вы получили бонус: +{bonus_percent:.0f}% к удаче до конца эвента!*"
    else:
        bonus_text = ""
    
    await message.answer(
        f"🎉 *Вы присоединились!*\n\n"
        f"🎯 *{active_event['type']}*\n"
        f"💰 *{active_event['reward']} ¢*\n"
        f"👥 *{parts} участников*\n"
        f"⏳ *{time_left}*"
        f"{bonus_text}"
    )

# =================== ФАРМ КОМАНДЫ ===================
@dp.message(lambda msg: msg.text and msg.text.lower() in FARM_COMMANDS)
async def farm_command(message: Message):
    user_id = message.from_user.id
    cmd = message.text.lower()
    
    # НЕЛЬЗЯ ФАРМИТЬ В ЛИЧНЫХ СООБЩЕНИЯХ
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("⛔ Фарм доступен только в группах и чатах!\n\nСоздайте группу и добавьте бота туда.")
        return
    
    if db.is_banned(user_id):
        await message.answer("⛔ Вы забанены!")
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь на канал! /check")
        return
    
    cd = db.get_cooldown(user_id, cmd)
    if cd:
        await message.reply(f"⏳ {cmd} на кулдауне!\n\nВозвращайтесь через {format_time(cd)}")
        return
    
    user_data = db.get_user_data(user_id)
    cmd_info = FARM_COMMANDS[cmd]
    
    effective_luck = db.get_effective_luck(user_id)
    base_luck = user_data.get('luck', 1.0)
    temp_luck_info = db.get_temp_luck_info(user_id)
    event_bonus_info = db.get_event_bonus_info(user_id)
    
    base_min = cmd_info["min"]
    base_max = cmd_info["max"]
    
    luck_multiplier = 1.0 + (effective_luck - 1.0) * 0.1
    
    if random.random() < 0.3:
        reward = random.randint(base_min, int(base_max * luck_multiplier))
        luck_used = True
    else:
        reward = random.randint(base_min, base_max)
        luck_used = False
    
    reward += user_data['star_power'] * 0.5
    reward *= user_data['productivity']
    
    if db.check_gold(user_id):
        reward *= 1.2
    
    if random.random() < 0.26:
        bonus = random.randint(5, 15)
        reward += bonus
        bonus_text = f"☢️ +{bonus} ¢\n"
    else:
        bonus_text = ""
    
    reward = round(reward, 2)
    
    db.update_balance(user_id, reward)
    db.set_cooldown(user_id, cmd, hours=2)
    
    new_balance = db.get_user_data(user_id)['balance']
    
    luck_text = ""
    if luck_used:
        luck_text = f"🍀 Удача {effective_luck:.1f}x помогла!\n"
        
        if temp_luck_info and effective_luck > base_luck:
            time_left = format_time(temp_luck_info['end_time'])
            luck_text += f"⏳ Временная удача закончится через: {time_left}\n"
        
        if event_bonus_info:
            bonus_percent = (event_bonus_info['value'] - 1) * 100
            time_left = format_time(event_bonus_info['end_time'])
            luck_text += f"✨ Бонус от эвента: +{bonus_percent:.0f}% к удаче!\n⏳ Осталось: {time_left}\n"
    
    response = (
        f"{cmd_info['emoji']} {cmd.upper()} ✅ *ЗАЧЁТ!*\n\n"
        f"{luck_text}"
        f"💰 *+{reward:.2f} ¢*\n"
        f"{bonus_text}"
        f"\n💳 *Баланс:* {new_balance:.2f} ¢\n\n"
        f"⏳ *Возвращайтесь через 2 часа*"
    )
    
    await message.reply(response, parse_mode="Markdown")

# =================== CALLBACK ОБРАБОТЧИКИ ===================
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

@dp.callback_query(lambda c: c.data == "events")
async def events_callback(callback_query: CallbackQuery):
    await events_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "help_menu")
async def help_callback(callback_query: CallbackQuery):
    await help_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "owner_panel")
async def owner_panel_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await owner_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("farm_"))
async def farm_button_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    cmd = callback_query.data.replace("farm_", "")
    
    if callback_query.message.chat.type == ChatType.PRIVATE:
        await callback_query.answer("⛔ Фарм доступен только в группах!", show_alert=True)
        return
    
    cmd_map = {
        "cactus": "кактус",
        "farm": "ферма",
        "mine": "шахта",
        "garden": "сад",
        "hunt": "охота"
    }
    
    if cmd not in cmd_map:
        await callback_query.answer("❌ Неизвестная команда")
        return
    
    cmd_name = cmd_map[cmd]
    
    if db.is_banned(user_id):
        await callback_query.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await callback_query.answer("❌ Сначала подпишитесь на канал!", show_alert=True)
        return
    
    cd = db.get_cooldown(user_id, cmd_name)
    if cd:
        await callback_query.answer(f"⏳ {cmd_name} на кулдауне! {format_time(cd)}", show_alert=True)
        return
    
    user_data = db.get_user_data(user_id)
    cmd_info = FARM_COMMANDS[cmd_name]
    
    effective_luck = db.get_effective_luck(user_id)
    base_luck = user_data.get('luck', 1.0)
    temp_luck_info = db.get_temp_luck_info(user_id)
    event_bonus_info = db.get_event_bonus_info(user_id)
    
    base_min = cmd_info["min"]
    base_max = cmd_info["max"]
    
    luck_multiplier = 1.0 + (effective_luck - 1.0) * 0.1
    
    if random.random() < 0.3:
        reward = random.randint(base_min, int(base_max * luck_multiplier))
        luck_used = True
    else:
        reward = random.randint(base_min, base_max)
        luck_used = False
    
    reward += user_data['star_power'] * 0.5
    reward *= user_data['productivity']
    
    if db.check_gold(user_id):
        reward *= 1.2
    
    if random.random() < 0.26:
        bonus = random.randint(5, 15)
        reward += bonus
        bonus_text = f"☢️ +{bonus} ¢\n"
    else:
        bonus_text = ""
    
    reward = round(reward, 2)
    
    db.update_balance(user_id, reward)
    db.set_cooldown(user_id, cmd_name, hours=2)
    
    new_balance = db.get_user_data(user_id)['balance']
    
    luck_text = ""
    if luck_used:
        luck_text = f"🍀 Удача {effective_luck:.1f}x помогла!\n"
        
        if temp_luck_info and effective_luck > base_luck:
            time_left = format_time(temp_luck_info['end_time'])
            luck_text += f"⏳ Временная удача закончится через: {time_left}\n"
        
        if event_bonus_info:
            bonus_percent = (event_bonus_info['value'] - 1) * 100
            time_left = format_time(event_bonus_info['end_time'])
            luck_text += f"✨ Бонус от эвента: +{bonus_percent:.0f}% к удаче!\n⏳ Осталось: {time_left}\n"
    
    response = (
        f"{cmd_info['emoji']} {cmd_name.upper()} ✅ *ЗАЧЁТ!*\n\n"
        f"{luck_text}"
        f"💰 *+{reward:.2f} ¢*\n"
        f"{bonus_text}"
        f"\n💳 *Баланс:* {new_balance:.2f} ¢\n\n"
        f"⏳ *Возвращайтесь через 2 часа*"
    )
    
    await callback_query.message.answer(response, parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data in ["buy_star", "buy_prod", "buy_luck", "buy_gold"])
async def buy_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.data
    
    if action == "buy_star":
        user_data = db.get_user_data(user_id)
        if user_data['balance'] >= 100:
            db.update_balance(user_id, -100)
            user_data['star_power'] += 1
            db.save_user_data(user_id, user_data)
            text = "✅ *Сила звёздности +1!*\n\nТеперь +0.5 ¢ к каждой награде!"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 100 ¢"
    
    elif action == "buy_prod":
        user_data = db.get_user_data(user_id)
        if user_data['balance'] >= 150:
            db.update_balance(user_id, -150)
            user_data['productivity'] = round(user_data['productivity'] * 1.1, 2)
            db.save_user_data(user_id, user_data)
            text = f"✅ *Урожайность увеличена!*\n\nТеперь: {user_data['productivity']}"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 150 ¢"
    
    elif action == "buy_luck":
        user_data = db.get_user_data(user_id)
        if user_data['balance'] >= 200:
            db.update_balance(user_id, -200)
            current_luck = user_data.get('luck', 1.0)
            new_luck = round(current_luck + 0.1, 1)
            db.set_luck(user_id, new_luck)
            text = f"✅ *Удача увеличена!*\n\nТеперь: {new_luck:.1f}x"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 200 ¢"
    
    elif action == "buy_gold":
        user_data = db.get_user_data(user_id)
        if user_data['balance'] >= 1500:
            if db.buy_gold(user_id):
                text = "✅ *GOLD подписка активирована!*\n\n+20% к наградам на 30 дней!"
            else:
                text = "❌ Ошибка!"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 1500 ¢"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "owner_luck_menu")
async def owner_luck_menu_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    text = (
        "🍀 *Управление удачей*\n\n"
        "📋 *Команды:*\n"
        "1. /luck <id> <значение> - постоянная удача\n"
        "2. /temp_luck <id> <значение> <минуты> - временная удача\n"
        "3. /luck_all <значение> - удача всем\n"
        "4. /luck_reset_all - сбросить удачу всем\n\n"
        "📊 *Примеры:*\n"
        "/luck 123456789 10.0 - удача 10x\n"
        "/temp_luck 123456789 50.0 10 - удача 50x на 10 мин\n"
        "/luck_all 5.0 - всем удача 5x\n"
        "/luck_reset_all - сбросить всем"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🎲 Удача всем", callback_data="owner_luck_all_prompt"),
        InlineKeyboardButton(text="🔄 Сбросить всем", callback_data="owner_luck_reset_prompt")
    )
    keyboard.row(
        InlineKeyboardButton(text="⏱️ Временная удача", callback_data="owner_temp_luck_prompt"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="owner_panel")
    )
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "owner_luck_all_prompt")
async def owner_luck_all_prompt_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback_query.message.answer(
        "🎲 *Установить удачу ВСЕМ пользователям*\n\n"
        "Введите команду:\n"
        "/luck_all <значение>\n\n"
        "Пример: /luck_all 10.0\n\n"
        "⚠️ *Внимание: Это действие нельзя отменить!*",
        parse_mode="Markdown"
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "owner_luck_reset_prompt")
async def owner_luck_reset_prompt_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback_query.message.answer(
        "🔄 *Сбросить удачу у ВСЕХ пользователей*\n\n"
        "Введите команду:\n"
        "/luck_reset_all\n\n"
        "⚠️ *Внимание: Это действие нельзя отменить!*",
        parse_mode="Markdown"
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "owner_temp_luck_prompt")
async def owner_temp_luck_prompt_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback_query.message.answer(
        "⏱️ *Установить временную удачу*\n\n"
        "Введите команду:\n"
        "/temp_luck <id> <значение> <минуты>\n\n"
        "📊 *Примеры:*\n"
        "/temp_luck 123456789 5.0 5 - удача 5x на 5 минут\n"
        "/temp_luck 123456789 100.0 60 - удача 100x на 1 час\n\n"
        "📊 *Эффект:* Временная удача заменяет постоянную на указанное время.",
        parse_mode="Markdown"
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("luck_all_confirm_"))
async def luck_all_confirm_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        luck_value = float(callback_query.data.replace("luck_all_confirm_", ""))
        user_count = db.set_luck_all(luck_value)
        
        await callback_query.message.edit_text(
            f"✅ *Удача установлена ВСЕМ пользователям!*\n\n"
            f"🍀 *Значение:* {luck_value:.1f}x\n"
            f"👥 *Затронуто пользователей:* {user_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "luck_reset_all_confirm")
async def luck_reset_all_confirm_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        user_count = db.remove_luck_all()
        
        await callback_query.message.edit_text(
            f"✅ *Удача сброшена у ВСЕХ пользователей!*\n\n"
            f"🍀 *Теперь у всех:* 1.0x\n"
            f"👥 *Затронуто пользователей:* {user_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Ошибка: {e}")
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("broadcast_confirm_"))
async def broadcast_confirm_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    original_msg_id = int(callback_query.data.replace("broadcast_confirm_", ""))
    
    try:
        original_message = await bot.get_message(
            chat_id=callback_query.message.chat.id,
            message_id=original_msg_id
        )
        
        broadcast_text = original_message.text
        if "\n\n" in broadcast_text:
            broadcast_text = broadcast_text.split("\n\n", 1)[1]
        
        await callback_query.message.edit_text("📢 *Рассылка началась...*", parse_mode="Markdown")
        
        all_users = db.get_all_users()
        total_users = len(all_users)
        sent_count = 0
        failed_count = 0
        
        for user_id in all_users.keys():
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"📢 *Сообщение от администратора:*\n\n{broadcast_text}",
                    parse_mode="Markdown"
                )
                sent_count += 1
                
                if sent_count % 10 == 0:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                failed_count += 1
        
        await callback_query.message.answer(
            f"✅ *Рассылка завершена!*\n\n"
            f"👥 *Всего пользователей:* {total_users}\n"
            f"✅ *Успешно отправлено:* {sent_count}\n"
            f"❌ *Не отправлено:* {failed_count}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await callback_query.message.answer(f"❌ Ошибка рассылки: {e}")
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "event_start")
async def event_start_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await callback_query.answer("❌ Сначала подпишитесь!", show_alert=True)
        return
    
    if not await is_chat_admin(user_id, chat_id):
        await callback_query.answer("❌ Только админы чата!", show_alert=True)
        return
    
    if not db.check_gold(user_id):
        await callback_query.answer("❌ Нужна GOLD подписка!", show_alert=True)
        return
    
    global active_event
    if active_event:
        await callback_query.answer("❌ Уже есть активный эвент!", show_alert=True)
        return
    
    event_types = [
        ("🎯 Обычный", 100, 300, "Обычный эвент", 1.0),
        ("🚀 Средний", 300, 600, "Средний эвент", 1.0),
        ("💎 Мега", 600, 1000, "Мега эвент с бонусом удачи!", 1.2)
    ]
    etype, emin, emax, edesc, bonus_value = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    end_time = datetime.now() + timedelta(hours=1)
    
    active_event = {
        'id': event_id,
        'type': etype,
        'reward': reward,
        'end_time': end_time,
        'chat_id': chat_id,
        'creator': user_id,
        'description': edesc,
        'bonus_value': bonus_value
    }
    event_participants[event_id] = []
    
    text = (
        f"🎪 *Новый эвент!*\n\n"
        f"🎯 *{etype}*\n"
        f"💰 *{reward} ¢*\n"
        f"⏳ *1 час*\n"
        f"📝 *{edesc}*\n"
        f"🆔 *{event_id}*\n\n"
        f"*Присоединиться:* нажмите кнопку ниже"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_event_{event_id}"))
    keyboard.row(InlineKeyboardButton(text="📊 Профиль", callback_data="profile"))
    
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
        await callback_query.answer("❌ Эвент уже завершен!", show_alert=True)
        return
    
    user_id = callback_query.from_user.id
    
    if active_event['creator'] != OWNER_ID and active_event.get('chat_id') != callback_query.message.chat.id:
        await callback_query.answer("❌ Этот эвент в другом чате!", show_alert=True)
        return
    
    if user_id in event_participants.get(active_event['id'], []):
        await callback_query.answer("✅ Вы уже участвуете!", show_alert=True)
        return
    
    event_participants[active_event['id']].append(user_id)
    parts = len(event_participants[active_event['id']])
    time_left = format_time(active_event['end_time'])
    
    # Если это эвент с бонусом, даём бонус удачи до конца эвента
    bonus_value = active_event.get('bonus_value', 1.0)
    if bonus_value > 1.0:
        db.set_event_bonus(user_id, active_event['id'], bonus_value, active_event['end_time'])
        bonus_percent = (bonus_value - 1) * 100
        bonus_text = f"\n✨ *Вы получили бонус: +{bonus_percent:.0f}% к удаче до конца эвента!*"
    else:
        bonus_text = ""
    
    await callback_query.answer(f"🎉 Вы присоединились к эвенту! {parts} участников", show_alert=True)
    
    text = (
        f"🎪 *Эвент*\n\n"
        f"🎯 *{active_event['type']}*\n"
        f"💰 *{active_event['reward']} ¢*\n"
        f"👥 *{parts} участников*\n"
        f"⏳ *{time_left}*"
        f"{bonus_text}\n\n"
        f"🆔 *ID:* {active_event['id']}"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🎪 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_event_{active_event['id']}"))
    keyboard.row(InlineKeyboardButton(text="📊 Профиль", callback_data="profile"))
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

# =================== ЗАДАЧИ ФОНОВОЙ ОБРАБОТКИ ===================
async def check_events_task():
    """Автоматическое завершение эвентов"""
    while True:
        global active_event
        if active_event and datetime.now() >= active_event['end_time']:
            eid = active_event['id']
            parts = event_participants.get(eid, [])
            
            if parts:
                reward = active_event['reward']
                for uid in parts:
                    db.update_balance(uid, reward)
                
                # Удаляем бонус удачи у всех участников
                for uid in parts:
                    db.remove_event_bonus(uid)
                
                # Если это МЕГА эвент, отправляем отдельное сообщение
                bonus_value = active_event.get('bonus_value', 1.0)
                if bonus_value > 1.0:
                    bonus_percent = (bonus_value - 1) * 100
                    try:
                        await bot.send_message(
                            active_event['chat_id'],
                            f"🎉 *МЕГА эвент завершен!*\n\n"
                            f"🎯 *{active_event['type']}*\n"
                            f"💰 *{reward} ¢ каждому*\n"
                            f"👥 *{len(parts)} участников*\n\n"
                            f"✨ *Бонус удачи (+{bonus_percent:.0f}%) был активен до конца эвента и теперь снят.*\n\n"
                            f"Поздравляем! 🎊",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                else:
                    try:
                        await bot.send_message(
                            active_event['chat_id'],
                            f"🎉 *Эвент завершен!*\n\n"
                            f"🎯 *{active_event['type']}*\n"
                            f"💰 *{reward} ¢ каждому*\n"
                            f"👥 *{len(parts)} участников*\n\n"
                            f"Поздравляем! 🎊",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            active_event = None
            if eid in event_participants:
                del event_participants[eid]
        
        await asyncio.sleep(60)

async def cleanup_temp_luck_task():
    """Очистка истекшей временной удачи"""
    while True:
        try:
            users = db.get_all_users()
            cleaned_count = 0
            
            for user_id, data in users.items():
                temp_end = data.get('temp_luck_end')
                if temp_end:
                    end_time = datetime.fromisoformat(temp_end)
                    if datetime.now() >= end_time:
                        db.remove_temp_luck(user_id)
                        cleaned_count += 1
            
            if cleaned_count > 0:
                print(f"🧹 Очищена временная удача у {cleaned_count} пользователей")
                
        except Exception as e:
            print(f"⚠️ Ошибка очистки временной удачи: {e}")
        
        await asyncio.sleep(300)

async def cleanup_event_bonus_task():
    """Очистка истекших бонусов от эвентов"""
    while True:
        try:
            users = db.get_all_users()
            cleaned_count = 0
            
            for user_id, data in users.items():
                event_bonus = data.get('event_bonus')
                if event_bonus and event_bonus.get('end_time'):
                    end_time = datetime.fromisoformat(event_bonus['end_time'])
                    if datetime.now() >= end_time:
                        db.remove_event_bonus(user_id)
                        cleaned_count += 1
            
            if cleaned_count > 0:
                print(f"🧹 Снят бонус от эвента у {cleaned_count} пользователей")
                
        except Exception as e:
            print(f"⚠️ Ошибка очистки бонусов эвента: {e}")
        
        await asyncio.sleep(600)

# =================== ЗАПУСК ===================
async def main():
    print("=" * 50)
    print("🤖 Farm Bot запускается...")
    print(f"👑 Владелец: {OWNER_ID}")
    print(f"📢 Канал: @{CHANNEL_USERNAME}")
    print("=" * 50)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_events_task())
    asyncio.create_task(cleanup_temp_luck_task())
    asyncio.create_task(cleanup_event_bonus_task())
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
