import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.batches import create_batch
from app.db.base import Base
from app.models import ScanItem
from app.schemas.batch import BatchCreate


def test_batch_accepts_fifty_documents():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        filenames = [f'kk-{number:02d}.pdf' for number in range(1, 51)]
        result = create_batch(BatchCreate(filenames=filenames), session)

        assert result['total'] == 50
        assert [item['item_number'] for item in result['items']] == list(range(1, 51))
        assert session.scalar(select(func.count()).select_from(ScanItem)) == 50
    finally:
        session.close()


def test_batch_rejects_more_than_fifty_documents():
    with pytest.raises(ValidationError):
        BatchCreate(filenames=[f'kk-{number:02d}.pdf' for number in range(1, 52)])


def test_batch_requires_at_least_one_document():
    with pytest.raises(ValidationError):
        BatchCreate(filenames=[])
