# -*- coding: UTF-8 -*

"""Groups & partitions
"""
from typing import Any

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN
from app.models import GROUPNAME_STR_LEN


class Partition(db.Model):
    """Partition: découpage d'une promotion en groupes"""

    __table_args__ = (db.UniqueConstraint("formsemestre_id", "partition_name"),)

    id = db.Column(db.Integer, primary_key=True)
    partition_id = db.synonym("id")
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
        index=True,
    )
    # "TD", "TP", ... (NULL for 'all')
    partition_name = db.Column(db.String(SHORT_STR_LEN))
    # numero = ordre de presentation)
    numero = db.Column(db.Integer)
    bul_show_rank = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    show_in_lists = db.Column(
        db.Boolean(), nullable=False, default=True, server_default="true"
    )

    def __init__(self, **kwargs):
        super(Partition, self).__init__(**kwargs)
        if self.numero is None:
            # génère numero à la création
            last_partition = Partition.query.order_by(Partition.numero.desc()).first()
            if last_partition:
                self.numero = last_partition.numero + 1
            else:
                self.numero = 1


class GroupDescr(db.Model):
    """Description d'un groupe d'une partition"""

    __tablename__ = "group_descr"
    __table_args__ = (db.UniqueConstraint("partition_id", "group_name"),)

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.synonym("id")
    partition_id = db.Column(db.Integer, db.ForeignKey("partition.id"))
    #  "A", "C2", ...  (NULL for 'all'):
    group_name = db.Column(db.String(GROUPNAME_STR_LEN))


group_membership = db.Table(
    "group_membership",
    db.Column("etudid", db.Integer, db.ForeignKey("identite.id")),
    db.Column("group_id", db.Integer, db.ForeignKey("group_descr.id")),
    db.UniqueConstraint("etudid", "group_id"),
)
