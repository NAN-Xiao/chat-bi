from enum import Enum
from typing import Optional

from sqlalchemy import text as sql_text
from sqlmodel import Session


class CustomPromptTypeEnum(str, Enum):
    GENERATE_SQL = "GENERATE_SQL"
    ANALYSIS = "ANALYSIS"
    PREDICT_DATA = "PREDICT_DATA"


def find_custom_prompts(
        session: Session,
        custom_prompt_type: CustomPromptTypeEnum,
        datasource: Optional[int] = None,
) -> tuple[str, list[str]]:
    rows = session.execute(
        sql_text(
            """
            SELECT prompt, specific_ds, datasource_ids
            FROM custom_prompt
            WHERE type = :custom_prompt_type
            ORDER BY create_time, id
            """
        ),
        {"custom_prompt_type": custom_prompt_type.value},
    ).mappings().all()

    prompt_list: list[str] = []
    for row in rows:
        prompt = row.get("prompt")
        if not prompt:
            continue
        if not row.get("specific_ds"):
            prompt_list.append(prompt)
            continue
        if datasource is None:
            continue
        datasource_ids = row.get("datasource_ids") or []
        if any(str(item) == str(datasource) for item in datasource_ids):
            prompt_list.append(prompt)

    if not prompt_list:
        return "", []

    content = "<Other-Infos>\n"
    content += "".join(f"\t<content>{prompt}</content>\n" for prompt in prompt_list)
    content += "</Other-Infos>\n"
    return content, prompt_list
