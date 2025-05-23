
from pydantic import BaseModel


class ChatQuestion(BaseModel):
    question: str
    chat_id: int