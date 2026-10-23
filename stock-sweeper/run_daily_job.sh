#!/usr/bin/env zsh
# Daily automated wrapper for Stock Sweeper (invoked by macOS launchd on boot/login and daily check).
# Ensures the full pipeline runs at most once per calendar day after network connectivity is available.

set -euo pipefail

PROJECT_DIR="/Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper"
LOG_DIR="${PROJECT_DIR}/logs"
STAMP_FILE="${LOG_DIR}/.last_daily_run_date"
LOG_FILE="${LOG_DIR}/daily_pipeline.log"

mkdir -p "${LOG_DIR}"
cd "${PROJECT_DIR}"

TODAY=$(date +%Y-%m-%d)

if [[ -f "${STAMP_FILE}" ]] && [[ "$(cat "${STAMP_FILE}")" == "${TODAY}" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stock Sweeper already completed today (${TODAY}). Skipping." >> "${LOG_FILE}"
    exit 0
fi

# Wait up to 60 seconds after boot/wake for network DNS to come online
for i in {1..12}; do
    if /sbin/ping -c 1 -t 3 query1.finance.yahoo.com >/dev/null 2>&1 || /usr/bin/nc -z -G 3 1.1.1.1 53 >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

echo "====================================================================" >> "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Daily Stock Sweeper Pipeline (${TODAY})" >> "${LOG_FILE}"
echo "====================================================================" >> "${LOG_FILE}"

export HEADLESS=1
export PYTHONUNBUFFERED=1

if "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/run_pipeline.py" >> "${LOG_FILE}" 2>&1; then
    echo "${TODAY}" > "${STAMP_FILE}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily Stock Sweeper Pipeline succeeded (${TODAY})." >> "${LOG_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [!] Daily Stock Sweeper Pipeline exited with an error." >> "${LOG_FILE}"
    exit 1
fi
