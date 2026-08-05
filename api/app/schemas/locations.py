from datetime import date

from pydantic import BaseModel


class LocationOut(BaseModel):
    id: str
    org_id: str
    org_name: str
    name: str
    activated_on: date
