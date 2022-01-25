# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Chargement de la configuration locale
"""
import os
import sys

from app import log
from app.scodoc import sco_config

# scodoc_local defines a CONFIG object
# here we check if there is a local config file


def load_local_configuration(scodoc_cfg_dir):
    """Load local configuration file (if exists)
    and merge it with CONFIG.
    """
    local_config_filename = os.path.join(scodoc_cfg_dir, "scodoc_local.py")
    local_config = None
    if os.path.exists(local_config_filename):
        if not scodoc_cfg_dir in sys.path:
            sys.path.insert(0, scodoc_cfg_dir)
        try:
            from scodoc_local import CONFIG as local_config

            log("imported %s" % local_config_filename)
        except ImportError:
            log("Error: can't import %s" % local_config_filename)
        del sys.path[0]
    if local_config is None:
        return
    # Now merges local config in our CONFIG
    for x in [x for x in local_config if x[0] != "_"]:
        v = local_config.get(x)
        if not x in sco_config.CONFIG:
            log(f"Warning: local config setting unused parameter {x} (skipped)")
        else:
            if v != sco_config.CONFIG[x]:
                log(f"Setting parameter {x} from {local_config_filename}")
                sco_config.CONFIG[x] = v
