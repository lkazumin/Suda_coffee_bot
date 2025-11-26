from aiogram import BaseMiddleware
from typing import Callable, Dict, Any
from sqlalchemy.ext.asyncio import async_sessionmaker

class DatabaseSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable,
        event: object,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            return await handler(event, data)