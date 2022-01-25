#!/bin/bash

#
# ScoDoc:  restore data (saved by save_scodoc7_data) 
#          into current server
# 
#  Utile pour migrer de ScoDoc 7 à ScoDoc 9, d'un serveur à un autre
#  A executer en tant que root sur le nouveau serveur
#  Ce script va créer les base postgresql "scodoc7" (SCOUSERS, SCODEPTs...)
#  afin que ScoDoc 9 puisse les importer avec ses scripts de migration.
#  Les données (photos, etc) sont pas touchées et seront importées par
#  la migration.
#
# E. Viennet, Sept 2011, Nov 2013, Mar 2017, Aug 2020, Jul 2021, Août 21
#

# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

if [ "$(id -nu)" != "$SCODOC_USER" ]
then
  echo "Erreur: le script $0 doit être lancé par l'utilisateur $SCODOC_USER"
fi

# Usage
if [ ! $# -eq 1 ]
then
  echo "Usage: $0 directory_or_archive"
  exit 1
fi

SRC=$1

if [ "${SRC:0:1}" != "/" ]
then
  echo "Usage: $0 directory_or_archive"
  echo "Erreur: utiliser un chemin absolu (commencant par /)"
  exit 1
fi

# Safety check
echo "Ce script recharge les donnees de votre installation ScoDoc 7"
echo "sur ce serveur pour migration vers ScoDoc 9."
echo "Ce fichier doit avoir ete cree par le script save_scodoc7_data.sh, sur une machine ScoDoc 7."
echo 
echo -n "Voulez-vous poursuivre cette operation ? (y/n) [n]"
read -r ans
if [ ! "$(norm_ans "$ans")" = 'Y' ]
then
   echo "Annulation"
   exit 1
fi

SCOBASES=$(psql -l | grep SCO | grep -v "$SCODOC_DB_PROD" | grep -v "$SCODOC_DB_DEV" | grep -v "$SCODOC_DB_TEST")
if [ -n "$SCOBASES" ]
then
  echo "Attention: vous avez apparemment déjà des bases ScoDoc7 chargées"
  echo "$SCOBASES"
  echo
  echo -n "poursuivre quand même ? (y/n) [n]"
  read -r ans
  if [ ! "$(norm_ans "$ans")" = 'Y' ]
  then
   echo "Annulation"
   exit 1
  fi
fi


# Source directory
if [ "${SRC##*.}" = 'tgz' ]
then
  echo "Opening tgz archive..."
  tmp=$(mktemp -d)
  chmod a+rx "$tmp"
  cd "$tmp" || terminate "directory error"
  tar xfz "$SRC" 
  SRC=$(ls -1d "$tmp"/*)
fi

echo "Source is $SRC"

echo "L'opération peut durer plusieurs minutes, suivant la taille de vos bases."
echo "Vous allez probablement voir s'afficher de nombreux messages : "
echo "pg_restore: attention : la restauration des tables avec WITH OIDS n'est plus supportée"
echo
echo "ce n'est pas grave !"
echo -n "valider pour continuer"
read -r ans

# Load postgresql dumps
for f in "$SRC"/SCO*.dump
do
  echo "Loading postgres database from $f"
  pg_restore --create  -d SCODOC --no-owner "$f"
  # le pg_restore a parfois des erreurs sans gravités...
  # voir https://www.postgresql.org/message-id/20849.1541638465%40sss.pgh.pa.us
  # donc on ne peut pas se fier au code de retour.
  # Demander aux utilisateurs de vérifier eux meêm que les bases sont OK
  # if [ ! "$?" -eq 0 ] 
  # then
  #   printf "Error restoring postgresql database\nPlease check that SQL server is running\nAborting."
  #   exit 1
  # fi
done

echo
echo "Terminé. (vous pouvez ignorer les éventuels avertissements de pg_restore ci-dessus !)"
echo 
echo "Vous pouvez passer à l'étape 4 de la migration (migrate_from_scodoc7.sh), voir la doc."
echo
# 
