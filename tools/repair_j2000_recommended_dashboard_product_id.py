# -*- coding: utf-8 -*-
"""将 j2000 空间推荐看板的 SQL 产品条件统一为 ``prod = 110000034``。"""

from __future__ import annotations

import repair_gig_recommended_dashboard_product_id as repair


PROFILE = {
    "tenant_id": 7493583991958671360,
    "tenant_public_id": "WSCWXDWV48",
    "tenant_name": "j2000",
    "bound_datasource": 11,
    "roi_datasource": 15,
    "target_product_id": "110000034",
    "old_product_counts": {"110000047": 158, "110000038": 36},
    "missing_filter_dashboard_id": "970030f34556447f9b513c1c5301ed2e",
    "missing_filter_chart_id": "99e31069e8b54504a321b7b8066bf946",
    "excluded_user_dashboard_id": "67f3988aa2ce47f4ab33d8586c3b26a5",
    "lock_key": "repair-j2000-recommended-dashboard-product-id-v1",
    "backup_kind": "j2000_recommended_dashboard_product_id_repair_v1",
    "backup_filename_prefix": "j2000_recommended_dashboard_product_id",
    "dashboards": {
        "135c99728aae4664b68fd8c97b278934": ("投放看板", "bound", 3),
        "1c499cba259b497a852291379b0d80a6": ("留存分析", "bound", 5),
        "34a2f15ecc9d417d8ba378d042fdd08a": ("核心看板", "bound", 15),
        "4946ab9002bf4845a937972271d8bb02": ("付费概览", "bound", 6),
        "7df439da88974fbdba989fee86877d30": ("活跃看板", "bound", 7),
        "970030f34556447f9b513c1c5301ed2e": ("养成看板", "bound", 2),
        "ab30f1f1dd15450c8d8fc5d5cd958c06": ("渠道分析", "bound", 5),
        "db7dee845ff24d348263d1b9a8371cb4": ("新增看板", "bound", 5),
        "f4752ac1104e4b88aa53b377a3402055": ("实时看板", "bound", 2),
        "ff98c30d2a844fb1b0d4bf2a07eb2a3a": ("ROI看板", "roi", 5),
    },
}


def main() -> None:
    repair.configure_profile(PROFILE)
    repair.main()


if __name__ == "__main__":
    main()
