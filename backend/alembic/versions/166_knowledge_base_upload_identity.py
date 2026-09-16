"""记录知识库最近一次文档上传者的身份与姓名快照。"""
from alembic import op
import sqlalchemy as sa

revision = "a71d3c9e6b20"
down_revision = "165platformmysqlsignedgeneration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史记录无法证明最近一次上传者，不以创建者冒充上传者。
    op.add_column("knowledge_base", sa.Column("uploaded_by", sa.BigInteger(), nullable=True))
    op.add_column("knowledge_base", sa.Column("uploaded_by_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_base", "uploaded_by_name")
    op.drop_column("knowledge_base", "uploaded_by")
