#!/usr/bin/env python3

"""Simple fake HTTP serveur
    emulating "Apogee" Web service
"""
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse
import http.server
import os
import random
import signal
import socketserver
import sys
import time

from gen_nomprenoms import nomprenom

script_dir = Path(os.path.abspath(__file__)).parent
os.chdir(script_dir)

# Les "photos" des étudiants
FAKE_FACES_PATHS = list((Path("faces").glob("*.jpg")))

# Etudiant avec tous les champs (USPN)
ETUD_TEMPLATE_FULL = open(script_dir / "etud_template.xml").read()
# Etudiant avec seulement les champs requis
ETUD_TEMPLATE_MINI = open(script_dir / "etud_minimal_template.xml").read()

ETUD_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<etudiants>"""
ETUD_TAIL = """</etudiants>
"""


def make_random_etud(nip, etape=None, annee=None, template=ETUD_TEMPLATE_FULL):
    """return XML for a student"""
    random.seed(nip)  # deterministic choice based on nip
    gender = random.choice(("M", "F"))
    nom, prenom = nomprenom(gender)
    if not etape:
        etape = random.choice(("V1RT", "V2RT", "V2RT2", ""))
    if not annee:
        annee = time.strftime("%Y")  # current year
    diplome = "VDRT"
    data = template.format(
        nip=nip,
        gender=gender,
        nom=nom,
        prenom=prenom,
        etape=etape,
        diplome=diplome,
        annee=annee,
        ville_naissance=random.choice(("Paris", "Berlin", "Londres", "")),
        code_dep_naissance=random.choice(("75", "99", "89")),
        libelle_dep_naissance="nom département",
        # nomlycee=
    )
    return data


def make_random_etape_etuds(etape, annee):
    """Liste d'etudiants d'une etape"""
    random.seed(etape + annee)
    nb = random.randint(0, 50)
    print(f"generating {nb} students")
    L = []
    for i in range(nb):
        if i % 2:
            template = ETUD_TEMPLATE_MINI
        else:
            template = ETUD_TEMPLATE_FULL
        nip = str(random.randint(10000000, 99999999))  # 8 digits
        L.append(make_random_etud(nip, etape=etape, annee=annee, template=template))
    return "\n".join(L)


def get_photo_filename(nip: str) -> str:
    """get an existing filename for a fake photo, found in faces/
    Returns a path relative to the current working dir
    """
    #
    nb_faces = len(FAKE_FACES_PATHS)
    if nb_faces == 0:
        print("WARNING: aucun fichier image disponible !")
        return ""
    return FAKE_FACES_PATHS[hash(nip) % nb_faces]


class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def send_xml(self, data):
        self.send_response(200)
        self.send_header("Content-type", "text/xml;charset=UTF-8")
        self.end_headers()
        self.wfile.write(bytes(data, "utf8"))

    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        print(f"path={self.path}", file=sys.stderr)
        print(query_components, file=sys.stderr)

        if "etapes" in self.path.lower():
            self.path = str(Path(script_dir / "etapes.xml").relative_to(Path.cwd()))
        elif "scodocEtudiant" in self.path:  # API v2
            # 2 forms: nip=xxx or etape=eee&annee=aaa
            if "nip" in query_components:
                nip = query_components["nip"][0]
                print(f"requesting nip={nip}")
                data = ETUD_HEAD + make_random_etud(nip) + ETUD_TAIL
                return self.send_xml(data)
            elif "etape" in query_components:
                etape = query_components["etape"][0]
                print(f"requesting etape={etape}", file=sys.stderr)
                if "annee" in query_components:
                    annee = query_components["annee"][0]
                    data = ETUD_HEAD + make_random_etape_etuds(etape, annee) + ETUD_TAIL
                    return self.send_xml(data)
                else:
                    print(
                        f"Error 404: (missing annee) path={self.path}", file=sys.stderr
                    )
                    self.send_response(404)
                    return
            else:
                print(
                    f"Error 404: (missing nip or etape) path={self.path}",
                    file=sys.stderr,
                )
                self.send_response(404)
                return
        elif "getPhoto" in self.path or "scodocPhoto" in self.path:
            nip = query_components["nip"][0]
            self.path = str(get_photo_filename(nip))
            print(f"photo for nip={nip}: {self.path}")
        else:
            print(f"Error 404: path={self.path}")
            self.send_response(404)
            return

        # Sending an '200 OK' response
        self.send_response(200)
        http.server.SimpleHTTPRequestHandler.do_GET(self)

        return


PORT = 8678


def signal_handler(sig, frame):
    print("You pressed Ctrl+C!")
    raise SystemExit()


signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    # Start the server
    print(f"Server listening on port {PORT}...")
    my_server = socketserver.TCPServer(("", PORT), MyHttpRequestHandler)
    try:
        my_server.serve_forever()
    finally:
        print("shutting down...")
        my_server.shutdown()
