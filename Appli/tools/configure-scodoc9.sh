#!/bin/bash

# Script à lancer en tant que root sur un nouveau serveur
# pour terminer la configuration juste après apt-get install scodoc9

# On ne place pas ces commandes dans le postinst
# car c'est spécifique et optionnel.
# Le répertoire de ce script:

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

cd /opt/scodoc || die "Error: chdir to /opt/scodoc"
check_uid_root

# ------------ VERIF SYSTEME 

if [ -e /etc/debian_version ]
then 
    debian_version=$(cat /etc/debian_version)
    debian_version=${debian_version%%.*}
    echo "Detected Debian version: ${debian_version}"
    if  [ "$debian_version" != "11" ]
    then
        echo "Erreur: version Linux Debian incompatible"
        echo "Utiliser un système Debian Bullseye (11)"
        echo
        exit 1
    fi
else
    echo "can't detect Debian version"
    exit 1
fi
echo "--- Configuration de ScoDoc pour Debian 11"

# ------------ CONFIG FIREWALL OPTIONNELLE
echo 
echo "Le firewall aide a proteger votre serveur d'intrusions indesirables."
echo -n "Voulez vous configurer un firewall minimal (ufw) ? (y/n) [n] "
read -r ans
if [ "$(norm_ans "$ans")" = 'Y' ]
then
    echo 'Installation du firewall IP ufw (voir documentation Debian)'
    echo '   on autorise les connexions ssh et https'
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow http
    ufw allow https
    yes | ufw enable
    echo
    echo "firewall ufw activé."
    echo
fi

# ------------ CONFIG NGINX
# --- CERTIFICATS AUTO-SIGNES
echo 
echo "Le serveur Web utilisé par ScoDoc et nginx"
echo "Il est possible d'utiliser des certificats cryptographiques"
echo "auto-signés, qui ne seront pas reconnus comme de confiance"
echo "par les navigateurs, permettent de tester."
echo "Si vous avez déjà de vrais certificats, passez cette étape et installez-les ensuite."
echo -n 'Voulez-vous générer des certificats ssl auto-signés ? (y/n) [y] '
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    # génération des certifs: cert.pem  key.pem dans /opt/scodoc-data/certs/
    su -c "(cd $SCODOC_VAR_DIR && mkdir -p certs && openssl req -new -newkey rsa:4096 -days 365 -nodes -x509  -keyout certs/key.pem -out certs/cert.pem)" "$SCODOC_USER"
fi

# ------------ CREATION ENVIRONNEMENT
echo
echo "Créer (et écraser) le fichier /opt/scodoc-data/.env"
echo "      définissant les variables d'environnement ?"
echo "(si vous ne savez pas, répondez oui !)"
echo -n 'Générer /opt/scodoc-data/.env ? (y/n) [y] '
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    echo -n "Adresse mail de l'administrateur du site: "
    read SCODOC_ADMIN_MAIL
    SECRET_KEY=$(python3 -c "import uuid; print(uuid.uuid4().hex)")
    cat > /opt/scodoc-data/.env <<EOF 
# .env for ScoDoc (production)
FLASK_APP=scodoc.py
FLASK_ENV=production

SCODOC_ADMIN_MAIL="$SCODOC_ADMIN_MAIL" # important: le mail de admin
SECRET_KEY="$SECRET_KEY" # une chaine aléatoire"

EOF
    echo "Fichier /opt/scodoc-data/.env créé avec:"
    cat /opt/scodoc-data/.env 
    echo 
    echo "Vous pouvez le modifier si besoin."
    echo
fi

# ------------ VERIFICATIONS DES REPERTOIRES ET DROITS
# déjà fait par le postinst, mais certaines fausses manips de nos utilisateurs
# ont pu changer ça:
set_scodoc_var_dir
change_scodoc_file_ownership

# ------------ CREATION BASE DE DONNEES
echo 
echo "Voulez-vous créer la base SQL SCODOC ?"
echo "(répondre oui sauf si vous savez vraiment ce que vous faites)"
echo -n 'Créer la base de données SCODOC ? (y/n) [y] '
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    # on ne créée pas les bases TEST et DEV
    su -c "/opt/scodoc/tools/create_database.sh SCODOC" "$SCODOC_USER" || die "Erreur: create_database.sh SCODOC"
    echo "base SCODOC créée."
    # ------------ INITIALISATION BASE DE DONNEES
    echo
    echo "Création des tables et du compte admin"
    echo
    msg="Saisir le mot de passe administrateur \(admin, via le web\):"
    su -c "(cd /opt/scodoc; source venv/bin/activate; flask db upgrade; flask sco-db-init; echo; echo $msg; flask user-password admin)" "$SCODOC_USER" || die "Erreur: sco-db-init"
    echo
    echo "Base initialisée et admin créé."
    echo
fi

# ------------ LANCEMENT DES SERVICES
systemctl start redis
systemctl start nginx
systemctl start scodoc9

echo
echo "Service configuré et démarré."
echo "Vous pouvez vous connecter en web et vous identifier comme \"admin\"."
echo "ou bien importer vos données et comptes de la version ScoDoc 7."
echo



    