"""Добавлены изменения в модели

Revision ID: 085772be20ad
Revises: 
Create Date: 2024-12-17 17:43:25.607002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '085772be20ad'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('reminders', 'time')
    op.drop_column('reminders', 'day_of_week')
    op.drop_column('user_states', 'reminder_msg_id')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user_states', sa.Column('reminder_msg_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('reminders', sa.Column('day_of_week', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('reminders', sa.Column('time', postgresql.TIMESTAMP(), autoincrement=False, nullable=False))
    # ### end Alembic commands ###
