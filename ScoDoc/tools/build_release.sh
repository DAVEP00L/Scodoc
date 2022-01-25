#!/bin/bash

# Préparation d'une release ScoDoc:
# Utilise jq sur Debian 11 VM
apt-get install jq


# Le répertoire de ce script: .../scodoc/tools
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

# tente de trouver la version dans le source , pour vérification
SCODOC_RELEASE=$(grep SCOVERSION "$SCRIPT_DIR/../sco_version.py" | awk '{ print substr($3, 2, length($3)-2) }')

# Dernière release
GITEA_RELEASE_URL="https://scodoc.org/git/api/v1/repos/viennet/ScoDoc/releases" # ?pre-release=true" 

# suppose que les realse sont nommées 9.0.17, ne considère pas les caractères non numériques
LAST_RELEASE_TAG=$(curl "$GITEA_RELEASE_URL" | jq ".[].tag_name" | tr -d -c "0-9.\n" | sort --version-sort | tail -1)
# | awk '{ print substr($1, 2, length($1)-2) }')

echo 
echo "Version détectée dans le source: $SCODOC_RELEASE"
echo "Dernière release trouvée sur gitea: $LAST_RELEASE_TAG"
echo -n "Utiliser  $LAST_RELEASE_TAG ? (y/n) [y] "
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
  PACKAGE_VERSION="$LAST_RELEASE_TAG"
else
  echo -n "Entrer la version à générer: "
  read PACKAGE_VERSION
fi

PACKAGE_NAME=scodoc9
RELEASE_TAG="$PACKAGE_VERSION"
VERSION="$PACKAGE_VERSION"
RELEASE=1
ARCH="amd64"
FACTORY_DIR="/opt/factory"
DEST_DIR="$PACKAGE_NAME"_"$VERSION"-"$RELEASE"_"$ARCH"
GIT_RELEASE_URL="https://scodoc.org/git/viennet/ScoDoc/archive/${RELEASE_TAG}.tar.gz"

echo "Le paquet sera $DEST_DIR.deb"
echo -n "Est-ce ok ? (y/n) [y] "
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
  echo "ok"
else
  echo "annulation."
  exit 0
fi

SCODOC_USER=scodoc
# Safety checks
[ -z "$FACTORY_DIR" ] && die "empty FACTORY_DIR"
[ "$(id -nu)" != "$SCODOC_USER" ] && die "Erreur: le script $0 doit être lancé par l'utilisateur $SCODOC_USER"

# Création répertoire du paquet, et de opt
slash="$FACTORY_DIR"/"$DEST_DIR"
optdir="$slash"/opt

[ -e "$slash" ] && die "Directory $slash already exists"
mkdir -p "$optdir" || die "mkdir failure for $optdir"

# On récupère la release
archive="$FACTORY_DIR"/"$PACKAGE_NAME-$RELEASE_TAG".tar.gz
echo "Downloading $GIT_RELEASE_URL ..."
curl -o "$archive" "$GIT_RELEASE_URL" || die "curl failure for $GIT_RELEASE_URL"

# On décomprime
# normalement le résultat s'appelle "scodoc" et va dans opt
(cd "$optdir" && tar xfz "$archive") || die "tar extraction failure"

SCODOC_DIR="$optdir"/scodoc
[ -d "$SCODOC_DIR" ] || die "die Erreur: $SCODOC_DIR inexistant"

# Inject version (eg 9.0.2) in debian:control
sed -i.bak "s/Version: x.y.z/Version: $PACKAGE_VERSION/g" "$SCODOC_DIR/tools/debian/control"
# and double check
v=$(grep Version "$SCODOC_DIR/tools/debian/control" | awk '{ print $2 }')
if [ "$v" != "$PACKAGE_VERSION" ]
then
  echo "error in debian control file: version mismatch (bug)"
  exit 1
fi

# Puis on déplace les fichiers de config (nginx, systemd, ...)
#  nginx:
mkdir -p "$slash"/etc/nginx/sites-available || die "can't mkdir nginx config"
cp -p "$SCODOC_DIR"/tools/etc/scodoc9.nginx "$slash"/etc/nginx/sites-available/scodoc9.nginx.distrib || die "can't copy nginx config"

#  systemd
mkdir -p "$slash"/etc/systemd/system/ || die "can't mkdir systemd config"
cp -p "$SCODOC_DIR"/tools/etc/scodoc9.service "$slash"/etc/systemd/system/ || die "can't copy scodoc9.service"

# Répertoire DEBIAN
mv "$SCODOC_DIR"/tools/debian "$slash"/DEBIAN || die "can't install DEBIAN dir"
chmod 755 "$slash"/DEBIAN/*inst || die "can't chmod debian scripts"

# ------------ CREATION DU VIRTUALENV
#echo "Creating python3 virtualenv..."
#(cd $SCODOC_DIR && python3 -m venv venv) || die "error creating Python 3 virtualenv"

# ------------ INSTALL DES PAQUETS PYTHON (3.9)
# pip in our env, as user "scodoc"
#(cd $SCODOC_DIR && source venv/bin/activate && pip install wheel && pip install -r requirements-3.9.txt) || die "Error installing python packages"

# -------- THE END
echo "Terminé."

echo -n "Voulez-vous poursuivre et construire le .deb ? (y/n) [y] "
read -r ans
if [ "$(norm_ans "$ans")" != 'N' ]
then
  echo "ok"
else
  echo "arrêt."
  exit 0
fi

dpkg-deb --build --root-owner-group $DEST_DIR
DEB_FILE="$DEST_DIR".deb
echo "paquet construit: $DEB_FILE"



