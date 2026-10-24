from pydantic import BaseModel, ConfigDict

NANO_RUB = 1_000_000_000


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
