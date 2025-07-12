from pydantic import BaseModel, constr, validator
from datetime import datetime
from typing import Optional

class CustomerCreate(BaseModel):
    name: str
    phone: constr(regex=r"^09\d{7,9}$")
    region: str
    notes: Optional[str] = None

class Payment(BaseModel):
    user_id: str
    amount: float
    method: str
    reference_id: str
    timestamp: datetime = datetime.utcnow()

class ChatLog(BaseModel):
    viber_id: str
    message: str
    timestamp: datetime = datetime.utcnow()
    type: str
    status: str = "received"
