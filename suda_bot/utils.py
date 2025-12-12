import secrets
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from suda_bot.models import DailyCode


def generate_numeric_code() -> str:
    """Генерирует 6-значный код только из цифр"""
    return f"{secrets.randbelow(10 ** 6):06d}"


async def cleanup_old_codes_for_user(session: AsyncSession, user_id: int):
    """Удаляет старые (неиспользованные) коды для пользователя"""
    today = datetime.now().date()
    await session.execute(
        delete(DailyCode).where(
            DailyCode.user_id == user_id,
            DailyCode.date < today
        )
    )

async def get_or_create_daily_code(session: AsyncSession, user_id: int) -> DailyCode:
    """Возвращает существующий или создает новый код на сегодня для пользователя"""
    today = datetime.now().date()

    code_entry = await session.execute(
        select(DailyCode).where(
            DailyCode.user_id == user_id,
            DailyCode.date == today
        )
    )
    code_entry = code_entry.scalar_one_or_none()

    if not code_entry:
        code = generate_numeric_code()
        new_code = DailyCode(
            code=code,
            user_id=user_id,
            date=datetime.now(),
            is_used=False
        )
        session.add(new_code)
        await session.commit()
        code_entry = new_code

    return code_entry