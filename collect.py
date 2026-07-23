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
from core.result import ChannelResult, write_result


def do_login() -> None:
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for url in config.LOGIN_TABS:
            ctx.new_page().goto(url)
        print("Залогиньтесь во всех вкладках, затем закройте окно браузера.")
        ctx.pages[0].wait_for_event("close", timeout=0)


def run_channel(name: str, ctx, week, start, end) -> ChannelResult:
    # импорт внутри: падение одного модуля не валит остальные
    if name == "dzen":
        from channels.dzen import collect as fn
    elif name == "vk":
        from channels.vk import collect as fn
    elif name == "tenchat":
        from channels.tenchat import collect as fn
    else:
        raise ValueError(f"unknown channel {name}")
    return fn(ctx, week=week, start=start, end=end,
              out_dir=config.OUT_DIR / week)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--channels", default="")
    ap.add_argument("--week", default=None, help="напр. 2026-W30")
    args = ap.parse_args()

    if args.login:
        do_login()
        return 0

    names = list(config.CHANNELS) if args.all else [
        c.strip() for c in args.channels.split(",") if c.strip()]
    if not names:
        ap.error("укажите --login, --all или --channels")

    week, start, end = parse_week(args.week) if args.week else last_completed_week()
    out_dir = config.OUT_DIR / week
    print(f"Период: {week} ({start} — {end})")

    summary = {}
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for name in names:
            try:
                res = run_channel(name, ctx, week, start, end)
            except Exception as e:                      # канал упал — фиксируем и едем дальше
                traceback.print_exc()
                res = ChannelResult(
                    channel=name, week=week,
                    period_from=start.isoformat(), period_to=end.isoformat(),
                    status="failed", error=f"{type(e).__name__}: {e}")
            write_result(res, out_dir)
            summary[name] = res.status
        ctx.close()

    print("\n=== Итог ===")
    for name, status in summary.items():
        print(f"  {name:8s} {status}")
    return 0 if all(s == "ok" for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
