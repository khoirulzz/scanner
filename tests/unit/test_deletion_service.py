from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Export, ExportItem, FieldCorrection, KKMember, KKRecord, ScanAttempt, ScanBatch, ScanIssue, ScanItem
from app.services.deletion_service import delete_scan_batch, delete_scan_item


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model)) or 0


def _fixture(session):
    batch = ScanBatch(batch_code='TEST-DELETE', status='QUEUED')
    exported_at = datetime.now(timezone.utc)
    first = ScanItem(batch=batch, item_number=1, original_filename='first.pdf', status='APPROVED', exported_at=exported_at)
    second = ScanItem(batch=batch, item_number=2, original_filename='second.pdf', status='APPROVED', exported_at=exported_at)
    record = KKRecord(scan_item=first, no_kk='0012345678901234', alamat='DK BOJONGIRENG')
    member = KKMember(kk_record=record, no_urut_kk=1, nik='0012345678901235')
    session.add(batch)
    session.flush()
    session.add_all([
        ScanAttempt(scan_item=first, attempt_number=1, provider='test', model='test'),
        ScanIssue(scan_item=first, member_id=member.id, severity='WARNING', code='TEST', message='Fiktif'),
        FieldCorrection(scan_item_id=first.id, member_id=member.id, field_name='alamat'),
    ])
    export = Export(export_code='EXP-DELETE', filename='delete.xlsx', kk_count=2, row_count=1)
    session.add(export)
    session.flush()
    session.add_all([
        ExportItem(export_id=export.id, scan_item_id=first.id),
        ExportItem(export_id=export.id, scan_item_id=second.id),
    ])
    session.commit()
    return batch.id, first.id, second.id


def test_delete_scan_item_removes_children_and_invalidates_export_history():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        batch_id, first_id, second_id = _fixture(session)
        result = delete_scan_item(session, first_id)

        assert result['batch_deleted'] is False
        assert session.get(ScanItem, first_id) is None
        assert session.get(ScanItem, second_id) is not None
        assert session.get(ScanItem, second_id).exported_at is None
        assert session.get(ScanBatch, batch_id) is not None
        assert _count(session, KKRecord) == 0
        assert _count(session, KKMember) == 0
        assert _count(session, ScanAttempt) == 0
        assert _count(session, ScanIssue) == 0
        assert _count(session, FieldCorrection) == 0
        assert _count(session, Export) == 0
        assert _count(session, ExportItem) == 0
    finally:
        session.close()


def test_delete_batch_removes_every_scan_and_related_data():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        batch_id, _, _ = _fixture(session)
        result = delete_scan_batch(session, batch_id)

        assert result['scan_items'] == 2
        assert session.get(ScanBatch, batch_id) is None
        for model in (ScanItem, KKRecord, KKMember, ScanAttempt, ScanIssue, FieldCorrection, Export, ExportItem):
            assert _count(session, model) == 0
    finally:
        session.close()
