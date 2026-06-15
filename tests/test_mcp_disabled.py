import os


os.environ["MCP_ENABLED"] = "false"
os.environ["EMBEDDING_ENABLED"] = "false"
os.environ["TABLE_EMBEDDING_ENABLED"] = "false"


def test_mcp_tools_are_disabled_by_default():
    import main

    assert main.mcp is None
    mcp_app_routes = {getattr(route, "path", "") for route in main.mcp_app.routes}
    assert "/images" in mcp_app_routes
    assert "/mcp" not in mcp_app_routes

    app_routes = {getattr(route, "path", "") for route in main.app.routes}
    assert not any(path.startswith("/api/v1/mcp") for path in app_routes)
