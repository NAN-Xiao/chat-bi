"""用结构化表达式校验替代平台补零规则的列名正则。"""
from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op

revision = '167platformzerofillexpression'
down_revision = 'a71d3c9e6b20'
branch_labels = None
depends_on = None

SKILL_MARKER = '<!-- platform-foundation-skill:sql-date-grouping:v1 -->'
LEGACY_PATTERN = (
    r'\bcoalesce\s*\(\s*(?:[`\"\[]?\w+[`\"\]]?\s*\.\s*)?'
    r'[`\"\[]?\w+[`\"\]]?\s*,\s*0(?:\.0+)?\s*\)'
)
LEGACY_HOUR_PATTERN = (
    r'\b(?:hour_offsets?|hour_series|hour_spine|hour_calendar|hour_numbers|hours)\b'
    r'|\b(?:generate_series|sequence)\s*\('
)


def upgrade_prompt(prompt: str) -> str:
    def replace(match):
        rules = json.loads(match.group(1))
        items = rules if isinstance(rules, list) else [rules]
        changed = False
        for rule in items:
            patterns = rule.get('required_sql_patterns', [])
            if LEGACY_PATTERN in patterns:
                rule['required_sql_patterns'] = [pattern for pattern in patterns if pattern != LEGACY_PATTERN]
                rule['required_zero_fill'] = True
                changed = True
            if LEGACY_HOUR_PATTERN in patterns:
                rule['required_sql_patterns'] = [pattern for pattern in rule.get('required_sql_patterns', []) if pattern != LEGACY_HOUR_PATTERN]
                rule['required_hour_sequence'] = True
                changed = True
        if not changed:
            return match.group(0)
        return '<!-- data-skill-sql-validation: ' + json.dumps(rules, ensure_ascii=False, separators=(',', ':')) + ' -->'
    return re.sub(r'<!--\s*data-skill-sql-validation\s*:\s*(.*?)\s*-->', replace, prompt, flags=re.DOTALL)


def downgrade_prompt(prompt: str) -> str:
    def replace(match):
        rules = json.loads(match.group(1))
        items = rules if isinstance(rules, list) else [rules]
        changed = False
        for rule in items:
            for flag, pattern in (('required_zero_fill', LEGACY_PATTERN), ('required_hour_sequence', LEGACY_HOUR_PATTERN)):
                if rule.get(flag) is True:
                    rule.pop(flag)
                    patterns = rule.setdefault('required_sql_patterns', [])
                    if pattern not in patterns:
                        patterns.append(pattern)
                    changed = True
        if not changed:
            return match.group(0)
        return '<!-- data-skill-sql-validation: ' + json.dumps(rules, ensure_ascii=False, separators=(',', ':')) + ' -->'
    return re.sub(r'<!--\s*data-skill-sql-validation\s*:\s*(.*?)\s*-->', replace, prompt, flags=re.DOTALL)


def _update_prompts(transform):
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id,prompt FROM custom_prompt
        WHERE tenant_id=1 AND type='DATA_SKILL' AND visibility_scope='PLATFORM_PUBLIC'
          AND COALESCE(specific_ds,FALSE)=FALSE AND prompt LIKE :marker
        FOR UPDATE
    """), {'marker': '%' + SKILL_MARKER + '%'}).mappings().all()
    for row in rows:
        updated = transform(row['prompt'])
        if updated != row['prompt']:
            bind.execute(sa.text('UPDATE custom_prompt SET prompt=:prompt,embedding=NULL,embedding_signature=NULL WHERE id=:id'),
                         {'prompt': updated, 'id': row['id']})


def upgrade():
    _update_prompts(upgrade_prompt)


def downgrade():
    # 旧版本不识别结构化标记，必须恢复其能够执行的约束，不能静默跳过补零校验。
    _update_prompts(downgrade_prompt)
