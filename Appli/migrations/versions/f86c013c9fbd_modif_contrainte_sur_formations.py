"""modif contrainte sur formations

Revision ID: f86c013c9fbd
Revises: 669065fb2d20
Create Date: 2021-09-19 21:30:42.240422

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f86c013c9fbd'
down_revision = '669065fb2d20'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('notes_formations_acronyme_titre_version_key', 'notes_formations', type_='unique')
    op.create_unique_constraint(None, 'notes_formations', ['dept_id', 'acronyme', 'titre', 'version'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'notes_formations', type_='unique')
    op.create_unique_constraint('notes_formations_acronyme_titre_version_key', 'notes_formations', ['acronyme', 'titre', 'version'])
    # ### end Alembic commands ###
