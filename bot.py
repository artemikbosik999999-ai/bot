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
from aiogram.enums import ChatMemberStatus

# =================== КОНСТАНТЫ ===================
OWNER_ID = 7119681628
CHANNEL_USERNAME = "artem_bori"
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Замените на ваш токен!

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
        # Подключаемся к Redis
        try:
            self.redis = redis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis.ping()
            print("✅ Redis подключен")
        except:
            # Если Redis нет, используем словарь в памяти
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
            'subscription': None,
            'subscription_end': None,
            'is_permanent': False,
            'cooldowns': {},
            'total_earned': 0,
            'is_banned': False,
            'channel_check': False,
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
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.seconds % 3600) // 60)
    return f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"

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

# =================== КОМАНДЫ ВЛАДЕЛЬЦА ===================
@dp.message(Command("owner"))
async def owner_cmd(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    text = (
        "👑 *Панель владельца*\n\n"
        "💰 *Балансы:*\n"
        "`/give <id> <сумма>` - выдать\n"
        "`/set <id> <сумма>` - установить\n"
        "`/resetcd <id>` - сбросить кулдауны\n\n"
        "🎖️ *Подписки:*\n"
        "`/gold <id> <дни>` - выдать GOLD\n"
        "`/gold_forever <id>` - вечная GOLD\n"
        "`/remove_gold <id>` - удалить\n\n"
        "⚙️ *Админ:*\n"
        "`/ban <id>` - забанить\n"
        "`/unban <id>` - разбанить\n\n"
        "🎪 *Эвенты:*\n"
        "`/owner_event` - запустить эвент\n"
        "`/stop_event` - остановить эвент"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("give"))
async def give_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.update_balance(user_id, amount)
        new = db.get_user_data(user_id)['balance']
        await message.answer(f"✅ Выдано `{amount} ¢`\nНовый баланс: `{new} ¢`")
    except:
        await message.answer("❌ Ошибка! Использование: `/give <id> <сумма>`")

@dp.message(Command("set"))
async def set_money(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        args = command.args.split()
        user_id, amount = int(args[0]), float(args[1])
        db.set_balance(user_id, amount)
        await message.answer(f"✅ Баланс установлен: `{amount} ¢`")
    except:
        await message.answer("❌ Ошибка! Использование: `/set <id> <сумма>`")

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
        await message.answer("❌ Ошибка! Использование: `/gold <id> <дни>`")

@dp.message(Command("gold_forever"))
async def gold_forever(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.give_gold(user_id, permanent=True)
        await message.answer(f"✅ Вечная GOLD выдана")
    except:
        await message.answer("❌ Ошибка! Использование: `/gold_forever <id>`")

@dp.message(Command("remove_gold"))
async def remove_gold_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.remove_gold(user_id)
        await message.answer(f"✅ GOLD удалена")
    except:
        await message.answer("❌ Ошибка! Использование: `/remove_gold <id>`")

@dp.message(Command("ban"))
async def ban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.ban_user(user_id, True)
        await message.answer(f"⛔ Пользователь забанен")
    except:
        await message.answer("❌ Ошибка! Использование: `/ban <id>`")

@dp.message(Command("unban"))
async def unban_cmd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.ban_user(user_id, False)
        await message.answer(f"✅ Пользователь разбанен")
    except:
        await message.answer("❌ Ошибка! Использование: `/unban <id>`")

@dp.message(Command("resetcd"))
async def reset_cd(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(command.args)
        db.clear_cooldowns(user_id)
        await message.answer(f"✅ Кулдауны сброшены")
    except:
        await message.answer("❌ Ошибка! Использование: `/resetcd <id>`")

# =================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ===================
@dp.message(Command("check"))
async def check_channel(message: Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME}"))
    keyboard.row(InlineKeyboardButton(text="✅ Проверить", callback_data="verify"))
    text = (
        f"📢 *Подписка на канал*\n\n"
        f"Подпишитесь на канал: @{CHANNEL_USERNAME}\n"
        f"и нажмите 'Проверить'"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())

@dp.callback_query(lambda c: c.data == "verify")
async def verify_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await check_channel_subscription(user_id):
        db.set_channel_check(user_id, True)
        text = "✅ *Подписка подтверждена!* 🎉"
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🚀 Начать", callback_data="start"))
    else:
        text = "❌ *Вы не подписаны!*\n\nПодпишитесь и нажмите 'Проверить' снова"
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME}"))
        keyboard.row(InlineKeyboardButton(text="🔄 Проверить", callback_data="verify"))
    await callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
    await callback_query.answer()

# =================== ОСНОВНЫЕ КОМАНДЫ ===================
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    
    if db.is_banned(user_id):
        await message.answer("⛔ Вы забанены!")
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await check_channel(message)
        return
    
    user_data = db.get_user_data(user_id)
    is_admin = await is_chat_admin(user_id, message.chat.id)
    has_gold = db.check_gold(user_id)
    sub_status = get_sub_status(user_data)
    
    # Статус пользователя
    if user_id == OWNER_ID:
        status = "👑 *Владелец* (/owner)"
    elif is_admin and has_gold:
        status = f"🛡️ *Админ* ({sub_status}) - /event_start"
    elif has_gold:
        status = f"✨ *GOLD* ({sub_status})"
    else:
        status = f"👤 *Обычный* ({sub_status})"
    
    # Приветствие
    text = (
        f"🎮 *Farm Bot*\n\n"
        f"{status}\n\n"
        f"💰 Баланс: `{user_data['balance']:.2f} ¢`\n"
        f"✨ Сила: `{user_data['star_power']}`\n"
        f"⏳ Урожайность: `{user_data['productivity']:.2f}`\n\n"
        "🌵 *Фарм команды:*\n"
        "`кактус` `ферма` `шахта`\n"
        "`сад` `охота`\n(кулдаун 2 часа)\n\n"
        "📋 *Команды:*\n"
        "`/profile` - профиль\n"
        "`/shop` - магазин\n"
        "`/events` - эвенты\n"
        "`/help` - помощь"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="📊 Профиль", callback_data="profile")
    )
    
    if active_event and active_event.get('chat_id') == message.chat.id:
        text += f"\n\n🎪 *Активный эвент!*\n/join {active_event['id']}"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())

@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    user_id = message.from_user.id
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь на канал! /check")
        return
    
    user_data = db.get_user_data(user_id)
    sub_status = get_sub_status(user_data)
    
    text = (
        f"📊 *Профиль*\n\n"
        f"💰 Баланс: `{user_data['balance']:.2f} ¢`\n"
        f"✨ Сила: `{user_data['star_power']}`\n"
        f"⏳ Урожайность: `{user_data['productivity']:.2f}`\n"
        f"🎖️ Подписка: {sub_status}\n"
        f"📢 Канал: `{'✅' if db.get_channel_check(user_id) else '❌'}`\n\n"
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
        InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="🎪 Эвенты", callback_data="events")
    )
    
    is_admin = await is_chat_admin(user_id, message.chat.id)
    if is_admin and db.check_gold(user_id):
        keyboard.row(InlineKeyboardButton(text="🚀 Запустить эвент", callback_data="event_start"))
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())

@dp.message(Command("shop"))
async def shop_cmd(message: Message):
    user_id = message.from_user.id
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь! /check")
        return
    
    user_data = db.get_user_data(user_id)
    has_gold = db.check_gold(user_id)
    
    text = (
        "🛒 *Магазин*\n\n"
        "✨ *Сила звёздности* (100 ¢)\n"
        "+0.5 ¢ к каждой награде\n\n"
        "⏳ *Урожайность* (150 ¢)\n"
        "×1.1 к наградам\n\n"
        "🎖️ *GOLD подписка* (1500 ¢)\n"
        "+20% к наградам\n"
    )
    
    if has_gold:
        text += f"• У вас: {get_sub_status(user_data)}\n"
    
    text += f"\n💰 Ваш баланс: `{user_data['balance']:.2f} ¢`"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✨ Сила +1", callback_data="buy_star"),
        InlineKeyboardButton(text="⏳ Урожайность", callback_data="buy_prod")
    )
    
    if has_gold:
        keyboard.row(InlineKeyboardButton(text="🔄 Продлить GOLD", callback_data="buy_gold"))
    else:
        keyboard.row(InlineKeyboardButton(text="🎖️ Купить GOLD", callback_data="buy_gold"))
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())

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
            f"⏳ {time_left}\n\n"
            f"Присоединиться: `/join {active_event['id']}`"
        )
    else:
        text += (
            "📭 *Нет активных эвентов*\n\n"
            "✨ *Как запустить:*\n"
            "1. GOLD подписка\n"
            "2. Быть админом чата\n"
            "3. `/event_start`\n\n"
            "💰 *Награды:* 100-1000 ¢"
        )
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        "❓ *Помощь*\n\n"
        "🌵 *Фарм команды:*\n"
        "кактус, ферма, шахта, сад, охота\n"
        "(кулдаун 2 часа)\n\n"
        "📋 *Основные команды:*\n"
        "`/start` - начало\n"
        "`/profile` - профиль\n"
        "`/shop` - магазин\n"
        "`/events` - эвенты\n"
        "`/check` - подписка на канал\n\n"
        "🎪 *Эвенты:*\n"
        "Запускают админы с GOLD\n"
        "Участвовать может любой\n\n"
        "🎖️ *GOLD подписка:*\n"
        "+20% к наградам\n"
        "1500 ¢ / 30 дней"
    )
    await message.answer(text, parse_mode="Markdown")

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
    
    # Создаем эвент
    event_types = [("🎯 Обычный", 100, 300), ("🚀 Средний", 300, 600), ("💎 Мега", 600, 1000)]
    etype, emin, emax = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    
    active_event = {
        'id': event_id,
        'type': etype,
        'reward': reward,
        'end_time': datetime.now() + timedelta(hours=1),
        'chat_id': chat_id,
        'creator': user_id
    }
    event_participants[event_id] = []
    
    text = (
        f"🎪 *Новый эвент!*\n\n"
        f"🎯 {etype}\n"
        f"💰 {reward} ¢\n"
        f"⏳ 1 час\n"
        f"🆔 {event_id}\n\n"
        f"Присоединиться: `/join {event_id}`"
    )
    await message.answer(text, parse_mode="Markdown")
    # Автоматически добавляем создателя
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
    
    # Создаем эвент для владельца
    event_types = [("🎯 Обычный", 100, 300), ("🚀 Средний", 300, 600), ("💎 Мега", 600, 1000)]
    etype, emin, emax = random.choice(event_types)
    reward = random.randint(emin, emax)
    event_id = random.randint(1000, 9999)
    
    active_event = {
        'id': event_id,
        'type': etype,
        'reward': reward,
        'end_time': datetime.now() + timedelta(hours=1),
        'chat_id': message.chat.id,
        'creator': OWNER_ID
    }
    event_participants[event_id] = []
    
    text = (
        f"🎪 *Владелец запустил эвент!*\n\n"
        f"🎯 {etype}\n"
        f"💰 {reward} ¢\n"
        f"⏳ 1 час\n"
        f"🆔 {event_id}\n\n"
        f"Присоединиться: `/join {event_id}`"
    )
    await message.answer(text, parse_mode="Markdown")
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
        await message.answer(f"Использование: `/join {active_event['id']}`")
        return
    
    if int(command.args) != active_event['id']:
        await message.answer("❌ Неверный ID эвента!")
        return
    
    user_id = message.from_user.id
    
    # Проверка чата для обычных админов
    if active_event['creator'] != OWNER_ID and active_event.get('chat_id') != message.chat.id:
        await message.answer("❌ Этот эвент в другом чате!")
        return
    
    if user_id in event_participants.get(active_event['id'], []):
        await message.answer("✅ Вы уже участвуете!")
        return
    
    event_participants[active_event['id']].append(user_id)
    parts = len(event_participants[active_event['id']])
    time_left = format_time(active_event['end_time'])
    
    await message.answer(
        f"🎉 *Вы присоединились!*\n\n"
        f"🎯 {active_event['type']}\n"
        f"💰 {active_event['reward']} ¢\n"
        f"👥 {parts} участников\n"
        f"⏳ {time_left}",
        parse_mode="Markdown"
    )

# =================== ФАРМ КОМАНДЫ ===================
@dp.message(lambda msg: msg.text and msg.text.lower() in FARM_COMMANDS)
async def farm_command(message: Message):
    user_id = message.from_user.id
    cmd = message.text.lower()
    
    if db.is_banned(user_id):
        await message.answer("⛔ Вы забанены!")
        return
    
    if user_id != OWNER_ID and not db.get_channel_check(user_id):
        await message.answer("❌ Сначала подпишитесь на канал! /check")
        return
    
    # Проверка кулдауна
    cd = db.get_cooldown(user_id, cmd)
    if cd:
        await message.reply(f"⏳ *{cmd} на кулдауне!*\n\nВозвращайтесь через {format_time(cd)}")
        return
    
    user_data = db.get_user_data(user_id)
    cmd_info = FARM_COMMANDS[cmd]
    
    # Базовая награда
    reward = random.randint(cmd_info["min"], cmd_info["max"])
    
    # Бонус силы
    reward += user_data['star_power'] * 0.5
    
    # Урожайность
    reward *= user_data['productivity']
    
    # GOLD подписка
    if db.check_gold(user_id):
        reward *= 1.2
    
    # Случайный бонус 26%
    if random.random() < 0.26:
        bonus = random.randint(5, 15)
        reward += bonus
        bonus_text = f"☢️ +{bonus} ¢\n"
    else:
        bonus_text = ""
    
    reward = round(reward, 2)
    
    # Сохраняем
    db.update_balance(user_id, reward)
    db.set_cooldown(user_id, cmd, hours=2)
    
    new_balance = db.get_user_data(user_id)['balance']
    
    # Ответ
    response = (
        f"{cmd_info['emoji']} *{cmd.upper()}* ✅ *ЗАЧЁТ!*\n\n"
        f"💰 +{reward:.2f} ¢\n"
        f"{bonus_text}"
        f"\n💳 Баланс: *{new_balance:.2f} ¢*\n\n"
        f"⏳ Возвращайтесь через *2 часа*"
    )
    
    await message.reply(response, parse_mode="Markdown")

# =================== CALLBACK ОБРАБОТЧИКИ ===================
@dp.callback_query(lambda c: c.data == "start")
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

@dp.callback_query(lambda c: c.data == "event_start")
async def event_start_callback(callback_query: CallbackQuery):
    await event_start_cmd(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data in ["buy_star", "buy_prod", "buy_gold"])
async def buy_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_data = db.get_user_data(user_id)
    action = callback_query.data
    
    if action == "buy_star":
        if user_data['balance'] >= 100:
            db.update_balance(user_id, -100)
            user_data['star_power'] += 1
            db.save_user_data(user_id, user_data)
            text = "✅ *Сила звёздности +1!*\n\nТеперь +0.5 ¢ к каждой награде!"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 100 ¢"
    
    elif action == "buy_prod":
        if user_data['balance'] >= 150:
            db.update_balance(user_id, -150)
            user_data['productivity'] = round(user_data['productivity'] * 1.1, 2)
            db.save_user_data(user_id, user_data)
            text = f"✅ *Урожайность увеличена!*\n\nТеперь: `{user_data['productivity']}`"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 150 ¢"
    
    elif action == "buy_gold":
        if user_data['balance'] >= 1500:
            if db.buy_gold(user_id):
                text = "✅ *GOLD подписка активирована!*\n\n+20% к наградам на 30 дней!"
            else:
                text = "❌ Ошибка!"
        else:
            text = "❌ *Недостаточно средств!*\n\nНужно: 1500 ¢"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")
    await callback_query.answer()

# =================== ЗАВЕРШЕНИЕ ЭВЕНТОВ ===================
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
                
                # Уведомление
                try:
                    await bot.send_message(
                        active_event['chat_id'],
                        f"🎉 *Эвент завершен!*\n\n"
                        f"🎯 {active_event['type']}\n"
                        f"💰 {reward} ¢ каждому\n"
                        f"👥 {len(parts)} участников\n\n"
                        f"Поздравляем! 🎊",
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
    print("🤖 Farm Bot запускается...")
    print(f"👑 Владелец: {OWNER_ID}")
    print(f"📢 Канал: @{CHANNEL_USERNAME}")
    print("=" * 50)
    
    # Запускаем задачу проверки эвентов
    asyncio.create_task(check_events_task())
    
    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    # Запускаем
    asyncio.run(main())
