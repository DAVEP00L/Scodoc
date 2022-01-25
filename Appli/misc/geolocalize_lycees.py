# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# Gestion scolarite IUT
#
# Copyright (c) 2001 - 2012 Emmanuel Viennet.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#   Emmanuel Viennet      emmanuel.viennet@viennet.net
#
##############################################################################

"""Géolocalisation du fichiers des lycees (etablissements.csv)
Ajoute deux colonnes: LAT, LONG

Utilise geopy http://www.geopy.org/ et l'API Google

"""

from geopy import geocoders
import time

SOURCE = '../config/etablissements-orig.csv'
DEST = '../config/etablissements-geocode.csv'


g = geocoders.Google(domain="maps.google.fr") #, api_key='XXX')

inf = open(SOURCE)
out = open(DEST, 'w')

head = inf.readline()
out.write(head.strip() + ';LAT;LNG'+'\n')
for line in inf:
    address = ' '.join(line.split(';')[2:]).strip()
    print address
    try:
        place, (lat, lng) = g.geocode(address)
    except: # multiple possible locations ?
        time.sleep(0.11)
        try:
            place, (lat, lng) = g.geocode(address + ' France', exactly_one=False)[0]
        except:
            place, (lat, lng) = 'NOT FOUND', (0.,0.)
    print "%s: %.5f, %.5f" % (address, lat, lng)  
    out.write( line.strip() + ';%s;%s\n' % (lat,lng) )
    time.sleep(0.11) # Google API Rate limit of 10 requests per second.

inf.close()
out.close()
