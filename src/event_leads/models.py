from pydantic import BaseModel


class Lead(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    phone: str | None = None
