import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.notepad import NotepadEntryType


class NotepadEntryCreate(BaseModel):
    type: NotepadEntryType
    # Both allowed blank — the FAB creates a new entry immediately (before the user has typed
    # anything), same "starts empty, filled in by the editor's own debounced autosave" shape a
    # blank Keep/Notes entry uses.
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=100_000)


class NotepadEntryUpdate(BaseModel):
    title: str = Field(max_length=200)
    body: str = Field(max_length=100_000)
    # The updated_at this client last read — see NotepadEntry's own doc comment on why this is
    # the optimistic-concurrency token. Required, not optional: every save comes from an editor
    # that necessarily loaded the entry first, so there's always a real value to send.
    expected_updated_at: datetime.datetime


class NotepadEntryOut(BaseModel):
    id: uuid.UUID
    type: NotepadEntryType
    owner_id: uuid.UUID | None
    title: str
    body: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    updated_by: uuid.UUID | None
