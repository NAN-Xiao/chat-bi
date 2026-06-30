import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAND_NAME = "星通数智"
LEGACY_BRAND_NAME = "".join(("SQL", "Bot"))

JSON_COPY_FILES = [
    ROOT / "frontend/src/i18n/zh-CN.json",
    ROOT / "frontend/src/i18n/zh-TW.json",
    ROOT / "frontend/src/i18n/en.json",
    ROOT / "frontend/src/i18n/ko-KR.json",
]

EXPECTED_COPY_SNIPPETS = {
    "frontend/index.html": ["<title>星通数智</title>"],
    "frontend/embedded.html": ["<title>星通数智</title>"],
    "frontend/src/stores/appearance.ts": [
        "const DEFAULT_BRAND_NAME = '星通数智'",
        "name: DEFAULT_BRAND_NAME",
        "document.title = DEFAULT_BRAND_NAME",
        "setTitle(DEFAULT_BRAND_NAME)",
    ],
    "frontend/src/stores/chatConfig.ts": ["shuzhi_name: '星通数智'"],
    "frontend/src/components/layout/index.vue": ['<div class="logo" @click="goHome">星通数智</div>'],
    "frontend/src/views/chat/index.vue": ["t('embedded.i_am_shuzhi')"],
    "frontend/src/i18n/zh-CN.json": ['"i_am_shuzhi": "你好，我是星通数智"'],
    "frontend/src/views/work/index.vue": ["Hello, I'm 星通数智, happy to serve you!"],
    "frontend/src/views/system/parameter/index.vue": ["'chat.shuzhi_name': '星通数智'"],
    "backend/common/core/config.py": ['PROJECT_NAME: str = "星通数智"'],
    "backend/main.py": [
        "✅ 星通数智 初始化完成",
        "星通数智 应用关闭",
        "星通数智 API Document",
        "星通数智 API 文档",
        "星通数智 API Docs",
        'name="星通数智 MCP Server"',
        'description="星通数智 MCP Server"',
    ],
    "backend/apps/chat/models/chat_model.py": ['shuzhi_name: str = "星通数智"'],
    "backend/apps/analysis_assistant/api/analysis_assistant.py": [
        "你是星通数智内置的综合分析助手",
    ],
    "docker-compose.yaml": ['PROJECT_NAME: "星通数智"'],
    "installer/shuzhi/templates/shuzhi.conf": ['PROJECT_NAME="星通数智"'],
    "README.md": [
        "星通数智是一款基于大语言模型和 RAG 的智能报表系统",
        "快速开始",
        "基于星通数智的源代码",
    ],
    "docs/README.en.md": [
        "星通数智 is an intelligent data query system based on large language models and RAG.",
        "Installation and Deployment",
        "based on the 星通数智 source code",
    ],
    "installer/sctl": [
        "星通数智控制脚本",
        "查看星通数智服务运行状态",
        "星通数智服务状态",
    ],
    "installer/uninstall.sh": [
        "即将卸载星通数智服务",
        "停止星通数智服务",
        "星通数智服务卸载完成",
    ],
    "installer/install.conf": [
        "## 星通数智端口",
        "## 星通数智系统数据库库名",
        "## 星通数智 Secret Key",
    ],
    "frontend/src/utils/utils.ts": ["document.title = title || '星通数智'"],
    "frontend/public/vite-shuzhi.svg": ["<title>星通数智</title>"],
    "backend/common/core/app_cache.py": [
        "星通数智使用内存缓存",
        "星通数智使用Redis缓存",
        "星通数智未启用缓存",
    ],
    "backend/common/core/security_config.py": ["for the 星通数智 application"],
    "tools/seed_slg_bi_training.py": ["into the 星通数智系统库"],
}

EXPECTED_EXISTING_CORE_DB_SNIPPETS = {
    ".env": [
        "SHUZHI_DB_DB=zhishu_bi",
        "POSTGRES_DB=zhishu_bi",
    ],
    "backend/common/core/config.py": ['SHUZHI_DB_DB: str = "zhishu_bi"'],
    "tools/backend-local.ps1": ['$appSystemDbName = "zhishu_bi"'],
    "tools/stack-local.ps1": ['$appSystemDbName = "zhishu_bi"'],
    "tools/worker-local.ps1": [
        '$env:POSTGRES_DB = "zhishu_bi"',
        '$env:SHUZHI_DB_DB = "zhishu_bi"',
    ],
    "tools/core_system_db.py": ['"dbname": "zhishu_bi"'],
}


def _flatten_json_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_json_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_json_values(item)
    elif isinstance(value, str):
        yield value


def test_i18n_visible_copy_uses_new_brand_name():
    offenders = []
    for file_path in JSON_COPY_FILES:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        for value in _flatten_json_values(data):
            if LEGACY_BRAND_NAME in value:
                offenders.append(f"{file_path.relative_to(ROOT)}: {value}")

    assert offenders == []


def test_key_visible_copy_files_use_new_brand_name():
    missing = []
    for relative_path, snippets in EXPECTED_COPY_SNIPPETS.items():
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in content:
                missing.append(f"{relative_path}: {snippet}")

    assert missing == []


def test_local_existing_core_database_name_is_not_rebranded():
    missing = []
    for relative_path, snippets in EXPECTED_EXISTING_CORE_DB_SNIPPETS.items():
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in content:
                missing.append(f"{relative_path}: {snippet}")

    assert missing == []
