"""Targeted deletion helpers for batches and individual scan results.

Deletion is explicit instead of relying on database-level cascades so behavior is
consistent between local SQLite and the PostgreSQL deployment used by the web
variant. Export history that references deleted scans is invalidated as well,
because its stored row/KK counts would otherwise become stale.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import (
    Export,
    ExportItem,
    FieldCorrection,
    KKMember,
    KKRecord,
    ScanAttempt,
    ScanBatch,
    ScanIssue,
    ScanItem,
)


def _unique(values):
    return list(dict.fromkeys(values))


def _delete_scan_items(db: Session, item_ids: list[str]) -> dict[str, int]:
    item_ids = _unique(item_ids)
    if not item_ids:
        return {'scan_items': 0, 'kk_records': 0, 'kk_members': 0, 'exports_invalidated': 0}

    record_ids = _unique(
        db.scalars(select(KKRecord.id).where(KKRecord.scan_item_id.in_(item_ids))).all()
    )
    member_count = 0
    if record_ids:
        member_count = db.scalar(
            select(func.count()).select_from(KKMember).where(KKMember.kk_record_id.in_(record_ids))
        ) or 0

    export_ids = _unique(
        db.scalars(select(ExportItem.export_id).where(ExportItem.scan_item_id.in_(item_ids))).all()
    )

    # An export is a historical snapshot. If one referenced scan is deleted,
    # discard that export record instead of leaving stale counts/downloads.
    if export_ids:
        exported_item_ids = _unique(
            db.scalars(
                select(ExportItem.scan_item_id).where(ExportItem.export_id.in_(export_ids))
            ).all()
        )
        db.execute(delete(ExportItem).where(ExportItem.export_id.in_(export_ids)))
        db.execute(delete(Export).where(Export.id.in_(export_ids)))
        # A surviving scan may have appeared in an invalidated export. Make it
        # eligible again only when no other export history still references it.
        db.execute(
            update(ScanItem)
            .where(ScanItem.id.in_(exported_item_ids))
            .where(ScanItem.id.not_in(item_ids))
            .where(~ScanItem.id.in_(select(ExportItem.scan_item_id)))
            .values(exported_at=None)
        )

    db.execute(delete(FieldCorrection).where(FieldCorrection.scan_item_id.in_(item_ids)))
    db.execute(delete(ScanIssue).where(ScanIssue.scan_item_id.in_(item_ids)))
    db.execute(delete(ScanAttempt).where(ScanAttempt.scan_item_id.in_(item_ids)))

    if record_ids:
        db.execute(delete(KKMember).where(KKMember.kk_record_id.in_(record_ids)))
        db.execute(delete(KKRecord).where(KKRecord.id.in_(record_ids)))

    db.execute(delete(ScanItem).where(ScanItem.id.in_(item_ids)))

    return {
        'scan_items': len(item_ids),
        'kk_records': len(record_ids),
        'kk_members': int(member_count),
        'exports_invalidated': len(export_ids),
    }


def delete_scan_batch(db: Session, batch_id: str) -> dict:
    batch = db.get(ScanBatch, batch_id)
    if not batch:
        raise LookupError('Batch tidak ditemukan.')

    batch_code = batch.batch_code
    item_ids = list(db.scalars(select(ScanItem.id).where(ScanItem.batch_id == batch_id)).all())
    counts = _delete_scan_items(db, item_ids)
    db.execute(delete(ScanBatch).where(ScanBatch.id == batch_id))
    db.commit()

    return {
        'ok': True,
        'deleted': 'batch',
        'batch_id': batch_id,
        'batch_code': batch_code,
        **counts,
    }


def delete_scan_item(db: Session, item_id: str) -> dict:
    item = db.get(ScanItem, item_id)
    if not item:
        raise LookupError('Hasil scan tidak ditemukan.')

    batch_id = item.batch_id
    filename = item.original_filename
    counts = _delete_scan_items(db, [item_id])

    remaining = db.scalar(
        select(func.count()).select_from(ScanItem).where(ScanItem.batch_id == batch_id)
    ) or 0
    batch_deleted = False
    if remaining == 0:
        db.execute(delete(ScanBatch).where(ScanBatch.id == batch_id))
        batch_deleted = True

    db.commit()
    return {
        'ok': True,
        'deleted': 'scan_item',
        'item_id': item_id,
        'filename': filename,
        'batch_id': batch_id,
        'batch_deleted': batch_deleted,
        **counts,
    }
