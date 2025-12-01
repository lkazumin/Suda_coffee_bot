from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from datetime import datetime
from suda_bot.models import User, DailyCode
from suda_bot.utils import generate_numeric_code
from suda_bot.config import BARISTA_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN
from aiogram import Bot

user_router = Router()

# --- FSM ---
class Registration(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_phone = State()

# --- Клавиатуры ---
def welcome_keyboard():
    kb = [
        [InlineKeyboardButton(text="Начать регистрацию", callback_data="start_registration")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def request_phone_keyboard():
    kb = [
        [KeyboardButton(text="Отправить номер", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def main_menu_keyboard():
    kb = [
        [KeyboardButton(text="Получить код")],
        [KeyboardButton(text="Моя скидка")],
        [KeyboardButton(text="Правила акции")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Команды ---
@user_router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    # Проверяем, бариста ли это
    if str(message.from_user.id) in BARISTA_TELEGRAM_IDS:
        # Перенаправляем в бариста
        from suda_bot.handlers.barista import barista_menu_keyboard
        await message.answer("Привет, бариста!", reply_markup=barista_menu_keyboard())
        return

    # Обычный пользователь
    user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
    user = user.scalar_one_or_none()

    if user:
        await message.answer("Добро пожаловать в кофейню “Сюда”! ☕️", reply_markup=main_menu_keyboard())
        return

    # Отправляем приветствие с inline-кнопкой
    await message.answer(
        "Добро пожаловать в кофейню “Сюда”! ☕️\n\n"
        "За каждые 7 посещений вы можете получить 8-й напиток в подарок!\n"
        "Каждый день мы готовим для вас не только вкусный кофе, но и уникальный промокод — просто загляните к нам и введите его в боте, чтобы получить 1 очко и приблизиться к вашему бесплатному напитку!",
        reply_markup=welcome_keyboard()
    )

# --- Обработка нажатия inline-кнопки ---
@user_router.callback_query(F.data == "start_registration")
async def start_registration_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Введите ваше имя:")
    await state.set_state(Registration.waiting_for_first_name)
    await callback_query.answer()

@user_router.message(Registration.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    first_name = message.text.strip()

    if not first_name:
        await message.answer("Введите ваше имя.")
        return

    await state.update_data(first_name=first_name)
    await message.answer("Введите вашу фамилию:")
    await state.set_state(Registration.waiting_for_last_name)

@user_router.message(Registration.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    last_name = message.text.strip()

    if not last_name:
        await message.answer("Введите вашу фамилию.")
        return

    await state.update_data(last_name=last_name)
    await message.answer("Теперь нажмите кнопку ниже, чтобы отправить ваш номер телефона:", reply_markup=request_phone_keyboard())
    await state.set_state(Registration.waiting_for_phone)

@user_router.message(Registration.waiting_for_phone, F.contact)
async def process_phone_from_contact(message: Message, session: AsyncSession, state: FSMContext):
    contact = message.contact

    # Проверяем, что контакт принадлежит пользователю
    if contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте свой номер.")
        return

    phone = contact.phone_number

    if not phone.isdigit() or len(phone) < 10:
        await message.answer("Неверный формат номера. Попробуйте снова.")
        return

    # Приводим к 11-значному формату
    if phone.startswith('8') and len(phone) == 11:
        phone = '7' + phone[1:]
    elif phone.startswith('7') and len(phone) == 11:
        pass
    elif phone.startswith('+7') and len(phone) == 12:
        phone = phone[1:]
    else:
        await message.answer("Неверный формат номера. Попробуйте снова.")
        return

    data = await state.get_data()
    first_name = data['first_name']
    last_name = data['last_name']

    new_user = User(
        telegram_id=str(message.from_user.id),
        first_name=first_name,
        last_name=last_name,
        phone=phone
    )
    session.add(new_user)
    await session.commit()

    await state.clear()

    await message.answer(
        "Регистрация завершена!",
        reply_markup=main_menu_keyboard()
    )

@user_router.message(Registration.waiting_for_phone)
async def process_phone_invalid(message: Message):
    await message.answer("Пожалуйста, нажмите кнопку 'Отправить номер'.")

@user_router.message(F.text == "Получить код")
async def request_code(message: Message, session: AsyncSession):
    user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Сначала зарегистрируйтесь используя /start")
        return

    today = datetime.now().date()

    # Удаляем старые коды
    await session.execute(
        delete(DailyCode).where(
            DailyCode.user_id == user.id,
            DailyCode.date < today
        )
    )

    # Ищем код на сегодня
    code_entry = await session.execute(
        select(DailyCode).where(
            DailyCode.user_id == user.id,
            DailyCode.date == today
        )
    )
    code_entry = code_entry.scalar_one_or_none()

    if not code_entry:
        code = generate_numeric_code()
        new_code = DailyCode(
            code=code,
            user_id=user.id,
            date=today,
            is_used=False
        )
        session.add(new_code)
        await session.commit()
        code_entry = new_code

    # Отправляем бариста сообщение
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    for barista_id in BARISTA_TELEGRAM_IDS:
        try:
            await bot.send_message(
                chat_id=barista_id,
                text=f"{user.last_name} {user.phone[-4:]}: {code_entry.code}"
            )
        except Exception as e:
            print(f"Failed to send message to barista {barista_id}: {e}")
            pass

    await message.answer("Ваш запрос на код отправлен бариста. Скажите ему свою фамилию.\nОтправьте код в чат без лишних символов:")

@user_router.message(F.text == "Моя скидка")
async def show_discount(message: Message, session: AsyncSession):
    user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Сначала зарегистрируйтесь используя /start")
        return

    remaining = 7 - user.points
    await message.answer(f"У вас {user.points}/7 очков. Осталось до бесплатного напитка: {remaining}")

@user_router.message(F.text == "Правила акции")
async def show_rules(message: Message):
    await message.answer(
        "Акция: купите 7 напитков — 8-й в подарок!\n"
        "Каждый день бариста выдаёт вам уникальный код — введите его в боте, чтобы получить 1 очко.\n"
        "Можно получить только 1 очко в день.\n"
        "После 7 очков — бесплатный напиток!"
    )

# --- Обработка ввода кода от клиента ---
@user_router.message(F.text.regexp(r"^\d{6}$"))  # Только 6-значные цифры
async def handle_code_from_client(message: Message, session: AsyncSession):
    code = message.text.strip()

    user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь используя /start")
        return

    if str(message.from_user.id) in BARISTA_TELEGRAM_IDS:
        await message.answer("Вы бариста — используйте кнопки", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
        return

    db_code = await session.execute(
        select(DailyCode).where(
            DailyCode.code == code,
            DailyCode.is_used == False
        )
    )
    db_code = db_code.scalar_one_or_none()

    if user.last_check_in and user.last_check_in.date() == datetime.now().date():
        await message.answer("Вы уже использовали код сегодня. Приходите завтра!")
        return

    if not db_code:
        await message.answer("Неверный или уже использованный код")
        return

    if db_code.user_id != user.id:
        await message.answer("Этот код не принадлежит вам")
        return

    # Помечаем код как использованный
    stmt = (
        update(DailyCode)
        .where(DailyCode.id == db_code.id)
        .values(is_used=True)
    )
    await session.execute(stmt)

    # Обновляем пользователя
    stmt_user = (
        update(User)
        .where(User.telegram_id == str(message.from_user.id))
        .values(
            points=User.points + 1,
            last_check_in=datetime.now()
        )
    )
    await session.execute(stmt_user)
    await session.commit()

    # Проверяем, набрал ли 7 очков
    updated_user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
    updated_user = updated_user.scalar_one()
    remaining = 7 - updated_user.points

    if remaining <= 0:
        await message.answer("Поздравляем! Вы получаете бесплатный напиток!")
        # Сброс
        stmt_reset = (
            update(User)
            .where(User.telegram_id == str(message.from_user.id))
            .values(points=0)
        )
        await session.execute(stmt_reset)
        await session.commit()
    else:
        await message.answer(f"Вы получили 1 очко! Осталось до бесплатного напитка: {remaining}")