#!/bin/bash

# Upgrade ScoDoc installation using APT
#   
# This script STOP and RESTART ScoDoc and should be runned as root
#
# Upgrade also the Linux system using apt.
#
# Script for ScoDoc 9
#
# E. Viennet, sep 2013, mar 2017, jun 2019, aug 2020, dec 2020, aug 21


# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

cd "$SCODOC_DIR" || { echo "Invalid directory"; exit 1; }


check_uid_root "$0"

if [ -z "$SCODOC_UPGRADE_RUNNING" ]
   then
       apt-get update && apt-get -y dist-upgrade
       # install spécifiquement scodoc9, utile si les dépendances Debian de scodoc9
       # ont été changées, ce qui peut provoquer un
       # "packages have been kept back"
       apt install scodoc9
fi
systemctl restart redis
systemctl restart nginx
systemctl restart scodoc9
