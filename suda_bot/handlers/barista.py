from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from suda_bot.handlers.user import is_barista
from suda_bot.models import User, Barista
from suda_bot.config import TELEGRAM_BOT_TOKEN
from aiogram import Bot

barista_router = Router()


# --- FSM ---
class BaristaStates(StatesGroup):
    waiting_for_deduct_points = State()
    waiting_for_check_discount = State()
    waiting_for_enter_code = State()
    waiting_for_add_points = State()
    waiting_for_new_barista_id = State()


# --- Клавиатуры ---
def barista_menu_keyboard():
    kb = [
        [KeyboardButton(text="Списать баллы")],
        [KeyboardButton(text="Проверить баллы")],
        [KeyboardButton(text="Ввести код клиенту")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def admin_menu_keyboard():
    kb = [
        [KeyboardButton(text="Списать баллы")],
        [KeyboardButton(text="Проверить баллы")],
        [KeyboardButton(text="Ввести код клиенту")],
        [KeyboardButton(text="Выдать баллы")],
        [KeyboardButton(text="Назначить бариста")],
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
async def cmd_new_barista(message: Message, session: AsyncSession, state: FSMContext):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите ID пользователя, которого хотите добавить как бариста:")
    await state.set_state(BaristaStates.waiting_for_new_barista_id)

@barista_router.message(F.text == "Назначить бариста")
async def ask_new_barista(message: Message, session: AsyncSession, state: FSMContext):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите ID пользователя, которого хотите добавить как бариста:")
    await state.set_state(BaristaStates.waiting_for_new_barista_id)


@barista_router.message(BaristaStates.waiting_for_new_barista_id, F.text.isdigit())
async def handle_new_barista_id(message: Message, session: AsyncSession, state: FSMContext):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        await state.clear()
        return

    new_barista_id = message.text.strip()

    existing_barista = await session.execute(
        select(Barista).where(Barista.telegram_id == new_barista_id)
    )
    if existing_barista.scalar_one_or_none():
        await message.answer(f"Пользователь с ID {new_barista_id} уже является бариста.")
        await state.clear()
        return

    new_barista = Barista(telegram_id=new_barista_id, is_admin=False)
    session.add(new_barista)
    await session.commit()

    await message.answer(f"Пользователь с ID {new_barista_id} добавлен как бариста.")
    await state.clear()


@barista_router.message(F.text == "Списать баллы")
async def ask_for_deduct_points(message: Message, state: FSMContext):
    await message.answer("Введите имя и последние 4 цифры телефона")
    await state.set_state(BaristaStates.waiting_for_deduct_points)


@barista_router.message(F.text == "Проверить баллы")
async def ask_for_check_discount(message: Message, state: FSMContext):
    await message.answer("Введите имя и последние 4 цифры телефона")
    await state.set_state(BaristaStates.waiting_for_check_discount)


# --- Ввести код клиенту ---
@barista_router.message(F.text == "Ввести код клиенту")
async def ask_for_enter_code(message: Message, state: FSMContext, session: AsyncSession):
    # Проверяем, что пользователь — бариста или админ
    is_barista_user = await is_barista(str(message.from_user.id), session)
    if not is_barista_user:
        await message.answer("У вас нет доступа к этой функции.")
        return

    await message.answer("Введите имя, последние 4 цифры телефона и код (например: Иван 4721: 123456)")
    await state.set_state(BaristaStates.waiting_for_enter_code)


@barista_router.message(BaristaStates.waiting_for_enter_code, F.text.regexp(r"^[^:]+ \d{4}: \d{6}$"))
async def handle_code_from_barista(message: Message, session: AsyncSession, state: FSMContext):
    # Повторная проверка, что пользователь — бариста или админ
    is_barista_user = await is_barista(str(message.from_user.id), session)
    if not is_barista_user:
        await message.answer("У вас нет доступа к этой функции.")
        await state.clear()
        return

    text = message.text.strip()
    # Разделяем на части: до ": " и после
    parts = text.split(': ')
    if len(parts) != 2:
        await message.answer("Неверный формат. Введите: имя 4 цифры: код")
        return

    name_and_digits = parts[0].strip()
    code = parts[1].strip()

    # Разделяем имя и 4 цифры
    name_parts = name_and_digits.rsplit(' ', 1)
    if len(name_parts) != 2:
        await message.answer("Неверный формат. Введите: имя 4 цифры: код")
        return

    first_name = name_parts[0].strip()
    last_4_digits = name_parts[1].strip()

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        await message.answer("Последние 4 цифры должны быть числом из 4 цифр.")
        return

    if not code.isdigit() or len(code) != 6:
        await message.answer("Код должен быть числом из 6 цифр.")
        return

    # Находим пользователя по имени и 4 цифрам
    user = await session.execute(
        select(User).where(
            User.first_name == first_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return

    # Проверяем, существует ли такой код и не использован ли он
    from suda_bot.models import DailyCode
    db_code = await session.execute(
        select(DailyCode).where(
            DailyCode.code == code,
            DailyCode.is_used == False
        )
    )
    db_code = db_code.scalar_one_or_none()

    if not db_code:
        await message.answer("Неверный или уже использованный код.")
        await state.clear()
        return

    # Проверяем, принадлежит ли код пользователю
    if db_code.user_id != user.id:
        await message.answer("Этот код не принадлежит указанному пользователю.")
        await state.clear()
        return

    # Помечаем код как использованный
    stmt = (
        update(DailyCode)
        .where(DailyCode.id == db_code.id)
        .values(is_used=True)
    )
    await session.execute(stmt)

    # Начисляем 1 балл пользователю
    stmt_user = (
        update(User)
        .where(User.telegram_id == user.telegram_id)
        .values(points=User.points + 1)
    )
    await session.execute(stmt_user)
    await session.commit()

    # Отправляем уведомление пользователю
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"Вы получили 1 балл! Теперь у вас {user.points} баллов."
        )
    except Exception:
        pass  # Не удалось отправить — не критично

    # Отправляем уведомление баристе
    await message.answer(f"Балл клиенту {user.first_name} {last_4_digits} начислен!")

    # Очищаем состояние
    await state.clear()


# --- Выдать баллы (только для администратора) ---
@barista_router.message(F.text == "Выдать баллы")
async def ask_for_add_points(message: Message, state: FSMContext, session: AsyncSession):
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите имя и последние 4 цифры телефона")
    await state.set_state(BaristaStates.waiting_for_add_points)


@barista_router.message(BaristaStates.waiting_for_add_points, F.text.contains(" "))
async def handle_ask_for_add_points(message: Message, session: AsyncSession, state: FSMContext):
    # Проверяем, что пользователь всё ещё администратор (защита от подмены)
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        await state.clear()  # Очищаем состояние
        return

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        await message.answer("Неверный формат. Введите имя и последние 4 цифры телефона:")
        return

    first_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        await message.answer("Последние 4 цифры должны быть числом из 4 цифр.")
        return

    user = await session.execute(
        select(User).where(
            User.first_name == first_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    await message.answer(f"Введите количество баллов для {user.first_name} {user.phone[-4:]}")
    await state.update_data(user_id=user.telegram_id)
    await state.set_state(BaristaStates.waiting_for_add_points)


@barista_router.message(BaristaStates.waiting_for_add_points, F.text.isdigit())
async def handle_add_points(message: Message, session: AsyncSession, state: FSMContext):
    # ПОВТОРНАЯ ПРОВЕРКА АДМИНА — КРИТИЧЕСКИ ВАЖНО!
    is_admin = await is_admin_barista(str(message.from_user.id), session)

    if not is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        await state.clear()
        return

    points_to_add = int(message.text.strip())

    if points_to_add <= 0:
        await message.answer("Количество баллов должно быть положительным числом.")
        return

    data = await state.get_data()
    user_telegram_id = data.get('user_id')

    if not user_telegram_id:
        await message.answer("Ошибка: пользователь не найден. Попробуйте снова.")
        await state.clear()
        return

    user = await session.execute(select(User).where(User.telegram_id == user_telegram_id))
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден. Попробуйте снова.")
        await state.clear()
        return

    # Обновляем количество баллов пользователя
    stmt = (
        update(User)
        .where(User.telegram_id == user_telegram_id)
        .values(points=User.points + points_to_add)
    )
    await session.execute(stmt)
    await session.commit()

    # Отправляем уведомление пользователю
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"Вам начислено {points_to_add} баллов! Теперь у вас {user.points} баллов."
        )
    except Exception:
        pass  # Не удалось отправить — не критично

    await message.answer(
        f"Пользователю {user.first_name} {user.phone[-4:]} начислено {points_to_add} баллов. Теперь у него {user.points} баллов.")
    await state.clear()  # Важно: очищаем состояние после успешной операции


# --- Обработка ввода после "Списать баллы" ---
@barista_router.message(BaristaStates.waiting_for_deduct_points, F.text.contains(" "))
async def handle_deduct_points(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        return

    first_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        return

    user = await session.execute(
        select(User).where(
            User.first_name == first_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    if user.points < 6:
        await message.answer(f"У {user.first_name} недостаточно баллов для списания (требуется 6).")
        return

    # Списываем 6 баллов
    stmt = (
        update(User)
        .where(User.telegram_id == user.telegram_id)
        .values(points=User.points - 6)
    )
    await session.execute(stmt)
    await session.commit()

    # Отправляем уведомление клиенту
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text="Поздравляем! Вы можете получить бесплатный напиток. 6 баллов списано."
        )
    except Exception:
        pass  # Не удалось отправить — не критично

    await message.answer(f"У {user.first_name} списано 6 баллов. Осталось: {user.points}")


# --- Обработка ввода после "Проверить баллы" ---
@barista_router.message(BaristaStates.waiting_for_check_discount, F.text.contains(" "))
async def handle_check_discount(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        return

    first_name = parts[0]
    last_4_digits = parts[1]

    if not last_4_digits.isdigit() or len(last_4_digits) != 4:
        return

    user = await session.execute(
        select(User).where(
            User.first_name == first_name,
            User.phone.like(f"%{last_4_digits}")
        )
    )
    user = user.scalar_one_or_none()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    await message.answer(f"У {user.first_name}: {user.points} баллов.")


@barista_router.message(F.text == "Правила акции")
async def show_rules(message: Message):
    await message.answer(
        "Акция: купите 6 напитков — 7-й в подарок!\n"
        "Каждый день бариста выдаёт вам уникальный код — введите его в боте, чтобы получить 1 балл.\n"
        "За каждые 6 баллов вы можете получить бесплатный напиток!"
    )