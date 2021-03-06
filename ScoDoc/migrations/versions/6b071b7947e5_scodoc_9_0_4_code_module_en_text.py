"""ScoDoc 9.0.4: code module en Text

Revision ID: 6b071b7947e5
Revises: 993ce4a01d57
Create Date: 2021-08-27 16:00:27.322153

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6b071b7947e5'
down_revision = '993ce4a01d57'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('notes_modules', 'code',
               existing_type=sa.VARCHAR(length=32),
               type_=sa.Text(),
               existing_nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('notes_modules', 'code',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=32),
               existing_nullable=False)
    # ### end Alembic commands ###
