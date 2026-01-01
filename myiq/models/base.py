
from pydantic import BaseModel, Field
from typing import Any, Union

class WsMessageBody(BaseModel):
    name: str
    version: str = "1.0"
    body: dict[str, Any] = Field(default_factory=dict)

class WsRequest(BaseModel):
    name: str
    request_id: str
    msg: Union[WsMessageBody, dict[str, Any]]

class Balance(BaseModel):
    id: int
    type: int
    amount: float
    currency: str

class Candle(BaseModel):
    id: int
    from_time: int = Field(alias="from")
    to_time: int = Field(alias="to")
    open: float
    close: float
    min: float
    max: float
    volume: float
    # Real-time fields
    active_id: Union[int, None] = None
    size: Union[int, None] = None
    at: Union[int, None] = None
    ask: Union[float, None] = None
    bid: Union[float, None] = None
    phase: Union[str, None] = None
