#!/usr/bin/env python3
"""Отправка owner-report PDF по SMTP с отдельного ящика (замена Apps Script).

Тянет детальный (+ опц. краткую) PDF из native storage за неделю и шлёт письмом.
Креды/получатели — из .report_env рядом (KEY=VALUE, вне git):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
  REPORT_TO, REPORT_CC (опц.), SHARED_KEY, STORAGE_URL
STORAGE_URL — native /webhook/akg-owner-report (без ?): PDF тянется ?key=&week=&variant=.

Печатает машиночитаемый статус: SENT=1/0, при ошибке ERROR=...
"""
import argparse
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path


def load_env(path: str) -> dict:
    env = {}
    p = Path(path)
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def fetch_pdf(storage_url: str, key: str, week: str, variant: str) -> bytes | None:
    url = f"{storage_url}?key={urllib.parse.quote(key)}&week={urllib.parse.quote(week)}"
    if variant:
        url += f"&variant={variant}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            ct = (r.headers.get("Content-Type", "") or "").lower()
            if r.status == 200 and "application/pdf" in ct:
                return r.read()
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--env", default=str(Path(__file__).parent / ".report_env"))
    ap.add_argument("--to", help="переопределить получателя (для теста)")
    a = ap.parse_args()

    env = load_env(a.env)
    key = env.get("SHARED_KEY", "")
    storage = env.get("STORAGE_URL", "")
    if not (key and storage):
        print("SENT=0 ERROR=no_env (SHARED_KEY/STORAGE_URL)")
        return 2

    det = fetch_pdf(storage, key, a.week, "")
    if not det:
        print(f"SENT=0 ERROR=no_detailed_pdf week={a.week}")
        return 2
    mini = fetch_pdf(storage, key, a.week, "mini")

    to = a.to or env.get("REPORT_TO", "")
    if not to:
        print("SENT=0 ERROR=no_recipient")
        return 2
    cc = "" if a.to else env.get("REPORT_CC", "")

    msg = EmailMessage()
    msg["From"] = env.get("SMTP_FROM", env.get("SMTP_USER", ""))
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = f"Капитал · Маркетинг — отчёт за {a.week}"
    body = ["Здравствуйте,", "", "Во вложении — еженедельный отчёт по маркетингу:"]
    if mini:
        body.append("  • «Краткая сводка» — главные цифры на одной странице;")
    body += ["  • «Детальный отчёт» — полная разбивка по каналам и план/факт.", "",
             "Цифры берутся из листа «Реестр_факта» рабочей таблицы маркетинга.", "",
             "С уважением,", "отдел маркетинга «Капитал»"]
    msg.set_content("\n".join(body))
    if mini:
        msg.add_attachment(mini, maintype="application", subtype="pdf",
                           filename=f"Капитал_краткая_сводка_{a.week}.pdf")
    msg.add_attachment(det, maintype="application", subtype="pdf",
                       filename=f"Капитал_детальный_отчёт_{a.week}.pdf")

    host = env.get("SMTP_HOST", "")
    port = int(env.get("SMTP_PORT", "465"))
    recips = [to] + ([c.strip() for c in cc.split(",") if c.strip()] if cc else [])
    try:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
            s.login(env.get("SMTP_USER", ""), env.get("SMTP_PASS", ""))
            s.send_message(msg, to_addrs=recips)
    except Exception as e:
        print(f"SENT=0 ERROR=smtp:{type(e).__name__}:{e}")
        return 3
    print(f"SENT=1 TO={to} MINI={'1' if mini else '0'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
