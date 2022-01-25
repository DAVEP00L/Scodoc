#!/bin/bash

# Migre une install ScoDoc 7 vers ScoDoc 9
# Les données ScoDoc7 sauvegardées par save_scodoc7_data.sh
# sont copiés au bon endroit
# puis les bases SQL ScoDoc 7 sont traduites dans la base ScoDoc 9
#
# Fichiers de données et config locale:
#     archives, photos: /opt/scodoc/var/ => /opt/scodoc-data
#
#

# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

cd "$SCODOC_DIR" || die "ScoDoc 9 non installe"

# Ce script doit tourner comme "root"
check_uid_root "$0"

# ScoDoc 9 doit être bien installé
[ -e .env ] || die "ScoDoc 9 mal configuré: manque .env"

# Usage
usage() {
    echo "Script de migration: import des données de ScoDoc 7 dans ScoDoc 9"
    echo "Ce script doit être lancé en tant que root sur le nouveau"
    echo "serveur ScoDoc 9 / Debian 11."
    echo
    echo "Usage: $0 [-h] [-m] [-z] archive"
    echo
    echo "    archive doit être un répertoire exporté via save_scodoc7_data.sh"
    echo "            sur le serveur ScoDoc 7"
    echo "    Options:"
    echo "       -m"
    echo "          effectue une migration \"en place\""
    echo "          avec import des données ScoDoc 7 qui étaient sur cette même"
    echo "          machine."
    echo "          Dans ce cas, le répertoire /opt/scodoc DOIT avoir été renommé"
    echo "           /opt/scodoc7"
    echo "          AVANT l'installation de ScoDoc 9."
    echo 
    echo "       -z"
    echo "          efface la base existante, utilise le scodoc-data existant sans"
    echo "          l'effacer et tolère les fichiers manquants dans la source."
    echo "          Utilisée pour reprendre une migration interrompue."
    exit 1
}

INPLACE=0
RESTART=0
while getopts "hmz" opt; do
  case "$opt" in
    h)
    usage
    ;;
    m)
    echo "Migration en place"
    INPLACE=1
    SCODOC7_HOME=/opt/scodoc7
    # vérifie que ScoDoc7 est bien arrêté:
    systemctl is-active scodoc >& /dev/null && systemctl stop scodoc
    ;;
    z)
    echo "Mode reprise sur erreur"
    RESTART=1
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

shift "$((OPTIND - 1))"

if [ "$INPLACE" = "0" ]
then
    echo "Migration depuis archive $1"
    SCODOC7_HOME="$1" # racine de l'archive importée
fi

# --- 0. En mode reprise, efface la base de données. En effet, les base d'origine ne sont pas
#        effacées par le script de migration, et en cas d'erreur en cours d'import, il est plus
#        sûr de repartir de zéro.
if [ "$RESTART" = "1" ]
then
    echo "Efface la base existante"
    su -c "(cd /opt/scodoc && source venv/bin/activate && flask sco-db-init --erase)" "$SCODOC_USER" || die "Erreur: sco-db-init"
fi

# --- 1. Vérifie qu'aucun des départements à importer n'existe déjà
check_existing_depts() {
    sco7_depts=""
    for f in "${SCODOC7_HOME}/var/scodoc/"/config/depts/*.cfg
    do
        dept=$(basename "${f%.*}") # le nom du dept peut-être en minuscules
        sco9_name=$(echo "$dept" | tr "[:lower:]" "[:upper:]") # acronym ScoDoc 9 toujours en majuscule
        sco7_depts="$sco7_depts $sco9_name"
    done
    nb_existing=$(echo "$sco7_depts"  | su -c "cd $SCODOC_DIR && source venv/bin/activate && xargs flask list-depts" "$SCODOC_USER" | wc -l)
    if [ "$nb_existing" -gt 0 ]
    then
        echo "Attention: il existe déjà $nb_existing départements de même nom que celles"
        echo "que vous souhaitez importer !"
        echo "Département qui allaient être importées: $sco7_depts"
        echo "=> arrêt."
        exit 2
    fi
}


# --- 2. Propriétaire des bases de données pour import "en place"
# Bases appartenant à www-data: les attribue à "scodoc" pour le script de migration SQL
#  qui tourne en tant que "scodoc"
# Inutile si on importe via pg_restore (voir restore-scodoc7_data.sh)
#
migrate_database_ownership() {
    echo "Changing databases ownerships"
    SCO7_BASES=$(su -c "psql -l -t | grep www-data" "$POSTGRES_SUPERUSER" | awk -F '|' '{print $1}')
    if [ -z "$SCO7_BASES" ]
    then
        echo "Aucune base ScoDoc 7 appartenant à www-data. OK."
    else
        for base in $SCO7_BASES
        do
            echo "modifying $base owner"
            su -c "psql -c 'REASSIGN OWNED BY \"www-data\" TO scodoc;' $base" "$POSTGRES_SUPERUSER"
        done
        su -c "psql -c 'REASSIGN OWNED BY \"www-data\" TO scodoc;'" "$POSTGRES_SUPERUSER"
    fi
}

# --- 3. Fichiers locaux: /opt/scodoc7/var => /opt/scodoc-data
# note mémo: $SCODOC_DIR est /opt/scodoc, et $SCODOC_VAR_DIR /opt/scodoc-data
#
# Migration en place: /opt/scodoc7/var == SCODOC7_HOME/var  => /opt/scodoc-data
# Migration via archive: SCODOC7_HOME/var => /opt/scodoc-data

migrate_local_files() {
    echo "Déplacement des fichiers de configuration et des archives"
    SCODOC_VAR_DIR_BACKUP="$SCODOC_VAR_DIR".bak
    if [ "$RESTART" = "0" ] # ne le fait pas en mode "reprise"
    then
        if [ -e "$SCODOC_VAR_DIR_BACKUP" ]
        then
            die "supprimer ou déplacer $SCODOC_VAR_DIR_BACKUP avant de continuer"
        fi
        if [ -e "$SCODOC_VAR_DIR" ]
        then
            echo "    renomme $SCODOC_VAR_DIR  en  $SCODOC_VAR_DIR_BACKUP"
            mv "$SCODOC_VAR_DIR" "$SCODOC_VAR_DIR_BACKUP"
        fi
        mkdir "$SCODOC_VAR_DIR" || die "erreur creation repertoire"
    fi
    if [ $(ls "${SCODOC7_HOME}/var/scodoc" | wc -l) -ne 0 ]
    then
        echo "    déplace ${SCODOC7_HOME}/var/scodoc/ dans $SCODOC_VAR_DIR..."
        mv "${SCODOC7_HOME}"/var/scodoc/* "$SCODOC_VAR_DIR" || die "migrate_local_files failed"
    fi
    # Récupère le .env: normalement ./opt/scodoc/.env est un lien vers
    # /opt/scodoc-data/.env
    # sauf si installation non standard (developeurs) avec .env réellement dans /opt/scodoc
    if [ -L "$SCODOC_DIR"/.env ] && [ ! -e "$SCODOC_VAR_DIR"/.env ]
    then
        cp -p "$SCODOC_VAR_DIR_BACKUP"/.env "$SCODOC_VAR_DIR" || die "fichier .env manquant dans l'ancien $SCODOC_VAR_DIR !"
    fi
    # et les certificats
    if [ -d "$SCODOC_VAR_DIR_BACKUP"/certs ] && [ ! -d "$SCODOC_VAR_DIR"/certs ]
    then
        cp -rp "$SCODOC_VAR_DIR_BACKUP"/certs "$SCODOC_VAR_DIR" || die "erreur copie certs"
    fi
    # Anciens logs ScoDoc7
    old_logs_dest="$SCODOC_VAR_DIR/log/scodoc7"
    echo "Copie des anciens logs ScoDoc 7 dans $old_logs_dest"
    mkdir -p "$old_logs_dest" || die "erreur creation $old_logs_dest"
    if [ $(ls "${SCODOC7_HOME}/log" | wc -l) -ne 0 ]
    then
        mv "${SCODOC7_HOME}"/log/* "$old_logs_dest" || die "erreur mv"
    fi
    # Le fichier de customization local:
    # peut être dans .../var/config/scodoc_local.py
    # ou bien, sur les très anciennes installs, dans Products/ScoDoc/config/scodoc_config.py
    # (si migration, copié dans SCODOC7_HOME/config/scodoc_config.py)
    # en principe ScoDoc 9 est encore compatible avec cet ancien fichier.
    # donc:
    if [ ! -e "$SCODOC_VAR_DIR"/scodoc_local.py ]
    then
        echo "note: pas de fichier scodoc_local.py (ok)."
        # if [ "$INPLACE" == 1 ]
        # then
        #     scodoc_config_filename = "${SCODOC7_HOME}"/Products/ScoDoc/config/scodoc_config.py
        # else
        #     scodoc_config_filename = "${SCODOC7_HOME}"/config/scodoc_config.py
        # fi
        # # Le fichier distribué avait-il été modifié ?
        # if [ $(md5sum "$scodoc_config_filename" | cut -f1 -d ' ') == "378caca5cb2e3b2753f5989c0762b8cc" ]
        # then
        #     echo "copying $scodoc_config_filename to $SCODOC_VAR_DIR/scodoc_local.py"
        #     cp "$scodoc_config_filename" "$SCODOC_VAR_DIR"/scodoc_local.py || die "erreur cp"
        # fi
    fi

    # Templates locaux poursuites etudes
    if [ -e "${SCODOC7_HOME}"/config/doc_poursuites_etudes/local ]
    then 
        mv "${SCODOC7_HOME}"/config/doc_poursuites_etudes/local "$SCODOC_VAR_DIR"/config/doc_poursuites_etudes || die "migrate_local_files failed to migrate doc_poursuites_etudes/local"
    fi
    # S'assure que le propriétaire est "scodoc":
    chown -R "${SCODOC_USER}:${SCODOC_GROUP}" "${SCODOC_VAR_DIR}" || die "change_scodoc_file_ownership failed on ${SCODOC_VAR_DIR}"
}


# ------ MAIN

check_existing_depts

change_scodoc_file_ownership

if [ "$INPLACE" == 1 ]
then
    migrate_database_ownership
fi

migrate_local_files
set_scodoc_var_dir

echo
echo "Les fichiers locaux de ScoDoc: configuration, photos, procès-verbaux..."
echo "sont maintenant stockées dans $SCODOC_VAR_DIR"
echo


# ----- Migration base utilisateurs
echo
echo "-------------------------------------------------------------"
echo "Importation des utilisateurs de ScoDoc 7 dans ScoDoc 9 "
echo "(la base SCOUSERS de ScoDoc 7 sera laissée inchangée)"
echo "(les utilisateurs ScoDoc 9 existants seront laissés inchangés)"
echo "-------------------------------------------------------------"
echo

su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask import-scodoc7-users)" "$SCODOC_USER" || die "Erreur de l'importation des utilisateurs ScoDoc7"


# ----- Migration bases départements
# les départements ScoDoc7 ont été déplacés dans /opt/scodoc-data/config/dept
# (ils ne sont plus utilisés par ScoDoc 9)
# Le nom du dept peut-être en minuscules et/ou majuscules (Geii, GEII...)
# Le nom de BD ScoDoc7 est toujours en majuscules (SCOGEII)
# Rappel: les archives ScoDoc7 étaient .../archives/<dept_name>/... donc minuscules/majuscules
# alors qu'en ScoDoc9 elles seront .../archives/<dept_id>/ : le numéro interne du département, 
#  puisque l'acronyme peut changer.
for f in "$SCODOC_VAR_DIR"/config/depts/*.cfg
do
    dept=$(basename "${f%.*}") # le nom du dept peut-être en minuscules
    db_name=$(echo "SCO$dept" | tr "[:lower:]" "[:upper:]") # nom de BD toujours en majuscule
    echo
    echo "----------------------------------------------"
    echo "|     MIGRATION DU DEPARTEMENT $dept"
    echo "----------------------------------------------"
    su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask import-scodoc7-dept $dept $db_name)" "$SCODOC_USER" || die "Erreur au cours de la migration de $dept."
    echo "restarting postgresql server..."
    systemctl restart postgresql
done 

# ----- Post-Migration: renomme archives en fonction des nouveaux ids
su -c "(cd $SCODOC_DIR && source venv/bin/activate && flask migrate-scodoc7-dept-archives)" "$SCODOC_USER" || die "Erreur de la post-migration des archives"


# --- Si migration "en place", désactive ScoDoc 7
if [ "$INPLACE" == 1 ]
then
    systemctl disable scodoc
fi


# Précaution a priori inutile (import-scodoc7-dept efface les caches)
systemctl restart redis

# --- THE END
echo 
echo "Migration terminée."
echo "Vérifiez le fichier de log /opt/scodoc-data/log/migration79.log"
echo "et:"
echo "- prévenez les utilisateurs dont le login aurait changé."
echo "- dans ScodoC, en tant qu'admin, vérifier la configuration et"
echo "   notamment la fonction de calcul du bonus sport, dont le réglage" 
echo "   est différent en ScoDoc 9 (plus de fichier de configuration python,"
echo "   passer par le formulaire de configuration.)"
echo


# Commande listant les nom des departement en DB:
# Liste des bases de données de département:
# dept_db=$(psql -l | awk '{print $1;}' | grep ^SCO | grep -v SCOUSERS | grep -v SCO8USERS | awk '{print substr($1,4);}')
