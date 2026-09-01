"""Persistence for reusable ViewDecoders."""

from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from app.db.models import ViewDecoderRecord
from app.models.schemas import ViewDecoder


class DecoderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, decoder: ViewDecoder) -> ViewDecoder:
        record = self.db.get(ViewDecoderRecord, decoder.view_id)
        payload = decoder.model_dump()
        if record is None:
            record = ViewDecoderRecord(
                view_id=decoder.view_id,
                view_name=decoder.view_name,
                payload=payload,
            )
            self.db.add(record)
        else:
            record.view_name = decoder.view_name
            record.payload = payload
        self.db.commit()
        self.db.refresh(record)
        return ViewDecoder.model_validate(record.payload)

    def get(self, view_id: str) -> ViewDecoder:
        record = self.db.get(ViewDecoderRecord, view_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"View decoder '{view_id}' not found",
            )
        return ViewDecoder.model_validate(record.payload)
