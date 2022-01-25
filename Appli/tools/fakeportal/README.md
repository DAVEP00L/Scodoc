# Portail pour tests

Un faux portail "apogée" pour inscrire de faux étudiants avec photos. Utile pour
tester les fonctions d'inscription/synchronisation, et aussi pour peupler
rapidement une base de donnée.

Le serveur écoute par défaut sur `tcp/8678`. Il faudra paramétrer l'URL du
"portail" dans les préférences du ScoDoc à tester, qui est en général sur le
même hôte, donc `http://localhost:8678`.

Lancement:

    cd /opt/scodoc
    ./tools/fakeportal/fakeportal.py 




