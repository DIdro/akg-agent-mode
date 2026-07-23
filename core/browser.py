"""Единый персистентный браузер-профиль. Все каналы работают в нём.

Браузер: config.BROWSER_EXECUTABLE, если такой файл есть (Яндекс.Браузер на
машинах с Amnezia — в обход VPN); иначе встроенный playwright-chromium.
"""
from pathlib import Path

from playwright.sync_api import BrowserContext
from config import PROFILE_DIR, BROWSER_EXECUTABLE


def _resolve_executable() -> str | None:
    """Путь к браузеру, если файл существует, иначе None → bundled chromium."""
    if BROWSER_EXECUTABLE and Path(BROWSER_EXECUTABLE).exists():
        return BROWSER_EXECUTABLE
    return None


def open_profile(pw, headless: bool = False) -> BrowserContext:
    PROFILE_DIR.mkdir(exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        executable_path=_resolve_executable(),
        headless=headless,
        viewport={"width": 1440, "height": 900},
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        args=[
            "--disable-blink-features=AutomationControlled",
            # не восстанавливать вкладки прошлой сессии: иначе накопленные
            # вкладки ВК упираются в лимит одновременных сессий дашборда
            # и статистика отдаёт «Не удалось загрузить данные».
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ],
    )
    # Закрываем всё, что браузер всё же восстановил, оставляя один чистый лист —
    # каналы работают в своих ctx.new_page(), лишние вкладки не должны висеть.
    keep = ctx.new_page()
    for pg in list(ctx.pages):
        if pg is not keep:
            try:
                pg.close()
            except Exception:
                pass
    return ctx
