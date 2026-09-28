from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import admin_required, csrf_required
from app.core.config import get_settings
from app.db.session import get_db
from app.models import ScanBatch, ScanItem
from app.schemas.batch import BatchCreate

router = APIRouter(prefix='/api/batches', tags=['batches'])


def utcnow():
    return datetime.now(timezone.utc)


def serialize_batch(batch):
    counts = Counter(item.status for item in batch.items)
    return {
        'id': batch.id, 'batch_code': batch.batch_code, 'status': batch.status, 'created_at': batch.created_at,
        'total': len(batch.items), 'queued': counts['QUEUED'], 'processing': counts['PROCESSING'],
        'extracted': counts['EXTRACTED'], 'review_required': counts['REVIEW_REQUIRED'],
        'approved': counts['APPROVED'], 'failed': counts['FAILED'],
        'items': [
            {'id': item.id, 'item_number': item.item_number, 'original_filename': item.original_filename,
             'status': item.status, 'failure_code': item.failure_code, 'failure_message': item.failure_message}
            for item in sorted(batch.items, key=lambda item: item.item_number)
        ],
    }


def _batch(db, batch_id):
    return db.scalar(select(ScanBatch).where(ScanBatch.id == batch_id).options(selectinload(ScanBatch.items)))


@router.post('', dependencies=[Depends(csrf_required)])
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    max_batch_items = get_settings().max_batch_items
    if len(payload.filenames) > max_batch_items:
        raise HTTPException(422, f'Maksimal {max_batch_items} dokumen per batch.')
    today = datetime.now().strftime('%Y%m%d')
    existing = db.scalar(select(func.count()).select_from(ScanBatch).where(ScanBatch.batch_code.like(f'SCAN-{today}-%'))) or 0
    batch = ScanBatch(batch_code=f'SCAN-{today}-{existing + 1:04d}', status='QUEUED')
    db.add(batch)
    db.flush()
    for index, filename in enumerate(payload.filenames, 1):
        db.add(ScanItem(batch_id=batch.id, item_number=index, original_filename=filename, status='QUEUED'))
    db.commit()
    return serialize_batch(_batch(db, batch.id))


@router.get('', dependencies=[Depends(admin_required)])
def list_batches(db: Session = Depends(get_db)):
    rows = db.scalars(select(ScanBatch).options(selectinload(ScanBatch.items)).order_by(ScanBatch.created_at.desc()).limit(100)).all()
    return [serialize_batch(batch) for batch in rows]


@router.get('/{batch_id}', dependencies=[Depends(admin_required)])
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = _batch(db, batch_id)
    if not batch:
        raise HTTPException(404, 'Batch tidak ditemukan.')
    return serialize_batch(batch)


@router.post('/{batch_id}/approve-extracted', dependencies=[Depends(csrf_required)])
def approve_extracted(batch_id: str, db: Session = Depends(get_db)):
    batch = _batch(db, batch_id)
    if not batch:
        raise HTTPException(404, 'Batch tidak ditemukan.')
    eligible = [item for item in batch.items if item.status == 'EXTRACTED']
    if not eligible:
        raise HTTPException(422, 'Tidak ada data valid yang menunggu persetujuan.')
    now = utcnow()
    for item in eligible:
        item.status = 'APPROVED'
        item.approved_at = now
    db.commit()
    db.expire_all()
    return {'approved_count': len(eligible), 'batch': serialize_batch(_batch(db, batch_id))}
