from sqlalchemy import Column, Integer, String, DateTime, Boolean
from suda_bot.database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    points = Column(Integer, default=0)
    last_check_in = Column(DateTime, nullable=True)
    is_free_drink_used = Column(Boolean, default=False)

class DailyCode(Base):
    __tablename__ = 'daily_codes'

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)