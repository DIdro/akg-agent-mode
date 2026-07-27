#!/usr/bin/env bash
# Генерация PDF за неделю + отправка. Вызывается по ssh с native-эндпоинта
# generate-report (5.187 → 178). Печатает машиночитаемый статус в одну строку:
#   GENERATED=1 SENT=1   |   GENERATED=0 ... ERROR=...
# Аргумент: $1 = неделя YYYY-Www. $2 (опц.) = тестовый получатель (--to).
#
# 178 периодически ловит DNS-флап (резолв crm-techno) — генерация/upload падают
# случайно. Поэтому генерация обёрнута в ретрай: повторяем inject+make_report
# --upload, пока PDF реально не окажется в storage (проверка curl), и ТОЛЬКО
# после этого шлём один раз (без риска дублей писем).
set -o pipefail
cd /home/mariiastar/AKG/owner-report-pipeline || { echo "GENERATED=0 SENT=0 ERROR=no_dir"; exit 2; }

WEEK="$1"
TEST_TO="$2"
[ -z "$WEEK" ] && { echo "GENERATED=0 SENT=0 ERROR=no_week"; exit 2; }

source /home/mariiastar/AKG/.venv_pw/bin/activate 2>/dev/null
# SHARED_KEY и STORAGE_URL берём из .report_env (единый источник, в git — нет).
set -a; source ./.report_env 2>/dev/null; set +a

XLSX="/home/mariiastar/AKG/План-факт отдела маркетинга Капитала_2026.xlsx"

# Одна попытка генерации: дотянуть целевую неделю из вебхука, вклеить в снэпшот,
# сгенерить det+mini PDF и загрузить в native storage.
gen_once() {
    local merged rc=1
    merged=$(mktemp --suffix=.xlsx)
    python3 inject_week.py --xlsx "$XLSX" --out "$merged" --week "$WEEK" --key "$SHARED_KEY" \
        >/dev/null 2>&1 || cp "$XLSX" "$merged"
    python3 src/make_report.py --week "$WEEK" --xlsx "$merged" --upload >/dev/null 2>&1 && rc=0
    rm -f "$merged"
    return $rc
}

# Проверка, что детальный PDF реально доступен в storage (make_report может
# вернуть успех, а upload при флапе — нет).
pdf_in_storage() {
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' "${STORAGE_URL}?key=${SHARED_KEY}&week=${WEEK}")
    [ "$code" = "200" ]
}

GEN=""
for attempt in 1 2 3; do
    if gen_once && pdf_in_storage; then GEN="GENERATED=1"; break; fi
    sleep 2
done
[ -z "$GEN" ] && { echo "GENERATED=0 SENT=0 ERROR=make_report"; exit 3; }

# Отправка (send_report печатает SENT=1/0 ...). PDF уже подтверждён в storage.
if [ -n "$TEST_TO" ]; then
    SEND=$(python3 send_report.py --week "$WEEK" --to "$TEST_TO")
else
    SEND=$(python3 send_report.py --week "$WEEK")
fi
echo "$GEN $SEND"
