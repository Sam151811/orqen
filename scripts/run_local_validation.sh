#!/usr/bin/env bash
# Exercises the real openai_compatible path end to end against a local gateway
# that rate-limits and errors on purpose. If this passes, the only untested
# variable against a real provider is the network itself.
set -euo pipefail
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost
export ORQEN_PROVIDER=openai_compatible
export ORQEN_BASE_URL=http://127.0.0.1:8899/v1
export ORQEN_API_KEY=test-key
export ORQEN_EMBED_PROVIDER=openai_compatible
export ORQEN_EMBED_BASE_URL=http://127.0.0.1:8899/v1
export ORQEN_EMBED_API_KEY=test-key
export ORQEN_DB=cohort.db

python3 scripts/fake_gateway.py 8899 & GW=$!
trap 'kill $GW 2>/dev/null || true' EXIT
sleep 1

rm -f "$ORQEN_DB" data/thresholds.json
python3 -m orqen.incidents.ingest data/incidents.seed.jsonl
printf '%s\n' ref/steady-7b ref/biased-7b ref/erratic-7b ref/overconf-7b ref/memoriser-7b ref/cautious-7b > /tmp/cohort.txt
python3 scripts/reference_cohort.py --models /tmp/cohort.txt --out data/cohort.json
python3 scripts/derive_thresholds.py --cohort data/cohort.json --out data/thresholds.json
echo "--- re-grading against derived thresholds ---"
python3 -m orqen.cli check ref/biased-7b || true
