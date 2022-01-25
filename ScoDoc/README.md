
#            ScoDoc - Gestion de la scolarité - Version ScoDoc 9

(c) Emmanuel Viennet 1999 - 2021 (voir LICENCE.txt)

Installation: voir instructions à jour sur <https://scodoc.org/GuideInstallDebian11>

Documentation utilisateur: <https://scodoc.org>

## Version ScoDoc 9

La version ScoDoc 9 est basée sur Flask (au lieu de Zope) et sur 
**python 3.9+**. 

La version 9.0 s'efforce de reproduire presque à l'identique le fonctionnement 
de ScoDoc7, avec des composants logiciels différents (Debian 11, Python 3,
Flask, SQLAlchemy, au lien de Python2/Zope dans les versions précédentes).



### État actuel (26 sept 21)

 - 9.0 reproduit l'ensemble des fonctions de ScoDoc 7 (donc pas de BUT), sauf:

**Fonctionnalités non intégrées:**
 
 - génération LaTeX des avis de poursuite d'études

 - ancien module "Entreprises" (obsolete)

 
### Lignes de commandes

Voir [https://scodoc.org/GuideConfig](le guide de configuration).


## Organisation des fichiers

L'installation comporte les fichiers de l'application, sous `/opt/scodoc/`, et
les fichiers locaux (archives, photos, configurations, logs) sous
`/opt/scodoc-data`. Par ailleurs, il y a évidemment les bases de données
postgresql et la configuration du système Linux. 

### Fichiers locaux
Sous `/opt/scodoc-data`, fichiers et répertoires appartienant à l'utilisateur `scodoc`. 
Ils ne doivent pas être modifiés à la main, sauf certains fichiers de configuration sous 
`/opt/scodoc-data/config`.

Le répertoire `/opt/scodoc-data` doit être régulièrement sauvegardé.

Principaux contenus:

    /opt/scodoc-data
    /opt/scodoc-data/log             # Fichiers de log ScoDoc
    /opt/scodoc-data/config          # Fichiers de configuration
                 .../config/logos    # Logos de l'établissement
                 .../config/depts    # un fichier par département
    /opt/scodoc-data/photos          # Photos des étudiants
    /opt/scodoc-data/archives        # Archives: PV de jury, maquettes Apogée, fichiers étudiants

## Pour les développeurs

### Installation du code

Installer ScoDoc 9 normalement ([voir la doc](https://scodoc.org/GuideInstallDebian11)).

Puis remplacer `/opt/scodoc` par un clone du git. 

    sudo su
    mv /opt/scodoc /opt/off-scodoc # ou ce que vous voulez
    apt-get install git # si besoin
    cd /opt
    git clone https://scodoc.org/git/viennet/ScoDoc.git
    # (ou bien utiliser votre clone gitea si vous l'avez déjà créé !)
    mv ScoDoc scodoc # important !
    
Il faut ensuite installer l'environnement et le fichier de configuration:

    # Le plus simple est de piquer le virtualenv configuré par l'installeur:
    mv /opt/off-scodoc/venv /opt/scodoc

Et la config:

    ln -s /opt/scodoc-data/.env /opt/scodoc

Cette dernière commande utilise le `.env` crée lors de l'install, ce qui
n'est pas toujours le plus judicieux: vous pouvez modifier son contenu, par
exemple pour travailler en mode "développement" avec `FLASK_ENV=development`.

### Tests unitaires

Certains tests ont besoin d'un département déjà créé, qui n'est pas créé par les 
scripts de tests:
Lancer au préalable:

    flask delete-dept TEST00 && flask create-dept TEST00

Puis dérouler les tests unitaires:

    pytest tests/unit

Ou avec couverture (`pip install pytest-cov`)

    pytest --cov=app --cov-report=term-missing --cov-branch tests/unit/*


#### Utilisation des tests unitaires pour initialiser la base de dev
On peut aussi utiliser les tests unitaires pour mettre la base 
de données de développement dans un état connu, par exemple pour éviter de
recréer à la main étudiants et semestres quand on développe. 

Il suffit de positionner une variable d'environnement indiquant la BD utilisée par les tests:

    export SCODOC_TEST_DATABASE_URI=postgresql:///SCODOC_DEV

(si elle n'existe pas, voir plus loin pour la créer) puis de les lancer
normalement, par exemple: 

    pytest tests/unit/test_sco_basic.py

Il est en général nécessaire d'affecter ensuite un mot de passe à (au moins) 
un utilisateur:

    flask user-password admin

**Attention:** les tests unitaires **effacent** complètement le contenu de la
base de données (tous les départements, et les utilisateurs) avant de commencer !

#### Modification du schéma de la base

On utilise SQLAlchemy avec Alembic et Flask-Migrate.

    flask db migrate -m "message explicatif....."
    flask db upgrade

Ne pas oublier de d'ajouter le script de migration à git (`git add migrations/...`).

**Mémo**: séquence re-création d'une base (vérifiez votre `.env`
ou variables d'environnement pour interroger la bonne base !).

    dropdb SCODOC_DEV
    tools/create_database.sh SCODOC_DEV # créé base SQL
    flask db upgrade # créé les tables à partir des migrations
    flask sco-db-init # ajoute au besoin les constantes (fait en migration 0)
    
    # puis imports:
    flask import-scodoc7-users
    flask import-scodoc7-dept STID SCOSTID

Si la base utilisée pour les dev n'est plus en phase avec les scripts de
migration, utiliser les commandes `flask db history`et `flask db stamp`pour se
positionner à la bonne étape.

### Profiling

Sur une machine de DEV, lancer

    flask profile --host 0.0.0.0 --length 32 --profile-dir /opt/scodoc-data

le fichier `.prof` sera alors écrit dans `/opt/scodoc-data` (on peut aussi utiliser `/tmp`).

Pour la visualisation, [snakeviz](https://jiffyclub.github.io/snakeviz/) est bien:

    pip install snakeviz

puis 

    snakeviz -s --hostname 0.0.0.0 -p 5555 /opt/scodoc-data/GET.ScoDoc......prof 



# Paquet Debian 11

Les scripts associés au paquet Debian (.deb) sont dans `tools/debian`. Le plus
important est `postinst`qui se charge de configurer le système (install ou
upgrade de scodoc9).

La préparation d'une release se fait à l'aide du script
`tools/build_release.sh`. 

