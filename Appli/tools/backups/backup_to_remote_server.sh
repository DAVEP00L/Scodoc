#!/bin/bash

# Script effectuant un backup des principaux repertoires
# du serveur ScoDoc vers une machine distante.
# utilise rsync (pour ne cpier que les fichiers modifies)
# et ssh (pour se connecter de faon securisee).
#
# L'utilisateur root du serveur scodoc (qui execute ce script)
# doit pouvoir se conencter directement (sans mot de passe) sur
# la machine distante (installer les cles ssh necessaires).
#
# A adapter a vos besoins. Utilisation a vos risques et perils.
#
# E. Viennet, 2002, 2021

# Installation:
# 1- Installer rsync:
#     apt-get install rsync
# 2- mettre en place un job cron:
#     par exemple copier ce script dans /etc/cron.daily/
#    (et le rendre executable avec chmod +x ...)

# -------------------- CONFIGURATION A ADAPTER

remotehost=XXXX # nom ou IP du serveur de sauvegarde
destdir=/home/SAU-SCODOC # repertoire sur serveur de sauvegarde

logfile=/var/log/rsynclog # log sur serveur scodoc

# A qui envoyer un mail en cas d'erreur de la sauvegarde:
SUPERVISORMAIL=emmanuel.viennet@example.com

CALLER=$(basename $0)
MACHINE=$(hostname -s)

# -----------------------------------------------------

# ----------------------------------
# Subroutine to terminate abnormally
# ----------------------------------
terminate()
{
 dateTest=$(date)

 mail -s "Attention: Probleme sauvegarde ScoDoc" $SUPERVISORMAIL <<EOF
The execution of script $CALLER was not successful on $MACHINE.

Look at logfile $logfile"

$CALLER terminated, exiting now with rc=1."

EOF
 
# repeat message for logs...
 echo "The execution of script $CALLER was not successful on $MACHINE."
 echo
 echo  "Look at logfile $logfile"
 echo
 echo "$CALLER terminated, exiting now with rc=1."
 dateTest=$(date)
 echo "End of script at: $dateTest"
 echo ""

 exit 1
}

# --------------------------------------
# Subroutine to mirror a dir using rsync (mirror on REMOTE HOST)
# Variables:
#   remotehost : hostname on which is the mirror
#   srcdir     : directory to mirror on local host 
#   destdir    : directory on remotehost where to put the copy
#   logfile    : filename to log actions
# --------------------------------------
rsync_mirror_to_remote()
{
  echo "--------------- mirroring $MACHINE:$srcdir to $remotehost:$destdir" >> $logfile 2>&1
  echo "starting at $(date)" >> $logfile 2>&1
  rsync -vaze ssh --delete --rsync-path=/usr/bin/rsync "$srcdir" "$remotehost:$destdir" >> $logfile 2>&1
  if [ $? -ne 0 ]
  then
    echo Error in rsync: code=$?
    terminate
  fi

  echo "ending at $(date)" >> $logfile 2>&1
  echo "---------------"  >> $logfile 2>&1
}



# ----------- REPERTOIRES A SAUVEGARDER:
for srcdir in /etc /home /root /opt /usr/local /var; do
    rsync_mirror_to_remote
done
