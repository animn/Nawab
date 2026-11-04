#!/bin/sh
set -eu

# Private database, originals and derived clips must not be world-readable.
umask 077
port=${PORT:-8000}
case "$port" in
  ''|*[!0-9]*) echo 'PORT must be an integer from 1 to 65535.' >&2; exit 1 ;;
esac
if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
  echo 'PORT must be an integer from 1 to 65535.' >&2
  exit 1
fi

# Set only to the hosting provider's verified proxy IPs/CIDRs. Never trust all
# clients, even when a public edge normally terminates HTTPS.
trusted_proxies=${FORWARDED_ALLOW_IPS:-127.0.0.1}
case "$trusted_proxies" in
  *\**) echo 'Wildcard proxy trust is not permitted.' >&2; exit 1 ;;
esac

# SQLite queue ownership and interrupted-job recovery require exactly one worker.
exec uvicorn api.main:app --host 0.0.0.0 --port "$port" --workers 1 \
  --proxy-headers --forwarded-allow-ips "$trusted_proxies"
