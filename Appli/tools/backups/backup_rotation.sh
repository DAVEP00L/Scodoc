#!/bin/bash
# Backup rotation
# Usage example: backup_rotation.sh /var/lib/postgresql/BACKUP-SCODOC
#
# This script is designed to run each hour
#
# E. Viennet 2014, loosely inspired by  Julius Zaromskis, 
#    http://nicaw.wordpress.com/2013/04/18/bash-backup-rotation-script/

# Storage folder where to move backup files
# Must contain backup.monthly backup.weekly backup.daily backup.hourly folders
storage="$1"

NB_HOURLY=48   # nb de sauvegardes horaires a conserver (1 par heure)
NB_DAILY=40    # nb de sauvegardes quotidiennes a conserver
NB_WEEKLY=30   # nombre de sauvegardes hebdomadaires a conserver
NB_MONTHLY=200 # nombre de sauvegardes mensuelles a conserver

# Work in backup directory:
cd $storage

# Source folder where files are backed
source="incoming"

# Destination file names
date_daily=$(date -u +"%Y-%m-%d")
date_hourly=$(date -u +"%Y-%m-%dT%H:%M")

# Get current month and week day number
month_day=$(date -u +"%d")
week_day=$(date -u +"%u")
hour=$(date -u +"%H")

# Optional check if source files exist. Email if failed.
#if [ ! -f $source/archive.tgz ]; then
#ls -l $source/ | mail your@email.com -s "[backup script] Daily backup failed! Please check for missing files."
#fi

# We take files from source folder and move them to
# the appropriate destination folder:

# On first month day do (once)
if [ "$month_day" -eq 1 ] && [ ! -e backup.monthly/$date_daily ]; then
  destination=backup.monthly/$date_daily
else
  # On sunday do (once)
  if [ "$week_day" -eq 7 ] && [ ! -e backup.weekly/$date_daily ]; then
    destination=backup.weekly/$date_daily
  else
    if [ "$hour" -eq 0 ] ; then
      # On any regular day just after midnight do
      destination=backup.daily/$date_daily
     else
      # Each hour do:
      destination=backup.hourly/$date_hourly
     fi
  fi
fi

# Move the files
mkdir $destination
mv $source/* $destination

# hourly - keep NB_HOURLY 
m=$(($NB_HOURLY * 60))
find ./backup.hourly  -maxdepth 1 -mmin +"$m" -type d -exec /bin/rm -r {} \;

# daily - keep for NB_DAILY days
find ./backup.daily/ -maxdepth 1 -mtime +"$NB_DAILY" -type d -exec /bin/rm -r {} \;

# weekly - keep for NB_WEEKLY days
d=$(($NB_WEEKLY * 7))
find ./backup.weekly/ -maxdepth 1 -mtime +"$d" -type d -exec /bin/rm -r {} \;

# monthly - keep for NB_MONTHLY days (approx: 30 days/month)
d=$(($NB_MONTHLY * 30))
find ./backup.monthly/ -maxdepth 1 -mtime +"$d" -type d -exec /bin/rm -r {} \;
