"""Единый персистентный браузер-профиль (Яндекс.Браузер). Все каналы работают в нём."""
from playwright.sync_api import BrowserContext
from config import PROFILE_DIR, BROWSER_EXECUTABLE


def open_profile(pw, headless: bool = False) -> BrowserContext:
    PROFILE_DIR.mkdir(exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        executable_path=BROWSER_EXECUTABLE,
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
