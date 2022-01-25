"""ScoDoc 9.0.4: ajout id scodoc7 pour migrations (archives)

Revision ID: 017e32eb4773
Revises: 6b071b7947e5
Create Date: 2021-08-27 21:58:05.317092

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017e32eb4773'
down_revision = '6b071b7947e5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('identite', sa.Column('scodoc7_id', sa.Text(), nullable=True))
    op.add_column('notes_formsemestre', sa.Column('scodoc7_id', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('notes_formsemestre', 'scodoc7_id')
    op.drop_column('identite', 'scodoc7_id')
    # ### end Alembic commands ###
