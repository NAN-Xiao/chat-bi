"""120_refresh_saas_skill_scope_wording

Revision ID: e0f1a2b3c4d5
Revises: d9e8f7a6b5c4
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op


revision = "e0f1a2b3c4d5"
down_revision = "d9e8f7a6b5c4"
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
    saas_skills._create_saas_20_skills()


def downgrade() -> None:
    return None
