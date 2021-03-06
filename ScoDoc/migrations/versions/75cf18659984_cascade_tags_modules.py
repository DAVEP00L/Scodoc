"""cascade tags modules

Revision ID: 75cf18659984
Revises: d74b4e16fb3c
Create Date: 2021-10-26 10:17:15.547905

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '75cf18659984'
down_revision = 'd74b4e16fb3c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('notes_modules_tags_tag_id_fkey', 'notes_modules_tags', type_='foreignkey')
    op.drop_constraint('notes_modules_tags_module_id_fkey', 'notes_modules_tags', type_='foreignkey')
    op.create_foreign_key(None, 'notes_modules_tags', 'notes_tags', ['tag_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'notes_modules_tags', 'notes_modules', ['module_id'], ['id'], ondelete='CASCADE')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'notes_modules_tags', type_='foreignkey')
    op.drop_constraint(None, 'notes_modules_tags', type_='foreignkey')
    op.create_foreign_key('notes_modules_tags_module_id_fkey', 'notes_modules_tags', 'notes_modules', ['module_id'], ['id'])
    op.create_foreign_key('notes_modules_tags_tag_id_fkey', 'notes_modules_tags', 'notes_tags', ['tag_id'], ['id'])
    # ### end Alembic commands ###
