"""
脚本说明：这个脚本定义第三方 MCP 外部数据源配置的接口数据结构。
"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExternalMcpServerDTO(BaseModel):
    """
    类说明：ExternalMcpServerDTO 表示可返回给前端的第三方 MCP 数据源信息。
    """
    id: int
    name: str
    endpoint: str
    description: Optional[str] = None
    auth_type: str = "bearer"
    auth_header_name: str = "Authorization"
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    status: int = 1
    credential_configured: bool = False
    create_time: int = 0
    update_time: int = 0


class ExternalMcpServerCreator(BaseModel):
    """
    类说明：ExternalMcpServerCreator 表示创建第三方 MCP 数据源配置的请求。
    """
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1)
    description: Optional[str] = None
    auth_type: str = "bearer"
    auth_header_name: str = "Authorization"
    auth_token: Optional[str] = None
    server_name: Optional[str] = Field(default=None, max_length=128)
    server_version: Optional[str] = Field(default=None, max_length=64)
    status: int = 1


class ExternalMcpServerEditor(ExternalMcpServerCreator):
    """
    类说明：ExternalMcpServerEditor 表示更新第三方 MCP 数据源配置的请求。
    """
    id: int


class ExternalMcpToolDTO(BaseModel):
    """
    类说明：ExternalMcpToolDTO 表示第三方 MCP 暴露的一个工具。
    """
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ExternalMcpToolPreviewRequest(BaseModel):
    """
    类说明：ExternalMcpToolPreviewRequest 表示看板图表调用第三方 MCP 工具做预览。
    """
    external_mcp_server_id: int | str
    tenant_id: Optional[int | str] = None
    dashboard_id: Optional[str] = None
    tool: str = Field(min_length=1, max_length=256)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_path: Optional[str] = None
    key_field: Optional[str] = None
    value_field: Optional[str] = None


class ExternalMcpToolPreviewResponse(BaseModel):
    """
    类说明：ExternalMcpToolPreviewResponse 表示第三方 MCP 工具预览结果。
    """
    status: str = "success"
    fields: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    raw: Any = None
    message: str = ""
    mcp: dict[str, Any] = Field(default_factory=dict)
