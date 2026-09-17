"""Per-request review audit; cached model instances are never mutated."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import Session, select

from apps.chat.models.chat_model import ChatLog, ChatRecord, OperationEnum, TypeEnum
from common.core.db import engine


class ReviewedModel:
    def __init__(self, model, *, observer=None, json_mode=False, extra_body=None):
        self.model = model
        self.knowledge_review_observer = observer
        self.knowledge_review_json_mode = json_mode
        self.knowledge_review_extra_body = extra_body

    def __getattr__(self, name):
        return getattr(self.model, name)


class KnowledgeReviewAudit:
    def __init__(self, *, tenant_id: int, datasource_id: int | None, model_id: int | None,
                 model_name: str, surface: str, record_id: int | None = None, session_factory=None):
        if not tenant_id:
            raise ValueError('Review audit requires tenant context')
        self.tenant_id = int(tenant_id)
        self.record_id = record_id
        self.model_id = model_id
        self.model_name = model_name
        self.context = {'request_id': uuid.uuid4().hex, 'surface': surface,
                        'tenant_id': str(tenant_id), 'datasource_id': datasource_id, 'record_id': record_id}
        self.session_factory = session_factory or (lambda: Session(engine))
        self.pending = {}

    def __call__(self, event: dict):
        metadata = {**self.context, **event}
        with self.session_factory() as session:
            if event['event'] == 'start':
                if self.record_id is not None:
                    record = session.exec(select(ChatRecord.tenant_id, ChatRecord.datasource).where(ChatRecord.id == self.record_id)).first()
                    if (record is None or int(record.tenant_id) != self.tenant_id
                            or str(record.datasource) != str(self.context['datasource_id'])):
                        raise ValueError('Review audit record is outside tenant context')
                log = ChatLog(tenant_id=self.tenant_id, type=TypeEnum.CHAT,
                              operate=OperationEnum.KNOWLEDGE_REVIEW, pid=self.record_id,
                              ai_modal_id=self.model_id, base_modal=self.model_name,
                              messages=[metadata], start_time=datetime.now(),
                              local_operation=False, error=False)
                session.add(log)
                session.commit()
                session.refresh(log)
                self.pending[event['call_id']] = log.id
                return
            log_id = self.pending.pop(event['call_id'])
            log = session.exec(select(ChatLog).where(ChatLog.id == log_id, ChatLog.tenant_id == self.tenant_id)).one()
            log.messages = [*log.messages, metadata]
            log.finish_time = datetime.now()
            log.token_usage = event.get('usage', {})
            log.error = event['status'] in {'unavailable', 'invalid_response'}
            session.add(log)
            session.commit()
            # Count each logical invocation once, including malformed model responses.
            from apps.chat.curd.chat import _record_chat_usage_from_log
            _record_chat_usage_from_log(log, success=not log.error)
