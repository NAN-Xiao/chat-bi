import ast

with open('backend/apps/chat/task/smart_qa_graph.py', 'r', encoding='utf-8') as f:
    source = f.read()

DOCSTRINGS = {
    '_sql_statements': (
        "是什么：把原始 SQL 文本解析为 sqlglot 语法树语句列表。\n"
        "谁调用：所有需要分析或改写 SQL 的事件存在性相关函数调用。\n"
        "做了什么：根据数据源类型选择对应方言，调用 sqlglot.parse 解析并过滤掉空语句。"
    ),
    '_table_aliases_for_select': (
        "是什么：收集 SELECT 语句中 FROM 和 JOIN 子句的表别名映射。\n"
        "谁调用：_extract_requested_event_predicates、_aliases_for_final_sources 等 SQL 分析函数调用。\n"
        "做了什么：遍历 SELECT 的 from 和 joins，把表名及其别名映射回 exp.Table 节点，用于后续定位事件字段所属表。"
    ),
    '_literal_strings': (
        "是什么：从 sqlglot 表达式中提取所有字符串字面量。\n"
        "谁调用：_event_values_from_condition 在解析 WHERE 条件中的事件值时调用。\n"
        "做了什么：如果节点本身是字符串字面量则直接返回，否则递归查找子节点中的字符串字面量并去重返回。"
    ),
    '_event_values_from_condition': (
        "是什么：从 WHERE/HAVING 等条件表达式中提取与事件字段相关的字面量值。\n"
        "谁调用：_extract_requested_event_predicates 解析 SQL 谓词时调用。\n"
        "做了什么：遍历条件中的 EQ 和 In 表达式，当一侧是配置的事件名字段时，收集另一侧的字符串字面量，返回 (字段列, 事件值集合) 列表。"
    ),
    '_selected_output_columns': (
        "是什么：获取 SELECT 语句输出列的别名集合。\n"
        "谁调用：_extract_requested_event_predicates 记录每个 SELECT 的输出列信息时调用。\n"
        "做了什么：遍历 SELECT 的表达式列表，使用 alias_or_name 归一化后收集非通配符列名。"
    ),
    '_extract_requested_event_predicates': (
        "是什么：从 SQL 中解析出所有涉及事件名字段的查询谓词。\n"
        "谁调用：_event_availability_for_sql 在检查事件存在性前调用。\n"
        "做了什么：解析 SQL 语句，对每个 SELECT 的 WHERE 条件分析事件字段，记录涉及的表、schema、别名、事件字段、事件值、所在 CTE 别名及输出列。"
    ),
    '_nearest_cte_alias': (
        "是什么：查找 SELECT 表达式所在最近的 CTE 名称。\n"
        "谁调用：_extract_requested_event_predicates 在定位事件谓词属于哪个 CTE 时调用。\n"
        "做了什么：沿 sqlglot 父节点向上遍历，遇到 exp.CTE 时返回其别名，无则返回 None。"
    ),
    '_quote_table_for_sql': (
        "是什么：把表名和可选 schema 名转换为带引号的 SQL 表标识符字符串。\n"
        "谁调用：_event_values_exist_in_datasource 构造存在性探测 SQL 时调用。\n"
        "做了什么：使用 sqlglot 创建带引号的 Table 表达式并按数据源方言输出 SQL 文本。"
    ),
    '_event_cache_datasource_key': (
        "是什么：为事件存在性缓存生成数据源级别的唯一键。\n"
        "谁调用：_event_cache_key 构造缓存键时调用。\n"
        "做了什么：优先返回数据源 id，否则返回由数据源类型、名称和对象 id 组成的元组。"
    ),
    '_event_cache_key': (
        "是什么：生成单个事件值存在性缓存的精确键。\n"
        "谁调用：_cached_event_existence 和 _store_event_existence_cache 读写缓存时调用。\n"
        "做了什么：组合数据源键、schema、表名、事件字段和事件值，并对标识符做归一化。"
    ),
    '_cached_event_existence': (
        "是什么：从进程内缓存读取一批事件值的存在性结果。\n"
        "谁调用：_event_values_exist_in_datasource 在查库前尝试命中缓存时调用。\n"
        "做了什么：读取 SMART_QA_EVENT_EXISTENCE_CACHE_TTL_SECONDS 配置，在锁保护下过滤过期键，返回已缓存结果和待查值集合。"
    ),
    '_store_event_existence_cache': (
        "是什么：把事件值存在性结果写入进程内缓存。\n"
        "谁调用：_event_values_exist_in_datasource 查询数据库后将新结果缓存时调用。\n"
        "做了什么：在锁保护下按 TTL 设置缓存项，键由 _event_cache_key 生成。"
    ),
    '_chunks': (
        "是什么：把列表按指定大小切分为多个批次。\n"
        "谁调用：_event_values_exist_in_datasource 分批查询事件值存在性时调用。\n"
        "做了什么：使用生成器每次产出至多 size 个元素的子列表。"
    ),
    '_event_values_exist_in_datasource': (
        "是什么：探测一组事件值在物理数据源表中是否存在。\n"
        "谁调用：_event_availability_for_sql 按组检查事件存在性时调用。\n"
        "做了什么：先读缓存，再分批对未命中缓存的值执行 SELECT DISTINCT 查询，把结果写回缓存，返回每个值的存在状态（True/False/None）。"
    ),
    '_event_exists_in_datasource': (
        "是什么：探测单个事件值在物理数据源表中是否存在。\n"
        "谁调用：需要单点检查事件存在性的地方（目前主要为 _event_values_exist_in_datasource 的便捷封装）。\n"
        "做了什么：调用 _event_values_exist_in_datasource 并返回该单个值的存在状态。"
    ),
    '_event_availability_for_sql': (
        "是什么：对 SQL 中请求的所有事件值进行存在性校验并分类。\n"
        "谁调用：_rewrite_sql_for_missing_events、_cleanup_missing_event_result 等事件缺失处理逻辑调用。\n"
        "做了什么：提取事件谓词，按 (schema, table, event_field) 分组查库，根据 strict/unknown 策略把每个值标记为缺失、存在或未知。"
    ),
    '_missing_requested_events_from_availability': (
        "是什么：从事件可用性结果中筛选出缺失的事件谓词。\n"
        "谁调用：_cleanup_missing_event_result 判断需要清理哪些事件时调用。\n"
        "做了什么：遍历 _EventAvailability 列表，把 missing_values 非空的谓词重新构造为 _RequestedEventPredicate 返回。"
    ),
    '_missing_requested_events': (
        "是什么：获取 SQL 中所有请求但数据源缺失的事件值。\n"
        "谁调用：_cleanup_missing_event_result 在 availability 参数为 None 时调用。\n"
        "做了什么：调用 _event_availability_for_sql 后再用 _missing_requested_events_from_availability 提取缺失事件。"
    ),
    '_unknown_events_from_availability': (
        "是什么：收集事件存在性校验中无法确认的事件值。\n"
        "谁调用：_rewrite_sql_for_missing_events 生成 unknown_events 列表时调用。\n"
        "做了什么：从 _EventAvailability 列表中提取所有 unknown_values 并排序去重。"
    ),
    '_final_select': (
        "是什么：从一条 SQL 语句中找出最终 SELECT 表达式。\n"
        "谁调用：_result_fields_for_missing_events 在定位最终输出 SELECT 时调用。\n"
        "做了什么：若语句本身是 SELECT 则直接返回，否则通过 find(exp.Select) 查找内部的 SELECT。"
    ),
    '_aliases_for_final_sources': (
        "是什么：获取最终 SELECT 中所有表来源的别名到表名映射。\n"
        "谁调用：_result_fields_for_missing_events 和 _remove_missing_event_cte_branches 在识别列来源时调用。\n"
        "做了什么：调用 _table_aliases_for_select，把别名和表名都映射到归一化的表名。"
    ),
    '_result_fields_for_missing_events': (
        "是什么：根据缺失事件谓词找出需要被移除的结果字段。\n"
        "谁调用：_rewrite_sql_for_missing_events 和 _cleanup_missing_event_result 在清理结果时调用。\n"
        "做了什么：解析 SQL，找出最终 SELECT 输出列中依赖缺失 CTE/表的字段，返回这些输出字段名集合。"
    ),
    '_prune_result_fields': (
        "是什么：从 SQL 执行结果中删除指定的字段列。\n"
        "谁调用：_cleanup_missing_event_result 和 _execute_sql 在业务提示要求移除字段时调用。\n"
        "做了什么：重建 fields 和 data，过滤掉指定的列名，保持其他数据结构不变。"
    ),
    '_missing_event_feedback': (
        "是什么：生成缺失埋点事件的用户提示文案。\n"
        "谁调用：_prepare_sql 和 _execute_sql 在检测到缺失事件时调用。\n"
        "做了什么：拼接缺失事件名称，如果有被移除的字段则补充说明已生成其余结果。"
    ),
    '_missing_event_notice': (
        "是什么：构造缺失埋点事件的业务提示数据结构。\n"
        "谁调用：_prepare_sql 和 _execute_sql 在需要返回 notice 时调用。\n"
        "做了什么：返回包含 notice_type、severity、reason、items 和 removed_fields 的字典。"
    ),
    '_unknown_event_feedback': (
        "是什么：生成无法确认事件存在性的用户提示文案。\n"
        "谁调用：_prepare_sql 在检测到未知事件时调用。\n"
        "做了什么：拼接未知事件名称，提示相关数值可能受数据源状态影响。"
    ),
    '_unknown_event_notice': (
        "是什么：构造事件存在性未知的业务提示数据结构。\n"
        "谁调用：_prepare_sql 在需要返回未知事件 notice 时调用。\n"
        "做了什么：返回包含 notice_type、reason、unconfirmed_events 和 agent_guidance 的字典。"
    ),
    '_business_notice_rank': (
        "是什么：评估业务提示的严重程度权重。\n"
        "谁调用：_merge_business_notice 在比较多个提示时调用。\n"
        "做了什么：根据 reason 返回缺失事件、存在性未知、数据不可用的优先级分数，未知 reason 返回 0。"
    ),
    '_merge_business_notice': (
        "是什么：合并两个业务提示，保留更严重的一个。\n"
        "谁调用：_prepare_sql 在组合缺失事件和未知事件提示时调用。\n"
        "做了什么：无候选返回当前，无当前返回候选，否则按 _business_notice_rank 比较并返回分数更高的提示。"
    ),
    '_missing_event_predicates_from_availability': (
        "是什么：从事件可用性结果中构造缺失事件的谓词列表。\n"
        "谁调用：_rewrite_sql_for_missing_events 在需要改写 SQL 前提取缺失谓词时调用。\n"
        "做了什么：遍历 availability，把 missing_values 非空的谓词复制为新的 _RequestedEventPredicate。"
    ),
    '_removable_missing_event_ctes': (
        "是什么：判断哪些 CTE 分支因事件全部缺失而可以被整体移除。\n"
        "谁调用：_rewrite_sql_for_missing_events 在决定移除哪些 CTE 时调用。\n"
        "做了什么：按 CTE 别名分组，若某 CTE 下所有谓词都缺失事件且没有任何存在/未知事件，则该 CTE 可移除。"
    ),
    '_expression_references_sources': (
        "是什么：判断 sqlglot 表达式是否引用了指定的表别名或表名。\n"
        "谁调用：_remove_order_references 和 _remove_missing_event_cte_branches 在决定移除哪些子句时调用。\n"
        "做了什么：遍历表达式中的列，检查列的 table 是否在 source_aliases 中，或经 final_aliases 映射后落在 source_names 中。"
    ),
    '_remove_order_references': (
        "是什么：从 SELECT 中移除引用缺失 CTE/表的 ORDER BY 项。\n"
        "谁调用：_remove_missing_event_cte_branches 在改写 SQL 时调用。\n"
        "做了什么：过滤 order 表达式中引用被移除来源的项，若全部项都被移除则把整个 order 置空。"
    ),
    '_remove_missing_event_cte_branches': (
        "是什么：在语法树层面移除因事件缺失而无法提供数据的 CTE/Join 分支及关联字段。\n"
        "谁调用：_rewrite_sql_for_missing_events 对每条 SQL 语句进行改写时调用。\n"
        "做了什么：删除缺失 CTE，移除关联的 LEFT JOIN、输出列、WHERE/HAVING/GROUP/QUALIFY 引用，并清理 ORDER BY；若主表或关键子句受影响则放弃改写。"
    ),
    '_rewrite_sql_for_missing_events': (
        "是什么：当 SQL 请求的事件部分缺失时尝试改写 SQL 以保留可展示结果。\n"
        "谁调用：_prepare_sql 在校验用户 SQL 后调用。\n"
        "做了什么：检查事件可用性，计算缺失/未知事件，若可安全移除整组 CTE 分支则生成改写后的 SQL；否则返回不可执行及原因。"
    ),
    '_cleanup_missing_event_result': (
        "是什么：在 SQL 执行完成后根据缺失事件清理结果集。\n"
        "谁调用：_execute_sql 在执行 SQL 后调用。\n"
        "做了什么：识别缺失事件，从结果字段中移除依赖缺失事件的列，记录清理日志，返回清理后的结果和元信息。"
    ),
    '_observe_node': (
        "是什么：为 Smart Q&A 图的某个节点包装观测与错误处理。\n"
        "谁调用：_build_graph 注册每个 LangGraph 节点时调用。\n"
        "做了什么：调用 assistant_workflow.observe_node，传入工作流配置、节点名和实际处理器，使节点执行具备统一的日志、追踪与异常格式化能力。"
    ),
    '_prepare_existing_context': (
        "是什么：加载 Smart Q&A 所需的上下文与自定义提示。\n"
        "谁调用：LangGraph 工作流的 prepare_context 节点调用。\n"
        "做了什么：在数据库会话中加载当前数据源的 Data Skill、生成 SQL 类型的自定义提示、保存 Agent 上下文快照、加载打点配置并初始化消息。"
    ),
    '_emit_record_metadata': (
        "是什么：向客户端发送当前对话记录的基础元数据事件。\n"
        "谁调用：LangGraph 工作流的 emit_record_metadata 节点调用。\n"
        "做了什么：调用 assistant_workflow.emit_record_metadata，在聊天场景下发送包含问题和重新生成 id 的元数据事件。"
    ),
    '_ensure_datasource': (
        "是什么：确保 Smart Q&A 流程有合法且可连接的数据源。\n"
        "谁调用：LangGraph 工作流的 ensure_datasource 节点调用。\n"
        "做了什么：若当前无数据源则让服务自动选择并通过 SSE 通知前端；否则校验历史数据源；最后检查数据库连接，失败则抛出异常。"
    ),
    '_generate_sql': (
        "是什么：调用 LLM 生成回答用户问题的 SQL。\n"
        "谁调用：LangGraph 工作流的 generate_sql 节点调用。\n"
        "做了什么：在数据库会话中流式调用 service.generate_sql_text_streaming_reasoning，消费并透传推理内容，返回完整的 SQL 生成文本。"
    ),
    '_execute_saas_skill': (
        "是什么：尝试命中并执行 Data Skill 中声明的可执行 SaaS Skill。\n"
        "谁调用：LangGraph 工作流的 execute_saas_skill 节点调用。\n"
        "做了什么：匹配用户问题对应的 SaaS Skill，执行 SQL/MCP 多源逻辑并合并结果；命中后根据 finish_step 决定直接结束或继续生成分析回答。"
    ),
    '_prepare_sql': (
        "是什么：校验、保存并准备最终用于执行的 SQL。\n"
        "谁调用：LangGraph 工作流的 prepare_sql 节点调用。\n"
        "做了什么：校验 SQL，处理 Data Skill 校验错误，提取图表类型，按需重命名聊天标题，处理动态数据源 SQL，校验用户表权限，检测缺失/未知事件并尝试改写，最后返回执行所需的 SQL 与元信息。"
    ),
    '_execute_sql': (
        "是什么：在数据源上执行 SQL 并处理结果与业务提示。\n"
        "谁调用：LangGraph 工作流的 execute_sql 节点调用。\n"
        "做了什么：记录执行日志，调用 service.execute_sql，处理数据不可用和权限异常，对结果做大数字与列名归一化，清理缺失事件列，保存数据，按需结束流程或继续生成图表。"
    ),
    '_generate_chart': (
        "是什么：根据 SQL 执行结果生成图表配置。\n"
        "谁调用：LangGraph 工作流的 generate_chart 节点调用。\n"
        "做了什么：获取相关表 schema，流式调用 LLM 生成图表配置并校验保存，按 in_chat/stream/普通模式把图表或数据发送给前端。"
    ),
    '_should_continue_after_sql': (
        "是什么：决定 SQL 准备完成后是否继续执行 SQL。\n"
        "谁调用：LangGraph 条件边，在 prepare_sql 节点后调用。\n"
        "做了什么：若状态中存在 stop 标志则返回 END，否则进入 execute_sql 节点。"
    ),
    '_should_continue_after_saas_skill': (
        "是什么：决定 SaaS Skill 执行完成后是否继续常规 SQL 流程。\n"
        "谁调用：LangGraph 条件边，在 execute_saas_skill 节点后调用。\n"
        "做了什么：若状态中存在 stop 标志（表示已处理完成）则返回 END，否则进入 generate_sql 节点。"
    ),
    '_should_continue_after_execute': (
        "是什么：决定 SQL 执行完成后是否继续生成图表。\n"
        "谁调用：LangGraph 条件边，在 execute_sql 节点后调用。\n"
        "做了什么：若状态中存在 stop 标志则返回 END，否则进入 generate_chart 节点。"
    ),
    '_build_graph': (
        "是什么：构建并编译 Smart Q&A 的 LangGraph 状态机。\n"
        "谁调用：模块导入时调用，结果缓存到 SMART_QA_GRAPH。\n"
        "做了什么：添加 prepare_context、emit_record_metadata、ensure_datasource、execute_saas_skill、generate_sql、prepare_sql、execute_sql、generate_chart 节点及条件边，并编译图。"
    ),
    'run_smart_qa_graph': (
        "是什么：Smart Q&A 工作流的入口函数。\n"
        "谁调用：外部 Smart Q&A 服务启动一次问答流程时调用。\n"
        "做了什么：构造初始状态，调用 run_assistant_workflow 执行编译好的图，并透传执行过程中的事件/结果生成器。"
    ),
}

tree = ast.parse(source)
lines = source.split('\n')


def to_offset(lineno, col):
    offset = 0
    for i in range(lineno - 1):
        offset += len(lines[i]) + 1
    return offset + col


replacements = []
for node in ast.walk(tree):
    if not isinstance(node, ast.FunctionDef):
        continue
    name = node.name
    if name not in DOCSTRINGS:
        continue
    first_stmt = node.body[0]
    start_lineno = first_stmt.lineno
    start_col = first_stmt.col_offset
    end_lineno = first_stmt.end_lineno
    end_col = first_stmt.end_col_offset

    is_docstring = (
        isinstance(first_stmt, ast.Expr)
        and isinstance(first_stmt.value, ast.Constant)
        and isinstance(first_stmt.value.value, str)
    )

    indent = ' ' * start_col
    doc_content = DOCSTRINGS[name]
    doc_text = (
        f'{indent}"""\n'
        + '\n'.join(f'{indent}{line}' for line in doc_content.split('\n'))
        + f'\n{indent}"""'
    )

    start = to_offset(start_lineno, start_col)
    end = to_offset(end_lineno, end_col)
    replacements.append((start, end, doc_text, is_docstring))

# Apply replacements from end to start so offsets remain valid.
replacements.sort(key=lambda x: x[0], reverse=True)

for start, end, doc_text, is_docstring in replacements:
    if is_docstring:
        source = source[:start] + doc_text + source[end:]
    else:
        source = source[:start] + doc_text + '\n' + source[end:]

with open('backend/apps/chat/task/smart_qa_graph.py', 'w', encoding='utf-8') as f:
    f.write(source)

print(f"Updated {len(replacements)} function docstrings.")
