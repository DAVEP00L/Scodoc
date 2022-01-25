# -*- coding: utf-8 -*-

import os
import random
from pathlib import Path

cur_dir = Path(os.path.abspath(__file__)).parent

# Noms et prénoms les plus fréquents en France:
NOMS = [x.strip() for x in open(cur_dir / "nomsprenoms" / "noms.txt").readlines()]
PRENOMS_H = [
    x.strip() for x in open(cur_dir / "nomsprenoms" / "prenoms-h.txt").readlines()
]
PRENOMS_F = [
    x.strip() for x in open(cur_dir / "nomsprenoms" / "prenoms-f.txt").readlines()
]
PRENOMS_X = [
    x.strip() for x in open(cur_dir / "nomsprenoms" / "prenoms-x.txt").readlines()
]


def nomprenom(civilite):
    """Un nom et un prenom au hasard,
    toujours en majuscules. Pour tests et démos.
    """
    if civilite == "F":
        prenom = random.choice(PRENOMS_F)
    elif civilite == "M":
        prenom = random.choice(PRENOMS_H)
    elif civilite == "X":
        prenom = random.choice(PRENOMS_X)
    else:
        raise ValueError("civilite must be M, F or X")
    return random.choice(NOMS).upper(), prenom.upper()
