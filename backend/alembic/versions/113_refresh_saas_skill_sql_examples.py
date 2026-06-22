"""113_refresh_saas_skill_sql_examples

Revision ID: e5a7c9d1f3b4
Revises: d4f6a7b8c9e0
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op


revision = "e5a7c9d1f3b4"
down_revision = "d4f6a7b8c9e0"
branch_labels = None
depends_on = None


def _load_saas_skills_module():
    module_path = Path(__file__).with_name("112_expand_saas_data_skills.py")
    spec = importlib.util.spec_from_file_location("saas_skill_revision_112", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load SaaS skill revision from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = op
    return module


def upgrade() -> None:
    saas_skills = _load_saas_skills_module()
    saas_skills.op = op
    saas_skills._create_saas_20_skills()


def downgrade() -> None:
    # The prior revision already creates the same SaaS skills without SQL templates.
    # Keep the records active on downgrade; older code can still read the prompts.
    return None
