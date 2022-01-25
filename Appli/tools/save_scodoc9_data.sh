#!/bin/bash

#
# ScoDoc: save all user data (database, configs, images, archives...) in separate directory
# 
#  Utile pour migrer ScoDoc version 9 (et plus) d'un serveur a un autre
#  Executer en tant que scodoc sur le serveur d'origine.
#  Utiliser - pour sortir sur la sortie standard (eg pipe dans ssh...)
#
# E. Viennet, Sept 2011, Aug 2020, Aug 21
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

if [ "$(id -nu)" != "$SCODOC_USER" ]
then
 echo "$0: script must be runned as user $SCODOC_USER"
 exit 1
fi

echo "vérification de la configuration..."
DB_CURRENT=$(cd $SCODOC_DIR && source venv/bin/activate && flask scodoc-database -n)
if [ $DB_CURRENT != 'SCODOC' ]; then
  echo "Ce script ne peut transférer les données que depuis une base nommée SCODOC (c'est normalement le cas pour un serveur en production)"
  echo "Annulation"
  exit 1
fi

echo "Ce script est utile pour transférer toutes les données d'un serveur ScoDoc 9"
echo "à un autre ScoDoc 9."
echo "Il est vivement recommandé de mettre à jour votre ScoDoc avant."
echo ""
echo -n "Voulez-vous poursuivre cette sauvegarde ? (y/n) [n]"
read -r ans
if [ ! "$(norm_ans "$ans")" = 'Y' ]
then
   echo "Annulation"
   exit 1
fi

# Destination
if [ ! $# -eq 1 ]
then
  echo "Usage: $0 destination_file"
  echo "(- sort sur stdout)"
  echo "Exemple: $0 /tmp/mon-scodoc.tgz"
  exit 1
fi
DEST=$1
db_name="$SCODOC_DB_PROD" # SCODOC

# dump dans /opt/scodoc-data/SCODOC.dump
echo "sauvegarde de la base de données"
pg_dump --format=custom --file="$SCODOC_VAR_DIR/$db_name.dump" "$db_name" || die "Error dumping database"

echo "création du fichier d'archivage..."
# tar scodoc-data vers le fichier indiqué ou stdout
(cd $(dirname "$SCODOC_VAR_DIR"); tar cfz "$DEST" $(basename "$SCODOC_VAR_DIR")) || die "Error archiving data"

