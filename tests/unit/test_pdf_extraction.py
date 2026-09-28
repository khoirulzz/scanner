import asyncio
from io import BytesIO

import fitz
import pytest
from fastapi import UploadFile
from openpyxl import load_workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import batches, exports, scans
from app.core.exceptions import ScannerError
from app.db.base import Base
from app.models import ScanAttempt, ScanBatch, ScanItem
from app.schemas.kk import KKUpdate
from app.services.pdf_extraction_service import extract_pdf_document
from app.services.validation_service import validate_extraction


def synthetic_kk_pdf(pages=1, include_text=True, missing_secondary_row=False, include_second_member=True):
    """Fictitious residents on the same landscape grid as the supplied blanko."""
    document = fitz.open()
    for _ in range(pages):
        page = document.new_page(width=841.9, height=595.3)
        if not include_text:
            continue
        header = [
            (280, 35, 'KARTU KELUARGA'), (250, 57, 'NO : 3311111111111111'),
            (120, 70, 'Nama Kepala Keluarga'), (227, 70, ': BUDI SANTOSO'),
            (120, 80, 'Alamat'), (227, 80, ': JL MELATI 1'),
            (120, 90, 'RT/RW'), (227, 90, ': 001 / 002'),
            (120, 100, 'Kode Pos'), (227, 100, ': 59511'),
            (505, 70, 'Desa/Kelurahan'), (579, 70, ': LAMBANGGELUN'),
            (505, 80, 'Kecamatan'), (579, 80, ': KARANGANYAR'),
            (505, 90, 'Kabupaten/Kota'), (579, 90, ': DEMAK'),
            (505, 100, 'Provinsi'), (579, 100, ': JAWA TENGAH'),
            (83, 121, 'NAMA LENGKAP'), (234, 121, 'NIK'),
            (260, 277, 'KEWARGANEGARAAN'),
        ]
        for x, y, text in header:
            page.insert_text((x, y), text, fontsize=6)
        primary = [
            (16, '1'), (29, 'BUDI SANTOSO'), (206, '3311111111111112'),
            (285, 'LAKI-LAKI'), (326, 'DEMAK'), (426, '01-01-1980'),
            (468, 'ISLAM'), (521, 'SMA'), (642, 'PETANI'), (788, 'O'),
        ]
        secondary = [
            (16, '1'), (29, 'KAWIN TERCATAT'), (111, '01-01-2000'),
            (162, 'KEPALA KELUARGA'), (260, 'WNI'), (337, '-'),
            (403, '-'), (468, 'SUGENG'), (642, 'SRI'),
        ]
        for x, text in primary:
            page.insert_text((x, 153), text, fontsize=6)
        for x, text in secondary:
            page.insert_text((x, 310), text, fontsize=6)
        if include_second_member:
            for x, text in [(16, '2'), (29, 'ANI SANTOSO'), (206, '3311111111111113'), (285, 'PEREMPUAN'), (326, 'DEMAK'), (426, '02-02-2005'), (468, 'ISLAM'), (521, 'SMA'), (642, 'PELAJAR'), (788, 'A')]:
                page.insert_text((x, 164), text, fontsize=6)
        if include_second_member and not missing_secondary_row:
            for x, text in [(16, '2'), (29, 'BELUM KAWIN'), (111, '-'), (162, 'ANAK'), (260, 'WNI'), (337, '-'), (403, '-'), (468, 'BUDI SANTOSO'), (642, 'SRI')]:
                page.insert_text((x, 321), text, fontsize=6)
        # Preprinted empty slot must not become a resident.
        for y in (175, 332):
            page.insert_text((16, y), '3', fontsize=6)
            page.insert_text((29, y), '-', fontsize=6)
            page.insert_text((206 if y == 175 else 162, y), '-', fontsize=6)
        # Even a text watermark is ignored; the supplied PDF uses an image.
        page.insert_text((400, 480), 'DRAFT', fontsize=20)
    data = document.tobytes()
    document.close()
    return data


def test_landscape_kk_maps_all_columns_and_skips_empty_slots():
    result = extract_pdf_document(synthetic_kk_pdf())
    header, members = result.bundle.header, result.bundle.members
    assert result.metadata['parser'] == 'kk-landscape-v2'
    assert header.no_kk == '3311111111111111'
    assert header.nama_kepala_keluarga == 'BUDI SANTOSO'
    assert (header.rt, header.rw, header.kode_pos) == ('001', '002', '59511')
    assert (header.desa, header.kecamatan, header.kabupaten, header.provinsi) == ('LAMBANGGELUN', 'KARANGANYAR', 'DEMAK', 'JAWA TENGAH')
    assert len(members) == 2
    assert members[0].nik == '3311111111111112'
    assert members[0].status_hubungan == 'KEPALA KELUARGA'
    assert members[0].status_perkawinan == 'KAWIN TERCATAT'
    assert members[0].nama_ayah == 'SUGENG'
    assert members[0].nama_ibu == 'SRI'
    assert members[0].tanggal_lahir.isoformat() == '1980-01-01'
    assert members[1].nama_lengkap == 'ANI SANTOSO'
    assert validate_extraction(header, members, result.metadata['row_mismatches']) == []
    assert result.thumbnail_data


def test_missing_secondary_member_row_is_rejected():
    with pytest.raises(ScannerError) as error:
        extract_pdf_document(synthetic_kk_pdf(missing_secondary_row=True))
    assert error.value.code == 'PDF_TABLE_UNREADABLE'


def test_native_pdf_rejects_pdf_without_selectable_text():
    with pytest.raises(ScannerError) as error:
        extract_pdf_document(synthetic_kk_pdf(include_text=False))
    assert error.value.code == 'PDF_NO_SELECTABLE_TEXT'


def test_native_pdf_rejects_multiple_pages():
    with pytest.raises(ScannerError) as error:
        extract_pdf_document(synthetic_kk_pdf(pages=2))
    assert error.value.code == 'PDF_TOO_MANY_PAGES'


def _scan_session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    batch = ScanBatch(batch_code='TEST-001', status='QUEUED')
    item = ScanItem(batch=batch, item_number=1, original_filename='synthetic.pdf')
    session.add(item)
    session.commit()
    return session, item.id


def test_pdf_processing_records_native_attempt():
    session, item_id = _scan_session()
    try:
        result = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        assert result['status'] == 'EXTRACTED'
        assert len(result['members']) == 2
        attempt = session.scalar(select(ScanAttempt).where(ScanAttempt.scan_item_id == item_id))
        assert attempt.status == 'SUCCESS'
        assert attempt.provider == 'native_pdf'
        assert attempt.model == 'pymupdf-kk-landscape-v2'
    finally:
        session.close()


def test_retry_response_uses_replaced_members():
    session, item_id = _scan_session()
    try:
        first = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        assert len(first['members']) == 2
        retried = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf(include_second_member=False)), filename='synthetic.pdf'), session))
        assert retried['status'] == 'EXTRACTED'
        assert len(retried['members']) == 1
        assert len(retried['issues']) == 0
    finally:
        session.close()


def test_batch_approval_and_master_export_include_all_approved_rows():
    session, item_id = _scan_session()
    try:
        asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        item = session.get(ScanItem, item_id)
        approved = batches.approve_extracted(item.batch_id, session)
        assert approved['approved_count'] == 1
        assert approved['batch']['approved'] == 1
        assert approved['batch']['extracted'] == 0

        summary = exports.master_summary(session)
        assert summary == {'kk_count': 1, 'row_count': 2}
        response = exports.download_master(session)
        workbook = load_workbook(BytesIO(response.body))
        assert workbook.active.max_row == 3
        assert response.headers['x-export-kk-count'] == '1'
        assert response.headers['x-export-row-count'] == '2'
    finally:
        session.close()


def test_editing_address_recalculates_canonical_dusun():
    session, item_id = _scan_session()
    try:
        asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        updated = scans.update_kk(item_id, KKUpdate(alamat='DK.BOJONGIRENG RT 001'), session)
        assert updated['kk']['dusun'] == 'BOJONGIRENG'
        cleared = scans.update_kk(item_id, KKUpdate(alamat='Jalan tanpa nama dusun'), session)
        assert cleared['kk']['dusun'] is None
    finally:
        session.close()


def test_duplicate_pdf_and_duplicate_kk_are_not_saved_twice():
    session, first_id = _scan_session()
    try:
        source = synthetic_kk_pdf()
        first = asyncio.run(scans._process(first_id, UploadFile(file=BytesIO(source), filename='first.pdf'), session))
        assert first['status'] == 'EXTRACTED'
        first_item = session.get(ScanItem, first_id)

        identical = ScanItem(batch_id=first_item.batch_id, item_number=2, original_filename='identical.pdf')
        session.add(identical); session.commit()
        duplicate_file = asyncio.run(scans._process(identical.id, UploadFile(file=BytesIO(source), filename='identical.pdf'), session))
        assert (duplicate_file['status'], duplicate_file['failure_code']) == ('FAILED', 'DUPLICATE_DOCUMENT')

        same_household = ScanItem(batch_id=first_item.batch_id, item_number=3, original_filename='same-household.pdf')
        session.add(same_household); session.commit()
        duplicate_kk = asyncio.run(scans._process(same_household.id, UploadFile(file=BytesIO(synthetic_kk_pdf(include_second_member=False)), filename='same-household.pdf'), session))
        assert (duplicate_kk['status'], duplicate_kk['failure_code']) == ('FAILED', 'DUPLICATE_HOUSEHOLD')
    finally:
        session.close()


def test_unexpected_parser_error_marks_item_failed(monkeypatch):
    session, item_id = _scan_session()
    try:
        def raise_error(_data):
            raise RuntimeError('synthetic failure')
        monkeypatch.setattr(scans, 'extract_pdf_document', raise_error)
        result = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        assert result['status'] == 'FAILED'
        assert result['failure_code'] == 'PROCESSING_FAILED'
        attempt = session.scalar(select(ScanAttempt).where(ScanAttempt.scan_item_id == item_id))
        assert attempt.status == 'FAILED'
    finally:
        session.close()


def test_invalid_upload_is_terminal_and_records_preflight_attempt():
    session, item_id = _scan_session()
    try:
        result = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(b'not a supported document'), filename='invalid.pdf'), session))
        assert (result['status'], result['failure_code']) == ('FAILED', 'UNSUPPORTED_FORMAT')
        attempt = session.scalar(select(ScanAttempt).where(ScanAttempt.scan_item_id == item_id))
        assert (attempt.status, attempt.provider, attempt.model) == ('FAILED', 'validation', 'upload-preflight')
    finally:
        session.close()


def test_process_endpoint_is_idempotent_after_terminal_result():
    session, item_id = _scan_session()
    try:
        first = asyncio.run(scans._process(item_id, UploadFile(file=BytesIO(synthetic_kk_pdf()), filename='synthetic.pdf'), session))
        repeated = asyncio.run(scans.process_item(item_id, UploadFile(file=BytesIO(b'not the original PDF'), filename='synthetic.pdf'), session))
        attempts = session.scalars(select(ScanAttempt).where(ScanAttempt.scan_item_id == item_id)).all()
        assert repeated['status'] == first['status'] == 'EXTRACTED'
        assert len(attempts) == 1
    finally:
        session.close()
