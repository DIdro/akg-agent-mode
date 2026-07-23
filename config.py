from pathlib import Path

ROOT = Path(__file__).parent
PROFILE_DIR = ROOT / "profile"
OUT_DIR = ROOT / "out"

WEBHOOK_URL = None  # тестовая фаза: никуда не шлём

CHANNELS = {
    "dzen":    {"public_url": "https://dzen.ru/id/69a6a56804c3ba5d0aadf101"},
    "vk":      {"public_url": "https://vk.ru/nppsatek", "screen_name": "nppsatek"},
    "tenchat": {"public_url": "https://tenchat.ru/2418763"},
}

LOGIN_TABS = [
    "https://dzen.ru/profile/editor",
    "https://vk.ru/nppsatek",
    "https://tenchat.ru/auth",
]
