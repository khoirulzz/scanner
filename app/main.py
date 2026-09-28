import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, batches, data, deletions, exports, scans
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import ensure_csrf_token, require_admin
from app.db.base import Base
from app.db.session import engine, get_db
from app.models import *

settings = get_settings()
configure_logging()

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / 'static'
TEMPLATES_DIR = APP_DIR / 'templates'


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title='Standalone KK Scanner V1',
    lifespan=lifespan,
    docs_url=None if settings.is_production else '/docs',
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie='kk_scanner_session',
    max_age=43200,
    same_site='lax',
    https_only=settings.is_production,
)

app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.state.templates = templates

_buckets = defaultdict(deque)


@app.middleware('http')
async def security(request: Request, call_next):
    key = None
    limit = None
    client = request.client.host if request.client else 'unknown'

    if request.url.path == '/login' and request.method == 'POST':
        key = f'{client}:login'
        limit = settings.login_rate_limit_per_minute
    elif request.url.path.startswith('/api/') and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        key = f'{client}:api-write'
        limit = settings.api_write_rate_limit_per_minute

    if key:
        now = time.monotonic()
        bucket = _buckets[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse({'detail': 'Terlalu banyak permintaan.'}, status_code=429)
        bucket.append(now)

    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


for router in (auth.router, batches.router, scans.router, data.router, exports.router, deletions.router):
    app.include_router(router)


def ctx(request, **extra):
    return {'csrf_token': ensure_csrf_token(request), 'request': request, **extra}


@app.get('/healthz')
def healthz():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except Exception:
        return JSONResponse({'status': 'error', 'database': 'unavailable'}, status_code=503)
    return {'status': 'ok', 'database': 'ok'}


@app.get('/')
def root(request: Request):
    desktop_access = settings.is_desktop and settings.desktop_auto_login
    return RedirectResponse('/dashboard' if desktop_access or request.session.get('is_admin') else '/login', 303)


@app.get('/dashboard')
def dashboard(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    total = db.scalar(select(func.count()).select_from(ScanItem)) or 0
    approved = db.scalar(select(func.count()).select_from(ScanItem).where(ScanItem.status == 'APPROVED')) or 0
    extracted = db.scalar(select(func.count()).select_from(ScanItem).where(ScanItem.status == 'EXTRACTED')) or 0
    review = db.scalar(select(func.count()).select_from(ScanItem).where(ScanItem.status == 'REVIEW_REQUIRED')) or 0
    failed = db.scalar(select(func.count()).select_from(ScanItem).where(ScanItem.status == 'FAILED')) or 0
    population = db.scalar(select(func.count()).select_from(KKMember)) or 0
    latest = db.scalars(
        select(ScanBatch)
        .options(selectinload(ScanBatch.items))
        .order_by(ScanBatch.created_at.desc())
        .limit(8)
    ).all()
    return templates.TemplateResponse(
        request,
        'dashboard.html',
        ctx(
            request,
            stats={
                'total': total,
                'approved': approved,
                'extracted': extracted,
                'population': population,
                'review': review,
                'failed': failed,
            },
            batches=latest,
        ),
    )


@app.get('/scan')
def scan_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse(request, 'scan.html', ctx(request))


@app.get('/batches')
def batches_page(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    rows = db.scalars(
        select(ScanBatch)
        .options(selectinload(ScanBatch.items))
        .order_by(ScanBatch.created_at.desc())
        .limit(100)
    ).all()
    return templates.TemplateResponse(request, 'batches.html', ctx(request, batches=rows))


@app.get('/batches/{batch_id}')
def batch_detail(request: Request, batch_id: str, db: Session = Depends(get_db)):
    require_admin(request)
    batch = db.scalar(
        select(ScanBatch)
        .where(ScanBatch.id == batch_id)
        .options(selectinload(ScanBatch.items))
    )
    if not batch:
        raise HTTPException(404, 'Batch tidak ditemukan.')
    return templates.TemplateResponse(request, 'batch-detail.html', ctx(request, batch=batch))


@app.get('/scans/{item_id}')
def scan_detail(request: Request, item_id: str, db: Session = Depends(get_db)):
    require_admin(request)
    item = db.get(ScanItem, item_id)
    if not item:
        raise HTTPException(404, 'Scan tidak ditemukan.')
    return templates.TemplateResponse(request, 'scan-detail.html', ctx(request, item=item))


@app.get('/data')
def data_page(request: Request):
    require_admin(request)
    return RedirectResponse('/batches', 303)


@app.get('/exports')
def exports_page(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    export_rows = db.scalars(select(Export).order_by(Export.created_at.desc()).limit(100)).all()
    return templates.TemplateResponse(request, 'exports.html', ctx(request, exports=export_rows))
