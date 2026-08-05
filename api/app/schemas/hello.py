from datetime import datetime

from pydantic import BaseModel


class HelloResponse(BaseModel):
    message: str
    db_time: datetime
    environment: str
