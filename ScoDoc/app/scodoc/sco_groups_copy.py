from app import db

from app.scodoc import sco_groups
import app.scodoc.notesdb as ndb


def clone_partitions_and_groups(
    orig_formsemestre_id: int, formsemestre_id: int, inscrit_etuds=False
):
    """Crée dans le semestre formsemestre_id les mêmes partitions et groupes que ceux
    de orig_formsemestre_id.
    Si inscrit_etuds, inscrit les mêmes étudiants (rarement souhaité).
    """
    list_groups_per_part = []
    list_groups = []
    groups_old2new = {}  # old group_id : new_group_id
    # Création des partitions:
    for part in sco_groups.get_partitions_list(orig_formsemestre_id):
        if part["partition_name"] is not None:
            partname = part["partition_name"]
            new_partition_id = sco_groups.partition_create(
                formsemestre_id,
                partition_name=partname,
                numero=part["numero"],
                redirect=False,
            )
            for group in sco_groups.get_partition_groups(part):
                if group["group_name"] != None:
                    list_groups.append(group)
            list_groups_per_part.append([new_partition_id, list_groups])
            list_groups = []

    # Création des groupes dans les nouvelles partitions:
    for newpart in sco_groups.get_partitions_list(formsemestre_id):
        for (new_partition_id, list_groups) in list_groups_per_part:
            if newpart["partition_id"] == new_partition_id:
                for group in list_groups:
                    new_group_id = sco_groups.create_group(
                        new_partition_id, group_name=group["group_name"]
                    )
                    groups_old2new[group["group_id"]] = new_group_id
    #
    if inscrit_etuds:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor()
        for old_group_id, new_group_id in groups_old2new.items():
            cursor.execute(
                """
                WITH etuds AS (
                    SELECT gm.etudid
                    FROM group_membership gm, notes_formsemestre_inscription ins
                    WHERE ins.etudid = gm.etudid
                    AND ins.formsemestre_id = %(orig_formsemestre_id)s
                    AND gm.group_id=%(old_group_id)s
                    )
                INSERT INTO group_membership (etudid, group_id)
                SELECT *, %(new_group_id)s FROM etuds
                ON CONFLICT DO NOTHING
                """,
                {
                    "orig_formsemestre_id": orig_formsemestre_id,
                    "old_group_id": old_group_id,
                    "new_group_id": new_group_id,
                },
            )
        cnx.commit()
