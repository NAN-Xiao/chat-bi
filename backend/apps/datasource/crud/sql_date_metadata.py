from sqlmodel import select

from apps.system.models.tenant import TenantTrackingConfigModel, TenantTrackingFieldModel


def load_date_field_encodings(session, tenant_id: int, datasource_id: int, permission_scope: dict) -> dict[tuple[str, str], str]:
    if not permission_scope:
        return {}
    fields = session.exec(
        select(
            TenantTrackingFieldModel.table_name,
            TenantTrackingFieldModel.field_name,
            TenantTrackingFieldModel.extra_properties,
        )
        .join(TenantTrackingConfigModel, (
            (TenantTrackingConfigModel.tenant_id == TenantTrackingFieldModel.tenant_id)
            & (TenantTrackingConfigModel.datasource_id == TenantTrackingFieldModel.datasource_id)
        ))
        .where(
            TenantTrackingFieldModel.tenant_id == tenant_id,
            TenantTrackingFieldModel.datasource_id == datasource_id,
            TenantTrackingConfigModel.enabled.is_(True),
            TenantTrackingFieldModel.expression.is_(None),
            TenantTrackingFieldModel.json_path.is_(None),
        )
    ).all()
    formats = {
        'yyyymmdd': '%Y%m%d',
        'yyyymmdd_integer': '%Y%m%d',
        'yyyymmdd_number': '%Y%m%d',
        'yyyymmdd_text': '%Y%m%d',
        'iso_date': '%Y-%m-%d',
        'iso8601_date': '%Y-%m-%d',
    }
    encodings = {}
    for table_name, field_name, properties in fields:
        allowed_fields = permission_scope.get(table_name.lower(), {}).get('fields', set())
        if field_name.lower() not in allowed_fields or not isinstance(properties, dict):
            continue
        encoding = str(properties.get('encoding') or '').strip().lower().replace('-', '_')
        if encoding in formats:
            encodings[(table_name.lower(), field_name.lower())] = formats[encoding]
    return encodings
