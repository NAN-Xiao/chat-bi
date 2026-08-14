# -*- coding: utf-8 -*-
"""将 lds 空间推荐看板的 SQL 产品条件统一为 ``prod = 110000039``。"""

from __future__ import annotations

import repair_gig_recommended_dashboard_product_id as repair


PROFILE = {
    "tenant_id": 7493272675721154560,
    "tenant_public_id": "WS6MEJGDSA",
    "tenant_name": "lds",
    "bound_datasource": 10,
    "roi_datasource": 14,
    "target_product_id": "110000039",
    "old_product_counts": {"110000047": 158, "110000038": 36},
    "missing_filter_dashboard_id": "e39cc3bea92e49a8a0cd2009a4c38a5a",
    "missing_filter_chart_id": "99e31069e8b54504a321b7b8066bf946",
    "excluded_user_dashboard_id": "c338394f0f424eb58a7ba6a9449aff2e",
    "lock_key": "repair-lds-recommended-dashboard-product-id-v1",
    "backup_kind": "lds_recommended_dashboard_product_id_repair_v1",
    "backup_filename_prefix": "lds_recommended_dashboard_product_id",
    "dashboards": {
        "028e33c255824cda93320e78febe8d71": ("核心看板", "bound", 15),
        "0ce1b43d3640440f9f6ff78b4d4a38d2": ("留存分析", "bound", 5),
        "1c6f7e9d972b437dbb2330d85028528f": ("ROI看板", "roi", 5),
        "68a85458fa9f4c74b77376b650199c6b": ("付费概览", "bound", 6),
        "8900567ff2214a938774390d6f28ea8a": ("渠道分析", "bound", 5),
        "9e38e694e7db486298f57a5c7f462fec": ("新增看板", "bound", 5),
        "aab44e74534e4c8d940a48df34018ae4": ("实时看板", "bound", 2),
        "b9b54793e3da4cbab3a9a60f32b6f5f0": ("活跃看板", "bound", 7),
        "d11e4d66a255449fbb00448dd22bac31": ("投放看板", "bound", 3),
        "e39cc3bea92e49a8a0cd2009a4c38a5a": ("养成看板", "bound", 2),
    },
}


def main() -> None:
    repair.configure_profile(PROFILE)
    repair.main()


if __name__ == "__main__":
    main()
