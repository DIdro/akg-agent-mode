"""Единый персистентный Chromium-профиль. Все каналы работают в нём."""
from playwright.sync_api import sync_playwright, BrowserContext
from config import PROFILE_DIR


def open_profile(pw, headless: bool = False) -> BrowserContext:
    PROFILE_DIR.mkdir(exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1440, "height": 900},
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        args=["--disable-blink-features=AutomationControlled"],
    )
