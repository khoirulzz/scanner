from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import csrf_required
from app.db.session import get_db
from app.services.deletion_service import delete_scan_batch, delete_scan_item

router = APIRouter(prefix='/api', tags=['deletions'])


@router.delete('/batches/{batch_id}', dependencies=[Depends(csrf_required)])
def remove_batch(batch_id: str, db: Session = Depends(get_db)):
    try:
        return delete_scan_batch(db, batch_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete('/scan-items/{item_id}', dependencies=[Depends(csrf_required)])
def remove_scan_item(item_id: str, db: Session = Depends(get_db)):
    try:
        return delete_scan_item(db, item_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
