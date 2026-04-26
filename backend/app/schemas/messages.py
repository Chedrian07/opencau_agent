from pydantic import BaseModel, Field


class UserMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class UserMessageResponse(BaseModel):
    session_id: str
    accepted: bool
