import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAND_NAME = "星通智数"

JSON_COPY_FILES = [
    ROOT / "frontend/src/i18n/zh-CN.json",
    ROOT / "frontend/src/i18n/zh-TW.json",
    ROOT / "frontend/src/i18n/en.json",
    ROOT / "frontend/src/i18n/ko-KR.json",
]

EXPECTED_COPY_SNIPPETS = {
    "frontend/index.html": ["<title>星通智数</title>"],
    "frontend/embedded.html": ["<title>星通智数</title>"],
    "frontend/src/stores/appearance.ts": [
        "const DEFAULT_BRAND_NAME = '星通智数'",
        "name: DEFAULT_BRAND_NAME",
        "document.title = DEFAULT_BRAND_NAME",
        "setTitle(DEFAULT_BRAND_NAME)",
    ],
    "frontend/src/stores/chatConfig.ts": ["sqlbot_name: '星通智数'"],
    "frontend/src/components/layout/index.vue": ['<div class="logo">星通智数</div>'],
    "frontend/src/views/chat/index.vue": ["'你好，我是星通智数'"],
    "frontend/src/views/work/index.vue": ["Hello, I'm 星通智数, happy to serve you!"],
    "frontend/src/views/system/parameter/index.vue": ["'chat.sqlbot_name': '星通智数'"],
    "backend/common/core/config.py": ['PROJECT_NAME: str = "星通智数"'],
    "backend/main.py": [
        "✅ 星通智数 初始化完成",
        "星通智数 应用关闭",
        "星通智数 API Document",
        "星通智数 API 文档",
        "星通智数 API Docs",
        'name="星通智数 MCP Server"',
        'description="星通智数 MCP Server"',
    ],
    "backend/apps/chat/models/chat_model.py": ['sqlbot_name: str = "星通智数"'],
    "backend/apps/analysis_assistant/api/analysis_assistant.py": [
        "你是星通智数内置的综合分析助手",
        'sqlbot_name="星通智数"',
    ],
    "docker-compose.yaml": ['PROJECT_NAME: "星通智数"'],
    "installer/sqlbot/templates/sqlbot.conf": ['PROJECT_NAME="星通智数"'],
    "README.md": [
        "星通智数是一款基于大语言模型和 RAG 的智能报表系统。",
        "快速部署星通智数",
        "基于星通智数的源代码",
    ],
    "docs/README.en.md": [
        "星通智数 is an intelligent data query system based on large language models and RAG.",
        "quickly deploy 星通智数",
        "based on the 星通智数 source code",
    ],
    "installer/sctl": [
        "星通智数控制脚本",
        "查看星通智数服务运行状态",
        "星通智数服务状态",
    ],
    "installer/uninstall.sh": [
        "即将卸载星通智数服务",
        "停止星通智数服务",
        "星通智数服务卸载完成",
    ],
    "installer/install.conf": [
        "## 星通智数端口",
        "## 星通智数数据库库名",
        "## 星通智数 Secret Key",
    ],
    "frontend/src/utils/utils.ts": ["document.title = title || '星通智数'"],
    "frontend/public/vite-sqlbot.svg": ["<title>星通智数</title>"],
    "backend/common/core/app_cache.py": [
        "星通智数使用内存缓存",
        "星通智数使用Redis缓存",
        "星通智数未启用缓存",
    ],
    "backend/common/core/security_config.py": ["for the 星通智数 application"],
    "tools/seed_slg_bi_training.py": ["into the 星通智数系统库"],
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
            if "SQLBot" in value:
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
