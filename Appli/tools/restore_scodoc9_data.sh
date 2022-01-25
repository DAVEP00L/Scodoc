#!/bin/bash

#
# ScoDoc:  restore data (saved by save_scodoc9_data) into current install
# 
#  Utile pour migrer ScoDoc 9 d'un serveur a un autre
#  A executer en tant que root sur le nouveau serveur
#
# E. Viennet, Sept 2021
#
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

# Ce script doit tourner comme "root"
check_uid_root "$0"

# Usage
usage() {
  echo "Usage: $0 [ --keep-env ] archive"
  echo "Exemple: $0 /tmp/mon-scodoc.tgz"
  echo "OPTION"
  echo "--keep_env garde la configuration courante"
  exit 1
}

if (($# < 1 || $# > 2))
then
  usage
elif [ $# -eq 2 -a  $1 != '--keep-env' -a $2 != '--keep-env' ] ; then
  usage
elif [ $# -eq 1 ] ; then
  echo "restauration des données et de la configuration originale (production)"
  SRC=$1
  DB_DEST="SCODOC"
else
  echo "restauration des données dans la configuration actuelle"
  DB_CURRENT=$(su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask scodoc-database -n)")
  DB_DEST="$DB_CURRENT"
  KEEP=1
  if [ $1 = '--keep-env' ]; then
    SRC=$2
  else
    SRC=$1
  fi
fi
DB_DUMP="${SCODOC_VAR_DIR}"/SCODOC.dump

# Safety check
echo "Ce script va remplacer les donnees de votre installation ScoDoc par celles"
echo "enregistrées dans le fichier fourni."
echo "Ce fichier doit avoir ete cree par le script save_scodoc9_data.sh."
echo 
echo "Attention: TOUTES LES DONNEES DE CE SCODOC SERONT REMPLACEES !"
echo "Notamment, tous les utilisateurs et departements existants seront effaces !"
echo
echo "La base SQL $DB_CURRENT sera effacée et remplacée !!!"
echo
echo -n "Voulez vous poursuivre cette operation ? (y/n) [n]"
read -r ans
if [ ! "$(norm_ans "$ans")" = 'Y' ]
then
   echo "Annulation"
   exit 1
fi

# -- Stop ScoDoc
if [ $KEEP -ne 1 ]; then
   echo "Arrêt de scodoc9..."
   systemctl stop scodoc9
else
   echo -n "Assurez-vous d'avoir arrété le serveur scodoc (validez pour continuer)"
   read ans
fi

# Clear caches
echo "Purge des caches..."
su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask clear-cache)" "$SCODOC_USER" || die "Erreur purge cache scodoc9"

# Déplace scodoc-data s'il existe
if [ -e "$SCODOC_VAR_DIR" ]
then
  echo "$SCODOC_VAR_DIR existe: le renomme en .old"
  mv "$SCODOC_VAR_DIR" "$SCODOC_VAR_DIR".old || die "Erreur renommage scodoc-data"
fi

# -- Ouverture archive
echo "Ouverture archive $SRC..."
(cd $(dirname "$SCODOC_VAR_DIR"); tar xfz "$SRC") || die "Error opening archive"

# -- Ckeck/fix owner
echo "Vérification du propriétaire..."
chown -R "${SCODOC_USER}:${SCODOC_GROUP}" "${SCODOC_VAR_DIR}" || die "Error chowning ${SCODOC_VAR_DIR}"

# --- La base SQL: nommée $(db_name).dump
nb=$(su -c "psql -l" "$SCODOC_USER" | awk '{print $1}' | grep -c -x "$DB_DEST")
if [ "$nb" -gt 0 ]
then
  echo "Suppression de la base $DB_DEST..."
  su -c "dropdb $DB_DEST" "$SCODOC_USER" || die "Erreur destruction db"
fi
su -c "createdb $DB_DEST" "$SCODOC_USER" || die "Erreur création db"

if [ ! -z $KEEP_ENV ] ; then
   echo "conservation de la configuration actuelle"
   cp "$SCODOC_VAR_DIR".old/.env "$SCODOC_VAR_DIR"/.env
   echo "récupération des données..."
   su -c "pg_restore -f - $DB_DUMP | psql -q $DB_DEST" "$SCODOC_USER" >/dev/null || die "Erreur chargement/renommage de la base SQL"
   su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask db upgrade)" "$SCODOC_USER"
   echo "redémarrez scodoc selon votre configuration"
else
# -- Apply migrations if needed (only on "production" database, = SCODOC sauf config particulière)
   echo "restauration environnement de production"
   echo "Chargement de la base SQL..."
   su -c "pg_restore -d $DB_DEST $DB_DUMP" "$SCODOC_USER" || die "Erreur chargement de la base SQL"
   export FLASK_ENV="production"   # peut-être pas utile? : .env a été recopié
   su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask db upgrade)" "$SCODOC_USER"
# -- Start ScoDoc
   systemctl start scodoc9
fi


echo "Terminé."
