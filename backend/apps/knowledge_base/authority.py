import json
from xml.etree import ElementTree

from langchain_core.messages import HumanMessage, SystemMessage

from apps.knowledge_base.context import KNOWLEDGE_CONTEXT_SYSTEM_RULES, KnowledgeContextError


def knowledge_resolves_business_conflict(llm, knowledge_context: str, lower_priority_rule: str, output: str) -> bool:
    if not knowledge_context or not knowledge_context.strip():
        return False
    try:
        documents = ElementTree.fromstring(knowledge_context).findall(".//document")
        evidence = {
            document.attrib.get("id"): "\n".join(document.itertext())
            for document in documents
        }
        if not evidence:
            return False
        response = llm.invoke([
            SystemMessage(content=KNOWLEDGE_CONTEXT_SYSTEM_RULES + "\n你负责业务规则冲突裁决。status 只能是：not_applicable（知识库没有适用的冲突规则）；resolved（有明确的知识库规则覆盖低优先级规则，且当前输出符合知识库）；invalid_output（有覆盖规则但输出不符合）；conflict（适用的同层知识规则冲突）；uncertain（无法判断）。仅 not_applicable 允许继续使用低优先级规则，其余失败必须停止，不能当作无关知识。工作空间优先于平台。同层冲突应在 reason 中指出文档及冲突内容。权限、租户/产品强制过滤、物理可执行性、只读 SQL 和安全校验绝不能被覆盖。仅输出 JSON：{\"status\":\"resolved\",\"document_id\":\"文档ID\",\"quote\":\"支持裁决的完整原文规则\",\"reason\":\"裁决说明\"}。"),
            HumanMessage(content=json.dumps({
                "knowledge_context": knowledge_context,
                "lower_priority_rule": lower_priority_rule,
                "output": output,
            }, ensure_ascii=False)),
        ])
        verdict = json.loads(response.content)
        status = verdict.get("status")
        if status == "not_applicable":
            return False
        if status in {"conflict", "invalid_output", "uncertain"}:
            messages = {
                "conflict": "知识库同层业务规则存在冲突，请明确采用的文档口径。",
                "invalid_output": "生成结果未遵循知识库业务规则，请重新生成。",
                "uncertain": "无法确认知识库业务规则冲突，请明确口径。",
            }
            raise KnowledgeContextError(
                f"knowledge_{status}", messages[status] + str(verdict.get("reason") or ""),
                details={"verdict": verdict},
            )
        document_text = evidence.get(str(verdict.get("document_id")), "")
        quote = verdict.get("quote")
        if not (
            status == "resolved"
            and isinstance(quote, str)
            and bool(quote.strip())
            and quote in document_text
        ):
            raise ValueError("Missing verifiable knowledge evidence")
        return True
    except KnowledgeContextError:
        raise
    except Exception as error:
        raise KnowledgeContextError(
            "knowledge_conflict_review_failed",
            "知识库业务规则冲突校验失败，请重试；未采用冲突的 Data Skill 或元数据规则。",
        ) from error
