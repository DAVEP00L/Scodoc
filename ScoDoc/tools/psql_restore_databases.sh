#!/bin/bash

# aux script called by restore_scodoc_data.sh as "postgres" user
# DO NOT CALL DIRECTLY

PG_DUMPFILE=$1


# Drop all current ScoDoc databases, if any:
for f in $(psql -l --no-align --field-separator . | grep SCO | cut -f 1 -d.); do
  echo dropping "$f"
  dropdb "$f"
done
echo "Restoring postgres data..."
psql -f "$PG_DUMPFILE" postgres

