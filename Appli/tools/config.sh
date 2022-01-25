#!/bin/bash
# Version majeure de Debian (..., 9, 10)
debian_version=$(cat /etc/debian_version)
debian_version=${debian_version%%.*}

die() {
  echo 
  echo "Erreur: $1"
  echo
  exit 1
}

# Fix path
export PATH="${PATH}":/usr/sbin:/sbin

# ScoDoc: environment variables
umask 0022

export SCODOC_DIR=/opt/scodoc
export SCODOC_VAR_DIR=/opt/scodoc-data 

export SCODOC_VERSION_DIR="${SCODOC_VAR_DIR}/config/version"
export SCODOC_LOGOS_DIR="${SCODOC_VAR_DIR}/config/logos"

export FLASK_APP=scodoc.py

# Unix user running ScoDoc server:
export SCODOC_USER=scodoc
export SCODOC_GROUP=root

# Postgresql normal user: (same as unix user)
# IMPORTANT: must match SCO_DEFAULT_SQL_USER defined in sco_utils.py
export POSTGRES_USER="$SCODOC_USER"
# Postgresql superuser:
export POSTGRES_SUPERUSER=postgres

export SCODOC_DB_PROD="SCODOC"
export SCODOC_DB_DEV="SCODOC_DEV"
export SCODOC_DB_TEST="SCODOC_TEST"


# psql command: if various versions installed, force the one we want:
if [ "${debian_version}" = "11" ]
then
 PSQL=/usr/lib/postgresql/13/bin/psql
 export POSTGRES_SERVICE="postgresql@11-main.service"
else
   die "unsupported Debian version"
fi
export PSQL

# tcp port for SQL server 
# Important note: if changed, you should probably also change it in
#      sco_utils.py (SCO_DEFAULT_SQL_PORT).
export POSTGRES_PORT=5432

# ---
#echo "SCODOC_USER=$SCODOC_USER"
#echo "SCODOC_DIR=$SCODOC_DIR"
#echo "SCODOC_VAR_DIR=$SCODOC_VAR_DIR"
