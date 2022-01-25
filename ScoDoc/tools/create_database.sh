#!/bin/bash

# Create database for ScoDoc
# This script must be executed as user "scodoc"

die() {
  echo 
  echo "Erreur: $1"
  echo
  exit 1
}
[ $# = 1 ] || die "Usage $0 db_name"
db_name="$1"

# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR"/config.sh || die "config.sh not found, exiting"
source "$SCRIPT_DIR"/utils.sh || die "config.sh not found, exiting"

[ "$USER" = "$SCODOC_USER" ] || die "$0 must run as user $SCODOC_USER"

# ---
echo 'Creating postgresql database ' "$db_name"
createdb -E UTF-8  -p "$POSTGRES_PORT" -O "$POSTGRES_USER" "$db_name"

