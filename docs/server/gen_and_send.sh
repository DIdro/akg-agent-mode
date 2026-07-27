#!/usr/bin/env bash
# Генерация PDF за неделю + отправка. Вызывается по ssh с native-эндпоинта
# generate-report (5.187 → 178). Печатает машиночитаемый статус в одну строку:
#   GENERATED=1 SENT=1   |   GENERATED=0 ... ERROR=...
# Аргумент: $1 = неделя YYYY-Www. $2 (опц.) = тестовый получатель (--to).
set -o pipefail
cd /home/mariiastar/AKG/owner-report-pipeline || { echo "GENERATED=0 SENT=0 ERROR=no_dir"; exit 2; }

WEEK="$1"
TEST_TO="$2"
[ -z "$WEEK" ] && { echo "GENERATED=0 SENT=0 ERROR=no_week"; exit 2; }

source /home/mariiastar/AKG/.venv_pw/bin/activate 2>/dev/null

XLSX="/home/mariiastar/AKG/План-факт отдела маркетинга Капитала_2026.xlsx"
SHARED_KEY='<SHARED_KEY>'   # реальный ключ на сервере; в git — плейсхолдер

# Дотянуть целевую неделю из вебхука и вклеить в снэпшот (как run_weekly).
MERGED=$(mktemp --suffix=.xlsx)
python3 inject_week.py --xlsx "$XLSX" --out "$MERGED" --week "$WEEK" --key "$SHARED_KEY" \
    >/dev/null 2>&1 || cp "$XLSX" "$MERGED"

# Генерация PDF (det+mini) + upload в native storage.
if python3 src/make_report.py --week "$WEEK" --xlsx "$MERGED" --upload >/dev/null 2>&1; then
    GEN="GENERATED=1"
else
    rm -f "$MERGED"; echo "GENERATED=0 SENT=0 ERROR=make_report"; exit 3
fi
rm -f "$MERGED"

# Отправка (send_report печатает SENT=1/0 ...).
if [ -n "$TEST_TO" ]; then
    SEND=$(python3 send_report.py --week "$WEEK" --to "$TEST_TO")
else
    SEND=$(python3 send_report.py --week "$WEEK")
fi
echo "$GEN $SEND"
