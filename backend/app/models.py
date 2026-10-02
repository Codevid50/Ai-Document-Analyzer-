from pydantic import BaseModel


class SummaryResponse(BaseModel):
    document_id: int
    filename: str
    summary: str
    key_points: list[str]
    key_takeaways: list[str]


class AskResponse(BaseModel):
    filename: str
    question: str
    answer: str