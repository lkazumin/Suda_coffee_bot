import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Список ID бариста
BARISTA_TELEGRAM_IDS = os.getenv("BARISTA_TELEGRAM_IDS", "").split(",")