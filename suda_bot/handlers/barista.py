from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import date
from suda_bot.models import User, DailyCode
from suda_bot.utils import generate_numeric_code
from suda_bot.config import BARISTA_TELEGRAM_IDS

barista_router = Router()

# --- FSM ---
class BaristaState(StatesGroup):
    waiting_for_action = State()  # Ожидание выбора действия (не используется)
    waiting_for_user_info = State()  # Ожидание Фамилия 4цифры

# --- Клавиатуры ---
def barista_menu_keyboard():
    kb = [
        [KeyboardButton(text="Выдать код")],
        [KeyboardButton(text="Проверить баллы")],
        [KeyboardButton(text="Правила акции")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Команды ---
@barista_router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    if str(message.from_user.id) not in BARISTA_TELEGRAM_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return

    await state.clear()
    await message.answer("Привет, бариста!", reply_markup=barista_menu_keyboard())

# --- Обработчики кнопок ---
@barista_router.message(F.text == "Выдать код")
async def ask_for_codes_button(message: Message, state: FSMContext):
    if str(message.from_user.id) not in BARISTA_TELEGRAM_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return

    await state.set_state(BaristaState.waiting_for_user_info)
    await state.update_data(action='issue_code')
    await message.answer("Введите фамилию и последние 4 цифры телефона (например: Иванов 4567)")

@barista_router.message(F.text == "Проверить баллы")
async def ask_for_check_points_button(message: Message, state: FSMContext):
    if str(message.from_user.id) not in BARISTA_TELEGRAM_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return

    await state.set_state(BaristaState.waiting_for_user_info)
    await state.update_data(action='check_points')
    await message.answer("Введите фамилию и последние 4 цифры телефона (например: Иванов 4567)")

# --- Обработчик текста в состоянии waiting_for_user_info ---
@barista_router.message(BaristaState.waiting_for_user_info)
async def handle_user_info(message: Message, session: AsyncSession, state: FSMContext):
    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        await message.answer("Неверный формат. Введите: Фамилия 4цифры")
        return

    last_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        await message.answer("Последние 4 цифры должны быть числом.")
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
        await state.clear()
        return

    data = await state.get_data()
    action = data.get('action', 'unknown')

    if action == 'issue_code':
        today = date.today()

        await session.execute(
            delete(DailyCode).where(
                DailyCode.user_id == user.id,
                DailyCode.date < today
            )
        )

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
                date=today
            )
            session.add(new_code)
            await session.commit()
            code_entry = new_code

        await message.answer(f"Код для {user.first_name} {user.last_name}: `{code_entry.code}`", parse_mode="Markdown")

    elif action == 'check_points':
        remaining = 7 - user.points
        await message.answer(f"У {user.first_name} {user.last_name}: {user.points}/7 очков. Осталось до бесплатного: {remaining}")

    else:
        await message.answer("Неизвестная команда.")

    await state.clear()

@barista_router.message(F.text == "Правила акции")
async def show_rules(message: Message):
    await message.answer(
        "Акция: купите 7 напитков — 8-й в подарок!\n"
        "Каждый день бариста выдаёт вам уникальный код — введите его в боте, чтобы получить 1 очко.\n"
        "Можно получить только 1 очко в день.\n"
        "После 7 очков — бесплатный напиток!"
    )