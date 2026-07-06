from pydantic import BaseModel


class FeishuChallenge(BaseModel):
    challenge: str
    token: str
    type: str


class FeishuMessageSender(BaseModel):
    sender_id: dict = {}
    sender_type: str = ""


class FeishuMessageBody(BaseModel):
    message_id: str = ""
    chat_id: str = ""
    chat_type: str = ""
    message_type: str = ""
    content: str = ""


class FeishuMessageEvent(BaseModel):
    sender: FeishuMessageSender = FeishuMessageSender()
    message: FeishuMessageBody = FeishuMessageBody()


class ChoreInput(BaseModel):
    message_id: str
    chat_id: str
    sender_open_id: str
    chore_text: str


class ParsedIncomingMessage(BaseModel):
    message_id: str
    chat_id: str
    sender_open_id: str
    raw_text: str
    receive_id_type: str = "chat_id"
    receive_id: str = ""


class ParsedChoreTask(BaseModel):
    task_type: str
    confidence: float = 1.0
    evidence: str = ""


class LLMParseResult(BaseModel):
    tasks: list[ParsedChoreTask] = []
    ignored: list[str] = []
    need_confirm: bool = False
    raw_response: str | None = None


class ReminderParsedResult(BaseModel):
    is_reminder: bool = False
    target_person: str = ""
    event_text: str = ""
    event_date: str = ""
    remind_time: str = ""
    remind_text: str = ""
    raw_response: str | None = None
