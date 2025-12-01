from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suda_bot.models import User, Barista
from suda_bot.utils import cleanup_old_codes_for_user, get_or_create_daily_code

barista_router = Router()

# --- FSM ---
class BaristaStates(StatesGroup):
    waiting_for_code_search = State()
    waiting_for_check_discount = State()

# --- Клавиатуры ---
def barista_menu_keyboard():
    kb = [
        [KeyboardButton(text="Выдать код")],
        [KeyboardButton(text="Проверить баллы")],
        [KeyboardButton(text="Правила акции")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu_keyboard():
    kb = [
        [KeyboardButton(text="Выдать код")],
        [KeyboardButton(text="Проверить баллы")],
        [KeyboardButton(text="Добавить бариста")],
        [KeyboardButton(text="Правила акции")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Вспомогательная функция для проверки администратора ---
async def is_admin_barista(telegram_id: str, session: AsyncSession) -> bool:
    barista = await session.execute(
        select(Barista).where(Barista.telegram_id == telegram_id, Barista.is_admin == True)
    )
    return barista.scalar_one_or_none() is not None

# --- Команды ---
@barista_router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if is_admin:
        await message.answer("Привет, администратор!", reply_markup=admin_menu_keyboard())
        return

    barista = await session.execute(
        select(Barista).where(Barista.telegram_id == str(message.from_user.id))
    )
    if barista := barista.scalar_one_or_none():
        await message.answer("Привет, бариста!", reply_markup=barista_menu_keyboard())
    else:
        await message.answer("У вас нет доступа к этой команде.")

@barista_router.message(Command("new_barista"))
async def cmd_new_barista(message: Message, session: AsyncSession):
    # Только администратор может использовать команду
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите ID пользователя, которого хотите добавить как бариста (например: 123456789):")

@barista_router.message(F.text.isdigit())
async def handle_new_barista_id(message: Message, session: AsyncSession):
    # Проверим, является ли отправитель администратором
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        return

    new_barista_id = message.text.strip()

    existing_barista = await session.execute(
        select(Barista).where(Barista.telegram_id == new_barista_id)
    )
    if existing_barista.scalar_one_or_none():
        await message.answer(f"Пользователь с ID {new_barista_id} уже является бариста.")
        return

    # Добавляем нового бариста
    new_barista = Barista(telegram_id=new_barista_id, is_admin=False)
    session.add(new_barista)
    await session.commit()

    await message.answer(f"Пользователь с ID {new_barista_id} добавлен как бариста.")

@barista_router.message(F.text == "Добавить бариста")
async def ask_new_barista(message: Message, session: AsyncSession):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите ID пользователя, которого хотите добавить как бариста (например: 123456789):")

@barista_router.message(F.text == "Выдать код")
async def ask_for_codes(message: Message, state: FSMContext):
    await message.answer("Введите фамилию и последние 4 цифры телефона (например: Иванов 4567)")
    await state.set_state(BaristaStates.waiting_for_code_search)

@barista_router.message(F.text == "Проверить баллы")
async def ask_for_check_discount(message: Message, state: FSMContext):
    await message.answer("Введите фамилию и последние 4 цифры телефона (например: Иванов 4567)")
    await state.set_state(BaristaStates.waiting_for_check_discount)

# --- Обработка ввода после "Выдать код" ---
@barista_router.message(BaristaStates.waiting_for_code_search, F.text.contains(" "))
async def handle_codes_search(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()  # Сброс состояния

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        return

    last_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        return

    user = await session.execute(
        select(User).where(
            User.last_name == last_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    await cleanup_old_codes_for_user(session, user.id)

    code_entry = await get_or_create_daily_code(session, user.id)

    await message.answer(f"Код для {user.first_name} {user.last_name}: `{code_entry.code}`", parse_mode="Markdown")

# --- Обработка ввода после "Проверить баллы" ---
@barista_router.message(BaristaStates.waiting_for_check_discount, F.text.contains(" "))
async def handle_check_discount(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()  # Сброс состояния

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        return

    last_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        return

    user = await session.execute(
        select(User).where(
            User.last_name == last_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    remaining = 7 - user.points
    await message.answer(f"У {user.first_name} {user.last_name}: {user.points}/7 очков. Осталось до бесплатного: {remaining}")

@barista_router.message(F.text == "Правила акции")
async def show_rules(message: Message):
    await message.answer(
        "Акция: купите 7 напитков — 8-й в подарок!\n"
        "Каждый день бариста выдаёт вам уникальный код — введите его в боте, чтобы получить 1 очко.\n"
        "Можно получить только 1 очко в день.\n"
        "После 7 очков — бесплатный напиток!"
    )