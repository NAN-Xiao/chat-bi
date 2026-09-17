"""Code-owned validation contracts cannot be waived by knowledge review."""
from apps.knowledge_base.context import KnowledgeContextError


EXECUTABLE_SQL_GUIDANCE = '''
当前验收目标是生成并执行可用 SQL，语义质量不是执行门槛。
优先遵循知识库和 Data Skill；维度、指标口径、事件归类、日期补齐或业务定义不明确时，
允许基于当前已授权的真实表列作近似分析，必须在 message 中说明假设或缺失定义。
不能仅因语义不确定返回 success=false，不得为满足语义偏好反复重写已可执行 SQL。
真实数据源、表列、数据库方言、参数解析、权限过滤及只读限制仍为硬约束。
不得编造不存在的表列、虚构执行结果，或用 SELECT 1 等无关 SQL 冒充业务查询。
没有可用的授权数据或无法支持任何相关查询时应明确说明，不能越权或伪造数据。
图表只能绑定实际结果列；成功执行不代表业务口径已经验证。
'''


_RULE_TYPES = {'sql_structure', 'result_contract', 'security', 'business'}
_SQL_CONTRACT_KEYS = {
    'required_outer_select_cross_join', 'required_complete_hour_sequence',
    'required_scoped_max_time', 'required_zero_fill', 'required_hour_sequence',
}
_RESULT_CONTRACT_KEYS = {
    'required_fields', 'required_field_keywords', 'require_continuous_sequence',
}


def knowledge_review_allowed(rule: dict, *, surface: str) -> bool:
    # Unclassified declarations remain enforceable local contracts. Review is
    # an explicit business-rule capability, never inferred from free text/SQL.
    rule_type = rule.get('rule_type', 'sql_structure' if surface == 'sql' else 'result_contract')
    if not isinstance(rule_type, str) or rule_type not in _RULE_TYPES:
        raise KnowledgeContextError('data_skill_validation_config_invalid',
                                    'Data Skill 校验规则的 rule_type 无效，请检查配置。')
    contract_keys = _SQL_CONTRACT_KEYS if surface == 'sql' else _RESULT_CONTRACT_KEYS
    return rule_type == 'business' and not any(rule.get(key) for key in contract_keys)
