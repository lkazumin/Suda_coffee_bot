from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker
from suda_bot.models import DailyCode
from sqlalchemy import delete
from datetime import datetime, timedelta

_scheduler = None

async def cleanup_job(session_pool: async_sessionmaker):
    async with session_pool() as session:
        old_date = datetime.now() - timedelta(days=1)
        await session.execute(
            delete(DailyCode).where(
                DailyCode.date < old_date
            )
        )
        await session.commit()
    print("✅ Старые коды удалены")

def setup_scheduler(session_pool: async_sessionmaker):
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(cleanup_job, 'cron', hour=0, minute=0, args=[session_pool])
        _scheduler.start()
    return _scheduler

def get_scheduler():
    return _scheduler