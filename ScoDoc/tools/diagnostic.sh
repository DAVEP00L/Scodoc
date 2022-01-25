#!/bin/bash

# Rassemble informations sur le systeme et l'installation ScoDoc pour 
# faciliter le support a distance.
#
# Avec option:
#    -a : sauve aussi les bases de données
#
set -euo pipefail
# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR"/config.sh || die "config.sh not found, exiting"

DEST_ADDRESS=emmanuel.viennet@gmail.com 

TMP=/tmp/scodoc-$(date +%F-%s)

SAVE_DB=0
SEND_BY_MAIL=1

# -------------------------------------
# Arguments
# -------------------------------------

function join_by { local IFS="$1"; shift; echo "$*"; }

while getopts "anh" opt; do
  case "$opt" in
      a)
	  SAVE_DB=1
	  ;;
      n)
	  SEND_BY_MAIL=0
	  ;;
      h)
	  echo "Diagnostic installation ScoDoc"
	  echo "Rassemble informations sur le systeme et l'installation ScoDoc"
	  echo "Usage: $0 [-h] [-n] [-a] [-u] [-d dept]"
	  echo "  -h  cette aide"
	  echo "  -n  pas d'envoi par mail"
	  echo "  -a  enregistre la bases de donnees (prod)"
	  echo "  -u  enregistre la base utilisateurs"
	  exit 0
	  ;;
      \?)
	  echo "Invalid option: -$OPTARG" >&2
	  exit 1
	  ;;
      :)
	  echo "Option -$OPTARG requires an argument." >&2
	  exit 1
	  ;;
  esac
done


# -------------------------------------
# Configuration
# -------------------------------------

# needed for uuencode
if [ ! -e /usr/bin/uuencode ]
then
   apt-get install sharutils
fi

mkdir "$TMP"

# Files to copy:
FILES="/etc/hosts /etc/debian_version /etc/apt /etc/apache2 $SCODOC_DIR/VERSION $SCODOC_VAR_DIR/config"


echo "ScoDoc diagnostic: informations about your system will be "
if [ "${SEND_BY_MAIL}" = "1" ]
then
    echo "sent to ${DEST_ADDRESS}"
    echo -n "and "
fi
echo "left in ${TMP}"


# -------------------------------------
# Logs
# -------------------------------------

mkdir "$TMP"/scodoc_logs/
cp "$SCODOC_VAR_DIR"/log/*.log "$TMP"/scodoc_logs/

# -------------------------------------
# Linux System Configuration
# -------------------------------------

iptables -L > "$TMP"/iptables.out
ip a > "$TMP"/ip-a.out
ps auxww > "$TMP"/ps.out
df -h > "$TMP"/df.out
dpkg -l > "$TMP"/dpkg.lst

(cd "$SCODOC_DIR"; git status > "$TMP"/git.status)
(cd "$SCODOC_DIR"; git diff > "$TMP"/git.diff)

(cd "$SCODOC_DIR"; git log -n 5 >  "$TMP"/git.log)
ls -laR "$SCODOC_DIR" > "$TMP"/ls-laR


# -------------------------------------
# Databases configurations
# -------------------------------------
(su postgres -c "psql -l") > "${TMP}/psql-l.out"

for db in "$SCODOC_DB_PROD" "$SCODOC_DB_DEV"
do
  (su postgres -c "echo '\dt' | psql $db") > "${TMP}/psql-$db).out"
done


# -------------------------------------
# Other system configuration files
# -------------------------------------
# copy files:
for f in $FILES 
do
    if [ -e "$f" ]
    then
        cp -R "$f" "$TMP"
    fi
done


# -------------------------------------
# Optionally save database
# -------------------------------------

# Dump database
function dump_db {
    
}

if [ "${SAVE_DB}" = "1" ]
then
    for db in "$SCODOC_DB_PROD" "$SCODOC_DB_DEV"
    do
        echo "Dumping database ${db}..."
        pg_dump --create "${db}") | gzip > "${TMP}/${db}.dump.gz"
        # may add archives ? (no, probably too big)
    done
fi

# -------------------------------------
# Archive all stuff to /tmp
# -------------------------------------

tar cfz "$TMP".tgz "$TMP"

echo
echo "Fichier de diagnostic:  "$TMP".tgz"
echo

# If no mail, stop here
if [ "${SEND_BY_MAIL}" = "0" ]
then
    exit 0
fi

# -------------------------------------
# Send by e-mail
# -------------------------------------


# Code below found on http://www.zedwood.com/article/103/bash-send-mail-with-an-attachment

#requires: basename,date,md5sum,sed,sendmail,uuencode
function fappend {
    echo "$2">>"$1";
}
YYYYMMDD=$(date +%Y%m%d)

# CHANGE THESE
TOEMAIL=$DEST_ADDRESS
FREMAIL="scodoc-diagnostic@none.org";
SUBJECT="ScoDoc 9 diagnostic - $YYYYMMDD";
MSGBODY="ScoDoc 9 diagnostic sent by diagnostic.sh";
ATTACHMENT="$TMP.tgz"
MIMETYPE="application/gnutar" #if not sure, use http://www.webmaster-toolkit.com/mime-types.shtml


# DON'T CHANGE ANYTHING BELOW
TMP="/tmp/tmpfil_123"$RANDOM;
BOUNDARY=$(date +%s|md5sum)
BOUNDARY=${BOUNDARY:0:32}
FILENAME=$(basename "$ATTACHMENT")

rm -rf "$TMP"
uuencode --base64 "$FILENAME" < "$ATTACHMENT" >"$TMP"
sed -i -e '1,1d' -e '$d' "$TMP"; #removes first & last lines from "$TMP"
DATA=$(cat "$TMP")

rm -rf "$TMP";
fappend "$TMP" "From: $FREMAIL";
fappend "$TMP" "To: $TOEMAIL";
fappend "$TMP" "Reply-To: $FREMAIL";
fappend "$TMP" "Subject: $SUBJECT";
fappend "$TMP" "Content-Type: multipart/mixed; boundary=\""$BOUNDARY"\"";
fappend "$TMP" "";
fappend "$TMP" "This is a MIME formatted message.  If you see this text it means that your";
fappend "$TMP" "email software does not support MIME formatted messages.";
fappend "$TMP" "";
fappend "$TMP" "--$BOUNDARY";
fappend "$TMP" "Content-Type: text/plain; charset=ISO-8859-1; format=flowed";
fappend "$TMP" "Content-Transfer-Encoding: 7bit";
fappend "$TMP" "Content-Disposition: inline";
fappend "$TMP" "";
fappend "$TMP" "$MSGBODY";
fappend "$TMP" "";
fappend "$TMP" "";
fappend "$TMP" "--$BOUNDARY";
fappend "$TMP" "Content-Type: $MIMETYPE; name=\"$FILENAME\"";
fappend "$TMP" "Content-Transfer-Encoding: base64";
fappend "$TMP" "Content-Disposition: attachment; filename=\"$FILENAME\";";
fappend "$TMP" "";
fappend "$TMP" "$DATA";
fappend "$TMP" "";
fappend "$TMP" "";
fappend "$TMP" "--$BOUNDARY--";
fappend "$TMP" "";
fappend "$TMP" "";
#cat "$TMP">out.txt
cat "$TMP"|sendmail -t -f none@example.com;
rm "$TMP";

