"""Локальный оверрайд конфигурации — скопируй в config_local.py (он вне git).

config.py в конце делает `from config_local import *`, поэтому любые имена,
заданные здесь, переопределяют дефолты. Задавай только то, что отличается.

Пример ниже — под кабинеты клиента (АКГ «Капитал»). URL/скрины сверить с
клиентом: часть значений из внутренней памяти проекта, могли измениться.
"""

# --- Браузер ---
# На обычной машине без Amnezia строку можно НЕ задавать вовсе — тогда
# возьмётся встроенный playwright-chromium. Задай путь, только если нужен
# конкретный браузер (например, Яндекс.Браузер для обхода VPN):
# BROWSER_EXECUTABLE = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"

# --- Кабинеты клиента ---
# Один ключ канала = один кабинет. Для теста берём по одному основному на канал.
# Дзен: нужен доступ в Студию (аккаунт с правами редактора канала) — логинится
#   под ним при collect.py --login. public_url — публичная страница канала,
#   из её последнего сегмента берётся publisherId для экспорта XLSX.
# ВК: screen_name — короткое имя сообщества (vk.ru/<screen_name>), аккаунт
#   логина должен быть админом сообщества (иначе дашборд статистики не откроется).
# Тенчат: public_url — свой профиль клиента (кнопка статистики видна владельцу).
CHANNELS = {
    "dzen":    {"public_url": "https://dzen.ru/osnova_capital"},          # сверить
    "vk":      {"public_url": "https://vk.ru/agcapital", "screen_name": "agcapital"},  # сверить
    "tenchat": {"public_url": "https://tenchat.ru/<профиль-клиента>"},    # уточнить у клиента
}

LOGIN_TABS = [
    "https://dzen.ru/profile/editor",
    "https://vk.ru/agcapital",
    "https://tenchat.ru/auth",
]

# --- Запись в Реестр_факта (опционально) ---
# Куда агент шлёт готовые строки. Секрет — через env (не в git):
#   $env:AKG_WEBHOOK_URL = "https://n8n.crm-techno.ru/native/webhook/agent-metrics"
#   $env:AKG_WEBHOOK_KEY = "<секрет>"
# либо задать здесь (config_local.py вне git):
# WEBHOOK_URL = "https://n8n.crm-techno.ru/native/webhook/agent-metrics"
# WEBHOOK_KEY = "..."

# Имена каналов в колонке F «Канал (детальный)» реестра клиента.
# dzen/tenchat — строка; vk — dict по вкладкам (сообщество/блог/видео).
# CHANNELS["dzen"]["registry"] = "Корп. блог Дзен"        # или "Дзен ЛБ"
# CHANNELS["tenchat"]["registry"] = "Тенчат ЛБ"

# --- ВК: несколько аккаунтов клиента (--vk-account N) ---
# У клиента два ВК-сообщества под разными аккаунтами. Анна собирает по одному
# с перелогином: collect.py --channels vk --vk-account 1, затем ...--vk-account 2.
# У каждого аккаунта — свои сообщества и их registry-имена (колонка F).
# CHANNELS["vk"]["accounts"] = {
#     "1": {"screen": "agcapital",
#           "registry": {"community": "Корп. ВК-сообщество",
#                        "channel": "Корп. ВК блог", "video": "Корп. ВК-видео"}},
#     "2": {"screen": "irina.ekimovskih",
#           "registry": {"community": "ВК ЛБ"}},  # у ЛБ обычно только сообщество
# }

# --- Дзен: несколько кабинетов клиента (--dzen-account N) ---
# У клиента два Дзен-канала под разными Яндекс-аккаунтами (корп. блог + ЛБ).
# Анна собирает по одному с перелогином: collect.py --channels dzen --dzen-account 1,
# затем перелогин в другой Яндекс-аккаунт и ...--dzen-account 2.
# У каждого кабинета — свой public_url (из него берётся publisherId) и своё
# registry-имя (строка, колонка F). Логиниться нужно под аккаунтом с правами
# редактора соответствующего канала (доступ в Студию).
# CHANNELS["dzen"]["accounts"] = {
#     "1": {"public_url": "https://dzen.ru/osnova_capital", "registry": "Корп. блог Дзен"},
#     "2": {"public_url": "https://dzen.ru/ekimovskih",     "registry": "Дзен ЛБ"},
# }
