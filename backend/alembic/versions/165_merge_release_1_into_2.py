"""合并 release 1.0.0 与 release 2.0.0 的迁移链。"""

from __future__ import annotations


revision = "165mergerelease1into2"
down_revision = ("157workspaceprojectid", "164platformhistoricalhourly")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
