# -*- coding: utf-8 -*-
"""将 unicorn 空间推荐看板的 SQL 产品条件统一为 ``prod = 110000030``。"""

from __future__ import annotations

import repair_gig_recommended_dashboard_product_id as repair


PROFILE = {
    "tenant_id": 7493583885482070016,
    "tenant_public_id": "WSWGCD2XXN",
    "tenant_name": "unicorn",
    "bound_datasource": 9,
    "roi_datasource": 16,
    "target_product_id": "110000030",
    "old_product_counts": {"110000047": 158, "110000038": 36},
    "missing_filter_dashboard_id": "23530c49bf6342e7a14d296db984b655",
    "missing_filter_chart_id": "2a4676f86d7642faa0c21be327f9acbb",
    "excluded_user_dashboard_id": "ced94744471e47abbc389a77a7e98a1e",
    "excluded_user_dashboard_ids": (
        "6e34c464672743028dba7085949a3011",
        "ced94744471e47abbc389a77a7e98a1e",
    ),
    "lock_key": "repair-unicorn-recommended-dashboard-product-id-v1",
    "backup_kind": "unicorn_recommended_dashboard_product_id_repair_v1",
    "backup_filename_prefix": "unicorn_recommended_dashboard_product_id",
    "dashboards": {
        "06983ff7cf7248f1a0baade2d723587c": ("实时看板", "bound", 2),
        "23530c49bf6342e7a14d296db984b655": ("养成看板", "bound", 2),
        "3cce6ad2532e435886e65030764772e1": ("留存分析", "bound", 5),
        "435b7d52f4af447dbb877364345cd229": ("活跃看板", "bound", 7),
        "70a9b8167124499999e3c14cfbece2c6": ("付费概览", "bound", 6),
        "849356dd6e61432dbac036ebd47d2af7": ("核心看板", "bound", 15),
        "8560dfb189f34e8bac6ef5b9541868b4": ("渠道分析", "bound", 5),
        "9fc56e59c92f434f95ddf5db95ffdf17": ("新增看板", "bound", 5),
        "bfdca1687f2c48b7bffc10bd9fcd5d75": ("投放看板", "bound", 3),
        "dcb7645772724045bf3097811b2e9a14": ("ROI看板", "roi", 5),
    },
}


def main() -> None:
    repair.configure_profile(PROFILE)
    repair.main()


if __name__ == "__main__":
    main()
