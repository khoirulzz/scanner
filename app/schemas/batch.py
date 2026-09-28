from pydantic import BaseModel, Field


class BatchCreate(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=50)
class ScanItemCreate(BaseModel):
    original_filename: str
    original_size: int | None = None
