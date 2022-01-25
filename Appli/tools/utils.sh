#!/bin/bash
# Misc utilities for ScoDoc install shell scripts

to_lower() {
  echo "$1" | tr "[:upper:]" "[:lower:]" 
} 

to_upper() {
  echo "$1" | tr "[:lower:]" "[:upper:]" 
} 

norm_ans() {
  x=$(to_upper "$1" | tr O Y)
  echo "${x:0:1}"
}

check_uid_root() {
  if [ "$UID" != "0" ] 
  then
    echo "Erreur: le script $1 doit etre lance par root"
    exit 1
  fi
}

terminate() {
  status=${2:-1} # default: exit 1
  echo 
  echo "Erreur: $1"
  echo
  exit $status
}

# Start/stop scodoc, using sysv or systemd
scodocctl() {
  if [ "$1" = "start" ]; then
    echo "Starting ScoDoc..."
  elif [ "$1" = "stop" ]; then
    echo "Stopping ScoDoc"
  else
    echo "Error: invalid argument for scodocctl"
    exit 1
  fi
  if [ -e  /etc/systemd/system/scodoc.service ]
  then
     systemctl $1 scodoc
  else
    echo "(using legacy SystemV)"
    /etc/init.d/scodoc "$1"
  fi
}

# --- Ensure postgres user scodoc exists
init_postgres_user() { # run as root
  if [ -z $(echo "select usename from pg_user;" | su -c "(cd; $PSQL -d template1  -p $POSTGRES_PORT)" "$POSTGRES_SUPERUSER" | grep "$POSTGRES_USER") ]
  then
   # add database user
   echo "Creating postgresql user $POSTGRES_USER"
   su -c "(cd; createuser  -p $POSTGRES_PORT --createdb --no-superuser --no-createrole ${POSTGRES_USER})" "$POSTGRES_SUPERUSER"
  fi
}

# --- Ensure Unix user "scodoc" exists
check_create_scodoc_user() {
    if ! id -u "${SCODOC_USER}" &> /dev/null
    then
        echo "Creating unix user ${SCODOC_USER}"
        adduser --shell /bin/bash --disabled-password --gecos "ScoDoc service" "${SCODOC_USER}" || die "failed to create user"
    else
        echo "Unix user ${SCODOC_USER} exists"
    fi
    # Check / set FLASK_APP
    scodoc_home=$(getent passwd "${SCODOC_USER}" | cut -d: -f 6)
    if [ -e "$scodoc_home/.profile" ] && [ $(grep -c FLASK_APP "$scodoc_home/.profile") == 0 ]
    then
      echo "export FLASK_APP=scodoc.py" >> "$scodoc_home/.profile"
    fi
}

# --- Give all ScoDoc files (/opt/scodoc) to user "scodoc":
change_scodoc_file_ownership() {
  echo "Changing owner of ${SCODOC_DIR} to ${SCODOC_USER}"
  chown -R "${SCODOC_USER}:${SCODOC_GROUP}" "${SCODOC_DIR}" || die "change_scodoc_file_ownership failed on ${SCODOC_DIR}"
}

# Création du répertoire local (scodoc-data) et vérification du propriétaire
set_scodoc_var_dir() {
  echo "Checking $SCODOC_VAR_DIR..."
  [ -z ${SCODOC_VAR_DIR+x} ] && die "Error: env var SCODOC_VAR_DIR not set"
  [ -d "$SCODOC_VAR_DIR" ] || mkdir "$SCODOC_VAR_DIR" || die "can't create $SCODOC_VAR_DIR directory"
  for d in archives photos tmp log config certs config/version config/depts config/logos
  do
    [ -d "$SCODOC_VAR_DIR/$d" ] || mkdir "$SCODOC_VAR_DIR/$d" || die "can't create $SCODOC_VAR_DIR/$d subdirectory"
  done
  chown -R "${SCODOC_USER}:${SCODOC_GROUP}" "${SCODOC_VAR_DIR}" || die "change_scodoc_file_ownership failed on ${SCODOC_VAR_DIR}"
}


# XXX inutilise 
gen_passwd() { 
  PASSWORD_LENGTH="8"
  ALLOWABLE_ASCII="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%^&*()_+=-?><"
  SEED=$(head -c4 /dev/urandom | od -t u4 | awk '{ print $2 }')
  RANDOM=$SEED
  n=1
  password=""
  while [ "$n" -le "$PASSWORD_LENGTH" ]
  do
    password="$password${ALLOWABLE_ASCII:$((RANDOM%${#ALLOWABLE_ASCII})):1}"
    n=$((n+1))
  done
  echo "$password"
}
