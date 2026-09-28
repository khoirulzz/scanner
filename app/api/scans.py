import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from app.api.deps import admin_required, csrf_required
from app.core.config import get_settings
from app.core.exceptions import ERROR_MESSAGES, ScannerError
from app.core.logging import safe_scan_log
from app.core.security import hash_file
from app.db.session import get_db
from app.models import FieldCorrection, KKMember, KKRecord, ScanAttempt, ScanIssue, ScanItem
from app.providers import get_vision_provider
from app.schemas.extraction import HeaderExtraction, MergedMember
from app.schemas.kk import KKUpdate, MemberUpdate
from app.services.document_detector import rectify_document
from app.services.dusun_service import canonical_dusun
from app.services.extraction_service import extract_document
from app.services.image_optimizer import decode_image
from app.services.pdf_extraction_service import extract_pdf_document
from app.services.quality_checker import inspect_quality
from app.services.thumbnail_service import make_thumbnail
from app.services.validation_service import validate_extraction
from app.services.verification_service import verify_critical_fields
router=APIRouter(prefix='/api',tags=['scans'])
def utcnow(): return datetime.now(timezone.utc)
def _detect_mime(data):
    if data.startswith(b'%PDF-'): return 'application/pdf'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if len(data)>=12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP': return 'image/webp'
    return None

def _load(db,id): return db.scalar(select(ScanItem).where(ScanItem.id==id).options(selectinload(ScanItem.kk_record).selectinload(KKRecord.members),selectinload(ScanItem.issues),selectinload(ScanItem.attempts)))
def _serialize(i):
    r=i.kk_record
    return {'id':i.id,'batch_id':i.batch_id,'item_number':i.item_number,'original_filename':i.original_filename,'status':i.status,'failure_code':i.failure_code,'failure_message':i.failure_message,'quality_metrics':i.quality_metrics,'approved_at':i.approved_at,'exported_at':i.exported_at,'kk':None if not r else {k:getattr(r,k) for k in ['id','no_kk','nama_kepala_keluarga','alamat','rt','rw','kode_pos','dusun','desa','kecamatan','kabupaten','provinsi']},'members':[] if not r else [{k:getattr(m,k) for k in ['id','no_urut_kk','status_hubungan','nik','nama_lengkap','jenis_kelamin','tempat_lahir','tanggal_lahir','agama','pendidikan','jenis_pekerjaan','status_perkawinan','kewarganegaraan','no_paspor','no_kitas_kitap','nama_ayah','nama_ibu','golongan_darah']} for m in r.members],'issues':[{'id':x.id,'severity':x.severity,'code':x.code,'field_name':x.field_name,'message':x.message,'resolved':x.resolved} for x in i.issues]}

def _save(db,item,bundle,issues):
    db.execute(delete(ScanIssue).where(ScanIssue.scan_item_id==item.id))
    if item.kk_record: db.delete(item.kk_record); db.flush()
    h=bundle.header; r=KKRecord(scan_item_id=item.id,no_kk=h.no_kk,nama_kepala_keluarga=h.nama_kepala_keluarga,alamat=h.alamat,rt=h.rt,rw=h.rw,kode_pos=h.kode_pos,dusun=h.dusun,desa=h.desa,kecamatan=h.kecamatan,kabupaten=h.kabupaten,provinsi=h.provinsi); db.add(r); db.flush(); rowmap={}
    for m in bundle.members:
        x=KKMember(kk_record_id=r.id,**m.model_dump()); db.add(x); db.flush(); rowmap[m.no_urut_kk]=x.id
    for issue in issues: db.add(ScanIssue(scan_item_id=item.id,member_id=rowmap.get(issue.get('row')),severity=issue['severity'],code=issue['code'],field_name=issue.get('field_name'),message=issue['message']))

def _existing_document(db, file_hash, item_id):
    return db.scalar(select(ScanItem.id).where(ScanItem.file_hash == file_hash, ScanItem.id != item_id, ScanItem.status.in_(('EXTRACTED','REVIEW_REQUIRED','APPROVED'))).limit(1))

def _existing_household(db, no_kk, item_id):
    return db.scalar(select(ScanItem.id).join(ScanItem.kk_record).where(KKRecord.no_kk == no_kk, ScanItem.id != item_id, ScanItem.status.in_(('EXTRACTED','REVIEW_REQUIRED','APPROVED'))).limit(1))

def _fail_preflight(db, item, code, size):
    attempt=ScanAttempt(scan_item_id=item.id,attempt_number=len(item.attempts)+1,provider='validation',model='upload-preflight',status='FAILED',processing_ms=0,failure_code=code,completed_at=utcnow())
    db.add(attempt); db.flush(); item.current_attempt_id=attempt.id; item.status='FAILED'; item.failure_code=code; item.failure_message=ERROR_MESSAGES[code]; item.original_size=size; item.optimized_size=size; db.commit(); safe_scan_log(scan_id=item.id,status='FAILED',provider='validation',model='upload-preflight',processing_ms=0,failure_code=code); return _serialize(_load(db,item.id))

async def _process(item_id,file,db):
    settings=get_settings(); item=_load(db,item_id)
    if not item: raise HTTPException(404,'Scan item tidak ditemukan.')
    data=await file.read(max(settings.max_upload_bytes,settings.max_pdf_upload_bytes)+1)
    mime_type=_detect_mime(data)
    if not mime_type: return _fail_preflight(db,item,'UNSUPPORTED_FORMAT',len(data))
    max_bytes=settings.max_pdf_upload_bytes if mime_type=='application/pdf' else settings.max_upload_bytes
    if len(data)>max_bytes:
        code='PDF_TOO_LARGE' if mime_type=='application/pdf' else 'FILE_TOO_LARGE'
        return _fail_preflight(db,item,code,len(data))
    file_digest=hash_file(data)
    if _existing_document(db, file_digest, item.id):
        item.file_hash=file_digest; item.original_size=len(data); item.optimized_size=len(data); item.status='FAILED'; item.failure_code='DUPLICATE_DOCUMENT'; item.failure_message=ERROR_MESSAGES['DUPLICATE_DOCUMENT']; db.commit(); return _serialize(_load(db,item.id))
    provider_name='native_pdf' if mime_type=='application/pdf' else settings.vision_provider
    model_name='pymupdf-kk-landscape-v2' if mime_type=='application/pdf' else settings.vision_model
    attempt=ScanAttempt(scan_item_id=item.id,attempt_number=len(item.attempts)+1,provider=provider_name,model=model_name,status='PROCESSING'); db.add(attempt); db.flush(); item.current_attempt_id=attempt.id; item.status='PROCESSING'; item.file_hash=file_digest; item.original_size=len(data); item.optimized_size=len(data); db.commit(); started=time.perf_counter()
    try:
        if mime_type=='application/pdf':
            native=extract_pdf_document(data); bundle=native.bundle; mismatches=native.metadata.pop('row_mismatches',[]); meta=native.metadata; item.thumbnail_mime,item.thumbnail_data=native.thumbnail_mime,native.thumbnail_data; item.quality_metrics={'source_type':'native_pdf_text','word_count':meta['word_count'],'page_count':meta['page_count']}
        else:
            if not settings.enable_vision_fallback: raise ScannerError('VISION_FALLBACK_DISABLED','Vision fallback tidak diaktifkan.')
            image=decode_image(data); h,w=image.shape[:2]; item.image_width=w; item.image_height=h; metrics=inspect_quality(image); rectified,det=rectify_document(image); metrics.update(det); item.quality_metrics=metrics; item.thumbnail_mime,item.thumbnail_data=make_thumbnail(rectified); provider=get_vision_provider(); bundle,mismatches,meta=await extract_document(rectified,provider); verification=await verify_critical_fields(rectified,provider,validate_extraction(bundle.header,bundle.members,mismatches))
            if verification: meta['verification']=verification
        bundle.header.dusun = canonical_dusun(bundle.header.alamat)
        if _existing_household(db, bundle.header.no_kk, item.id):
            raise ScannerError('DUPLICATE_HOUSEHOLD', ERROR_MESSAGES['DUPLICATE_HOUSEHOLD'])
        issues=validate_extraction(bundle.header,bundle.members,mismatches)
        if mime_type!='application/pdf' and meta.get('verification'): issues.append({'code':'VERIFICATION_PERFORMED','message':'Pembacaan verifikasi dijalankan. Periksa hasil sebelum approval.','field_name':None,'severity':'WARNING','row':None})
        _save(db,item,bundle,issues); item.status='REVIEW_REQUIRED' if issues else 'EXTRACTED'; attempt.status='SUCCESS'; attempt.extraction_snapshot=bundle.model_dump(mode='json'); attempt.provider_metadata=meta; attempt.completed_at=utcnow(); attempt.processing_ms=int((time.perf_counter()-started)*1000); db.commit(); safe_scan_log(scan_id=item.id,status=item.status,provider=provider_name,model=model_name,member_count=len(bundle.members),issue_count=len(issues),processing_ms=attempt.processing_ms); db.expire_all(); return _serialize(_load(db,item.id))
    except ScannerError as exc:
        db.rollback(); item=_load(db,item_id); attempt=db.get(ScanAttempt,attempt.id); item.status='FAILED'; item.failure_code=exc.code; item.failure_message=ERROR_MESSAGES.get(exc.code,exc.message); attempt.status='FAILED'; attempt.failure_code=exc.code; attempt.completed_at=utcnow(); attempt.processing_ms=int((time.perf_counter()-started)*1000); db.commit(); return _serialize(_load(db,item.id))
    except Exception:
        db.rollback(); item=_load(db,item_id); attempt=db.get(ScanAttempt,attempt.id); item.status='FAILED'; item.failure_code='PROCESSING_FAILED'; item.failure_message=ERROR_MESSAGES['PROCESSING_FAILED']; attempt.status='FAILED'; attempt.failure_code='PROCESSING_FAILED'; attempt.completed_at=utcnow(); attempt.processing_ms=int((time.perf_counter()-started)*1000); db.commit(); safe_scan_log(scan_id=item.id,status='FAILED',provider=provider_name,model=model_name,processing_ms=attempt.processing_ms,failure_code='PROCESSING_FAILED'); return _serialize(_load(db,item.id))

@router.post('/scan-items/{item_id}/process',dependencies=[Depends(csrf_required)])
async def process_item(item_id:str,file:UploadFile=File(...),db:Session=Depends(get_db)):
    item=_load(db,item_id)
    if not item: raise HTTPException(404,'Scan item tidak ditemukan.')
    if item.status in {'EXTRACTED','REVIEW_REQUIRED','APPROVED','FAILED'}: return _serialize(item)
    return await _process(item_id,file,db)
@router.post('/scan-items/{item_id}/retry',dependencies=[Depends(csrf_required)])
async def retry_item(item_id:str,file:UploadFile=File(...),db:Session=Depends(get_db)): return await _process(item_id,file,db)
@router.get('/scan-items/{item_id}',dependencies=[Depends(admin_required)])
def get_item(item_id:str,db:Session=Depends(get_db)):
    i=_load(db,item_id)
    if not i: raise HTTPException(404,'Scan item tidak ditemukan.')
    return _serialize(i)
@router.get('/scan-items/{item_id}/thumbnail',dependencies=[Depends(admin_required)])
def thumbnail(item_id:str,db:Session=Depends(get_db)):
    i=db.get(ScanItem,item_id)
    if not i or not i.thumbnail_data: raise HTTPException(404,'Thumbnail tidak tersedia.')
    return Response(i.thumbnail_data,media_type=i.thumbnail_mime or 'image/webp')

def _corr(db,item_id,member_id,field,old,new):
    if str(old or '')!=str(new or ''): db.add(FieldCorrection(scan_item_id=item_id,member_id=member_id,field_name=field,original_value=None if old is None else str(old),corrected_value=None if new is None else str(new)))
@router.patch('/scan-items/{item_id}/kk',dependencies=[Depends(csrf_required)])
def update_kk(item_id:str,payload:KKUpdate,db:Session=Depends(get_db)):
    i=_load(db,item_id)
    if not i or not i.kk_record: raise HTTPException(404,'Data KK tidak ditemukan.')
    for f,v in payload.model_dump(exclude_unset=True).items(): _corr(db,i.id,None,f,getattr(i.kk_record,f),v); setattr(i.kk_record,f,v)
    derived_dusun=canonical_dusun(i.kk_record.alamat); _corr(db,i.id,None,'dusun',i.kk_record.dusun,derived_dusun); i.kk_record.dusun=derived_dusun
    i.status='REVIEW_REQUIRED'; i.approved_at=None; db.commit(); return _serialize(_load(db,i.id))
@router.patch('/members/{member_id}',dependencies=[Depends(csrf_required)])
def update_member(member_id:str,payload:MemberUpdate,db:Session=Depends(get_db)):
    m=db.get(KKMember,member_id)
    if not m: raise HTTPException(404,'Anggota tidak ditemukan.')
    r=db.get(KKRecord,m.kk_record_id); i=db.get(ScanItem,r.scan_item_id)
    for f,v in payload.model_dump(exclude_unset=True).items(): _corr(db,i.id,m.id,f,getattr(m,f),v); setattr(m,f,v)
    i.status='REVIEW_REQUIRED'; i.approved_at=None; db.commit(); return {'ok':True}
@router.post('/scan-items/{item_id}/approve',dependencies=[Depends(csrf_required)])
def approve(item_id:str,db:Session=Depends(get_db)):
    i=_load(db,item_id)
    if not i or not i.kk_record: raise HTTPException(404,'Data KK tidak ditemukan.')
    r=i.kk_record; h=HeaderExtraction(**{k:getattr(r,k) for k in ['no_kk','nama_kepala_keluarga','alamat','rt','rw','kode_pos','dusun','desa','kecamatan','kabupaten','provinsi']}); members=[MergedMember(**{k:getattr(m,k) for k in ['no_urut_kk','status_hubungan','nik','nama_lengkap','jenis_kelamin','tempat_lahir','tanggal_lahir','agama','pendidikan','jenis_pekerjaan','status_perkawinan','kewarganegaraan','no_paspor','no_kitas_kitap','nama_ayah','nama_ibu','golongan_darah']}) for m in r.members]; issues=validate_extraction(h,members,[]); blocking=[x for x in issues if x['severity'] in {'ERROR','CRITICAL'}]
    if blocking: raise HTTPException(422,{'message':'Data masih memiliki masalah yang harus diperbaiki.','issues':blocking})
    i.status='APPROVED'; i.approved_at=utcnow(); db.commit(); return _serialize(_load(db,i.id))
