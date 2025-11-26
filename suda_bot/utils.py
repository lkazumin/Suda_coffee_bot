import secrets
from datetime import date

def generate_numeric_code() -> str:
    """Генерирует 6-значный код только из цифр"""
    return f"{secrets.randbelow(10**6):06d}"

def generate_short_code() -> str:
    """Генерирует 6-символьный код из цифр и букв (для совместимости)"""
    return secrets.token_hex(3).upper()[:6]