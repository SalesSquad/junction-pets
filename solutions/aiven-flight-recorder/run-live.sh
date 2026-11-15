#!/bin/zsh
# Live flight-recorder run against the disposable demo services fr-demo-kafka / fr-demo-pg.
# Put these files in ./creds (Aiven Console -> service -> Connection information):
#   creds/ca.pem        project CA certificate (same file for Kafka and PostgreSQL)
#   creds/service.cert  fr-demo-kafka access certificate
#   creds/service.key   fr-demo-kafka access key
#   creds/pg.url        fr-demo-pg Service URI (one line)
set -euo pipefail
cd "${0:A:h}"
for f in ca.pem service.cert service.key pg.url; do [[ -s creds/$f ]] || { echo "missing creds/$f"; exit 1; }; done
chmod 600 creds/*
export AIVEN_KAFKA_BROKER="fr-demo-kafka-ssquad-8702.h.aivencloud.com:25614"
export AIVEN_KAFKA_TOPIC="flight-recorder-run1"
export AIVEN_KAFKA_CA="$PWD/creds/ca.pem" AIVEN_KAFKA_CERT="$PWD/creds/service.cert" AIVEN_KAFKA_KEY="$PWD/creds/service.key"
export AIVEN_PG_CA="$PWD/creds/ca.pem"
export AIVEN_PG_URL="$(tr -d '\n' < creds/pg.url)"
node cli.mjs --live | tee "result-live-$(date +%Y%m%dT%H%M%S).json"
