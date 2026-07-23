import os
from pathlib import Path

ROOT = Path(__file__).parent
PROFILE_DIR = ROOT / "profile"
OUT_DIR = ROOT / "out"

WEBHOOK_URL = None  # тестовая фаза: никуда не шлём

# Путь к браузеру. По умолчанию — Яндекс.Браузер (нужен на машинах с Amnezia:
# он в bypass VPN, playwright-chromium ходил бы через туннель). Если файла по
# этому пути нет (обычная машина без Amnezia/без Яндекса) — browser.py возьмёт
# встроенный playwright-chromium. Переопределить: env AKG_BROWSER_EXECUTABLE.
BROWSER_EXECUTABLE = os.environ.get(
    "AKG_BROWSER_EXECUTABLE",
    r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
)

# Кабинеты по умолчанию — тестовые кабинеты Alex'а. Для другой машины/клиента
# переопределяются в config_local.py (см. config_local.example.py) — он вне git.
CHANNELS = {
    "dzen":    {"public_url": "https://dzen.ru/id/69a6a56804c3ba5d0aadf101"},
    "vk":      {"public_url": "https://vk.ru/nppsatek", "screen_name": "nppsatek"},
    "tenchat": {"public_url": "https://tenchat.ru/2418763"},
}

# Вкладки для разового ручного логина (collect.py --login).
LOGIN_TABS = [
    "https://dzen.ru/profile/editor",
    "https://vk.ru/nppsatek",
    "https://tenchat.ru/auth",
]

# Локальный оверрайд (config_local.py — вне git): путь к браузеру, кабинеты
# клиента, login-вкладки. Всё, что задано там, переопределяет дефолты выше.
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
