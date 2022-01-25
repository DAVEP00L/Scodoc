#!/bin/bash

#
# ScoDoc 9: install third-party software necessary for our installation
# starting for a minimal Debian (Buster, 10.0) install.
#
# E. Viennet, Jun 2008, Apr 2009, Sept 2011, Sept 2013, Nov 2013, Mar 2017, Jul 2017, 
# Jun 2019, Oct 2019, Dec 2020, Jul 2021, Aug 21
#

set -euo pipefail


echo "ne plus utiliser ce script"
exit 0


# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

check_uid_root "$0"

cd "$SCODOC_DIR" || die "can't cd $SCODOC_DIR"

# ------------ Safety checks
if [ "${debian_version}" != "11" ]
then
   echo "Version du systeme Linux Debian incompatible"
   exit 1
fi

if [ "$(arch)" != "x86_64" ]
then
   echo "Version du systeme Linux Debian incompatible (pas X86 64 bits)"
   exit 1
fi

# ------------ Unix user
check_create_scodoc_user

# ------------ Permissions & directories
change_scodoc_file_ownership
set_scodoc_var_dir

# ------------ LOCALES (pour compat bad ScoDoc 7)
locname="en_US.UTF-8"
outname=$(echo ${locname//-/} | tr '[A-Z]' '[a-z]')
if [ "$(locale -a | grep -E -i ^${outname}$ | wc -l)" -lt 1 ]
then
    echo adding $locname
    echo "$locname ${locname##*.}" >> /etc/locale.gen
    /usr/sbin/locale-gen --keep-existing 
fi

# ------------ AJOUT DES PAQUETS DEBIAN NECESSAIRES
apt-get update
apt-get -y install gcc
apt-get -y install python3-dev
apt-get -y install python3-venv
apt-get -y install python3-pip
apt-get install -y python3-wheel
apt-get -y install libpq-dev
apt-get -y install libcrack2-dev
apt-get -y install nginx
apt-get -y install postgresql
apt-get -y install redis
apt-get -y install curl
apt-get -y install graphviz

systemctl start redis

# ------------ CREATION DU VIRTUALENV
echo "Creating python3 virtualenv..."
su -c "(cd $SCODOC_DIR && python3 -m venv venv)" scodoc || die "can't create Python 3 virtualenv"

# ------------ INSTALL DES PAQUETS PYTHON (3.9)
# pip in our env, as user "scodoc"
su -c "(cd $SCODOC_DIR && source venv/bin/activate && pip install wheel && pip install -r requirements-3.9.txt)" scodoc || die "Error installing python packages"
# pip install --upgrade pip => bug [Errno 39] Directory not empty: '_internal'

# ------------
SCODOC_RELEASE=$(grep SCOVERSION sco_version.py | awk '{ print substr($3, 2, length($3)-2) }')
SVERSION=$(curl --silent https://scodoc.org/scodoc-installmgr/version?mode=install\&release="$SCODOC_RELEASE")
echo "$SVERSION" > "${SCODOC_VERSION_DIR}/scodoc.sn"


# ------------ POSTFIX
echo 
echo "ScoDoc a besoin de pouvoir envoyer des messages par mail."
echo -n "Voulez vous configurer la messagerie (tres recommande) ? (y/n) [y] "
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    apt-get -y install postfix
fi

# ------------ CONFIG FIREWALL (non teste en Debian 10)
echo 
echo "Le firewall aide a proteger votre serveur d'intrusions indesirables."
echo -n "Voulez vous configurer un firewall minimal (ufw) ? (y/n) [n] "
read -r ans
if [ "$(norm_ans "$ans")" = 'Y' ]
then
    echo 'Installation du firewall IP ufw (voir documentation Debian)'
    echo '   on autorise les connexions ssh et https'
    apt-get -y install ufw
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow https
    yes | ufw enable
fi

# --- POSTGRESQL
# --- Ensure postgres user "scodoc" ($POSTGRES_USER) exists
init_postgres_user


# ------------ CONFIG NGINX

echo 
echo "La configuration du serveur web peut modifier l'installation nginx pour supporter ScoDoc."
echo -n "Voulez-vous configurer le serveur web nginx maintenant (vivement conseillé) ? (y/n) [y] "
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    echo "Configuration du serveur web nginx"
    # --- CERTIFICATS AUTO-SIGNES
    echo 
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
        cert_status=$?
    else
        cert_status=-1
    fi
    # ---
    echo 'copie de la configuration nginx'
    cp -p "$SCODOC_DIR"/tools/etc/scodoc9.nginx /etc/nginx/sites-available/
    ln -s /etc/nginx/sites-available/scodoc9.nginx  /etc/nginx/sites-enabled/
    /bin/rm -f /etc/nginx/sites-enabled/default
fi

systemctl restart nginx

# ------------ CONFIG SERVICE SCODOC
echo 
echo "Installation du service systemd scodoc9..."
# ScoDoc 7.19+ uses systemd
cp "$SCODOC_DIR"/tools/etc/scodoc9.service /etc/systemd/system/
systemctl daemon-reload


# --- XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX ---
echo
echo "WARNING: version ScoDoc 9 expérimentale"
echo "Ne pas utiliser en production !"
echo
echo "Pour lancer le serveur de développement: voir README"
echo
echo "Pour lancer scodoc9:  systemctl start scodoc9"
echo "(les logs sont dans /opt/scodoc-data/logs)"
exit 0
# --- XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX XXX ---

# XXX SUITE A TERMINER !

# ------------ CONFIG MISE A JOUR HEBDOMADAIRE
echo
echo -n "Mises a jour hebdomadaires (tres recommande) ? (y/n) [y] "
read ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
    cp "$SCODOC_DIR"/tools/etc/scodoc-updater.service /etc/systemd/system
    cp "$SCODOC_DIR"/tools/etc/scodoc-updater.timer /etc/systemd/system
    systemctl enable scodoc-updater.timer
    systemctl start scodoc-updater.timer
fi

# ------------ THE END
echo
echo "Installation terminee."
echo
echo "Vous pouvez maintenant creer la base d'utilisateurs avec ./create_user_db.sh"
echo "puis creer un departement avec  ./create_dept.sh"
echo "Ou bien restaurer vos donnees a partir d'une ancienne installation a l'aide du script restore_scodoc_data.sh"
echo "(voir https://scodoc.org/MigrationDonneesScoDoc/)"
echo


if [ "${cert_status}" != 0 ]
then
    echo "Attention: le serveur Web Apache n'a pas de certificat."
    echo "Il est probable qu'il ne fonctionne pas."
    echo "Installez vos certificats ou generez provisoirement des certificats autosignes"
    echo "avec la commande: /usr/sbin/make-ssl-cert /usr/share/ssl-cert/ssleay.cnf $ssl_dir/apache.pem"
    echo
fi

