#!/bin/bash

# Initialize database (create tables) for a ScoDoc instance
# This script must be executed as user scodoc
#
# $db_name and $DEPT passed as environment variables

# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

if [ "$(id -nu)" != "$SCODOC_USER" ]
then
 echo "$0: script must be runned as user $SCODOC_USER"
 exit 1
fi

# shellcheck disable=SC2154
echo 'Initializing tables in database ' "$db_name"
$PSQL -U "$POSTGRES_USER" -p "$POSTGRES_PORT" "$db_name" -f "$SCODOC_DIR"/misc/createtables.sql


# Set DeptName in preferences:
echo "insert into sco_prefs (name, value) values ('DeptName', '"${DEPT}\'\) | $PSQL -U "$POSTGRES_USER"  -p "$POSTGRES_PORT" "$db_name"
