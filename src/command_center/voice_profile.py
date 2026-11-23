"""Shared strict offline-voice profile; no credential reads or model loading."""
from pydantic import BaseModel, ConfigDict, Field


class VoiceProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    enabled: bool = False
    connection_file: str
    connection_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    model_directory: str
    model_manifest: dict[str, str]
    since: str
