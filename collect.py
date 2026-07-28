"""Оркестратор агентского режима АКГ.

  python collect.py --login                  разовый ручной логин в кабинеты
  python collect.py --all                    все каналы за последнюю завершённую неделю
  python collect.py --channels vk,dzen --week 2026-W30
"""
import argparse
import sys
import traceback

from playwright.sync_api import sync_playwright

import config
from core.browser import open_profile
from core.period import last_completed_week, parse_week
from core.registry_rows import to_registry_rows
from core.report import render_console, write_summary_csv, write_summary_md
from core.report_trigger import trigger_report
from core.result import ChannelResult, write_result
from core.webhook import post_rows


def do_login() -> None:
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for url in config.LOGIN_TABS:
            ctx.new_page().goto(url)
        print("Залогиньтесь во всех вкладках, затем закройте окно браузера.")
        ctx.pages[0].wait_for_event("close", timeout=0)


def run_channel(name: str, ctx, week, start, end,
                vk_community=None, dzen_account=None) -> list[ChannelResult]:
    # импорт внутри: падение одного модуля не валит остальные.
    # Возвращаем список: ВК за один заход может дать несколько сообществ.
    if name == "dzen":
        from channels.dzen import collect as fn
        return [fn(ctx, week=week, start=start, end=end,
                   out_dir=config.OUT_DIR / week, account=dzen_account)]
    elif name == "vk":
        from channels.vk import collect_all
        return collect_all(ctx, week=week, start=start, end=end,
                           out_dir=config.OUT_DIR / week, only=vk_community)
    elif name == "tenchat":
        from channels.tenchat import collect as fn
        return [fn(ctx, week=week, start=start, end=end, out_dir=config.OUT_DIR / week)]
    else:
        raise ValueError(f"unknown channel {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--channels", default="")
    ap.add_argument("--week", default=None, help="напр. 2026-W30")
    ap.add_argument("--vk-community", default=None,
                    help="собрать только одно ВК-сообщество из config communities "
                         "(ключ); по умолчанию — все сообщества за один заход")
    ap.add_argument("--dzen-account", default=None,
                    help="кабинет Дзена из config accounts (напр. 1 или 2)")
    ap.add_argument("--report", action="store_true",
                    help="сформировать и отправить PDF-отчёт (через native-эндпоинт)")
    args = ap.parse_args()

    if args.login:
        do_login()
        return 0

    if args.report:
        if not config.REPORT_URL:
            print("AKG_REPORT_URL не задан — некуда слать команду отчёта")
            return 1
        week, start, end = parse_week(args.week) if args.week else last_completed_week()
        ok, msg = trigger_report(config.REPORT_URL, config.WEBHOOK_KEY, week)
        print(f"Отчёт {week}: {'ok' if ok else 'СБОЙ'} — {msg}")
        return 0 if ok else 1

    names = list(config.CHANNELS) if args.all else [
        c.strip() for c in args.channels.split(",") if c.strip()]
    if not names:
        ap.error("укажите --login, --all или --channels")

    week, start, end = parse_week(args.week) if args.week else last_completed_week()
    out_dir = config.OUT_DIR / week
    print(f"Период: {week} ({start} — {end})")

    results = []
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for name in names:
            try:
                batch = run_channel(name, ctx, week, start, end,
                                    vk_community=args.vk_community, dzen_account=args.dzen_account)
            except Exception as e:                      # канал упал — фиксируем и едем дальше
                traceback.print_exc()
                batch = [ChannelResult(
                    channel=name, week=week,
                    period_from=start.isoformat(), period_to=end.isoformat(),
                    status="failed", error=f"{type(e).__name__}: {e}")]
            for res in batch:
                write_result(res, out_dir)
                results.append(res)
        ctx.close()

    # Читаемая сводка в консоль + файлы summary.md / summary.csv
    print(render_console(results, week, start, end, out_dir))
    write_summary_md(results, week, start, end, out_dir)
    csv_path = write_summary_csv(results, week, out_dir)
    print(f"Сводка: {csv_path.parent / 'summary.md'} · {csv_path}")

    # Отправка строк в Реестр_факта, если настроен вебхук
    if config.WEBHOOK_URL:
        rows = to_registry_rows(results, week, start, end)
        if rows:
            ok, msg = post_rows(config.WEBHOOK_URL, config.WEBHOOK_KEY, week, rows)
            print(f"\nОтправка в Реестр_факта: {'ok' if ok else 'СБОЙ'} "
                  f"({len(rows)} строк) — {msg}")
        else:
            print("\nОтправка в Реестр_факта: нет строк (нет каналов в статусе ok)")

    return 0 if all(r.status == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
