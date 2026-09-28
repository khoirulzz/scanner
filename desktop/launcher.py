import base64
import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
import webview

HOST = '127.0.0.1'
STARTUP_TIMEOUT_SECONDS = 25


def _data_root() -> Path:
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        root = Path(local_app_data) / 'KKScanner'
    else:
        root = Path.home() / '.kk_scanner'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resource_root() -> Path:
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[1]


def _icon_path() -> Path | None:
    icon_path = _resource_root() / 'assets' / 'scanner.ico'
    return icon_path if icon_path.exists() else None


def _icon_data_uri() -> str | None:
    icon_path = _icon_path()
    if icon_path is None:
        return None
    try:
        encoded = base64.b64encode(icon_path.read_bytes()).decode('ascii')
    except OSError:
        return None
    return f'data:image/x-icon;base64,{encoded}'


def _load_or_create_secret(root: Path) -> str:
    secret_file = root / 'session.secret'
    if secret_file.exists():
        value = secret_file.read_text(encoding='utf-8').strip()
        if value:
            return value

    value = secrets.token_urlsafe(64)
    secret_file.write_text(value, encoding='utf-8')
    return value


def _configure_environment(root: Path) -> None:
    database_file = root / 'kk_scanner.db'
    webview_data = root / 'webview'
    webview_data.mkdir(parents=True, exist_ok=True)

    os.environ['APP_ENV'] = 'desktop'
    os.environ['DESKTOP_AUTO_LOGIN'] = 'true'
    os.environ['DATABASE_URL'] = f"sqlite:///{database_file.as_posix()}"
    os.environ['SECRET_KEY'] = _load_or_create_secret(root)
    os.environ.setdefault('ENABLE_VISION_FALLBACK', 'false')
    os.environ.setdefault('MAX_BATCH_ITEMS', '50')


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


class ScannerServer(threading.Thread):
    def __init__(self, port: int):
        super().__init__(name='kk-scanner-server', daemon=True)
        self.port = port
        self.server: uvicorn.Server | None = None
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            from app.main import app

            config = uvicorn.Config(
                app=app,
                host=HOST,
                port=self.port,
                log_level='warning',
                access_log=False,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as exc:
            self.error = exc

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True


def _wait_until_ready(server: ScannerServer) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    health_url = f'http://{HOST}:{server.port}/healthz'

    while time.monotonic() < deadline:
        if server.error is not None:
            return False
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.2)

    return False


def _show_error(message: str) -> None:
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(0, message, 'KK Scanner', 0x10)
    else:
        print(message, file=sys.stderr)


def _splash_html() -> str:
    icon = _icon_data_uri()
    logo = (
        f'<img class="app-logo" src="{icon}" alt="KK Scanner">'
        if icon
        else '<div class="app-logo fallback">KS</div>'
    )
    html = '''<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#172033;background:#f4f7fb}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden}body{display:grid;place-items:center;background:radial-gradient(circle at 50% 20%,#e9f2ff 0,transparent 42%),#f4f7fb}
.card{width:min(430px,calc(100% - 44px));padding:34px 36px 30px;border:1px solid #dde6f1;border-radius:24px;background:#ffffffea;box-shadow:0 22px 70px #17345c18;text-align:center;backdrop-filter:blur(10px)}
.app-logo{width:74px;height:74px;object-fit:contain;margin:0 auto 18px;filter:drop-shadow(0 8px 18px #1b4d9630)}
.app-logo.fallback{display:grid;place-items:center;border-radius:20px;background:linear-gradient(145deg,#2867d4,#15458f);color:white;font-weight:850;font-size:24px;letter-spacing:-.04em}
h1{margin:0;font-size:25px;letter-spacing:-.035em}p{margin:7px 0 0;color:#708095;font-size:13px;line-height:1.5}
.loader{width:48px;height:48px;margin:26px auto 18px;border-radius:50%;border:4px solid #dce8f8;border-top-color:#2867d4;animation:spin .82s linear infinite}
.status{font-size:14px;font-weight:800;color:#29435f}.detail{min-height:20px;margin-top:7px;color:#8492a5;font-size:12px}.foot{margin-top:21px;padding-top:17px;border-top:1px solid #edf1f6;color:#9aa7b8;font-size:11px}
.error .loader{display:none}.error .status{color:#a93434}.error .detail{color:#785151}.error .card{border-color:#f0c8c8;background:#fffafa}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<main class="card">
  __LOGO__
  <h1>KK Scanner</h1>
  <p>Menyiapkan aplikasi agar siap digunakan.</p>
  <div class="loader" aria-hidden="true"></div>
  <div class="status" id="status">Menyiapkan aplikasi...</div>
  <div class="detail" id="detail">Mohon tunggu sebentar.</div>
  <div class="foot">Data operasional tetap tersimpan secara lokal di perangkat ini.</div>
</main>
<script>
window.setStartupStatus=(message,detail)=>{
  document.body.classList.remove('error');
  document.getElementById('status').textContent=message||'Menyiapkan aplikasi...';
  document.getElementById('detail').textContent=detail||'';
};
window.setStartupError=(message,detail)=>{
  document.body.classList.add('error');
  document.getElementById('status').textContent=message||'Aplikasi tidak dapat dijalankan';
  document.getElementById('detail').textContent=detail||'Tutup aplikasi lalu coba kembali.';
};
</script>
</body>
</html>'''
    return html.replace('__LOGO__', logo)


def _set_status(window, message: str, detail: str = '') -> None:
    try:
        window.evaluate_js(
            f'window.setStartupStatus({json.dumps(message)}, {json.dumps(detail)});'
        )
    except Exception:
        pass


def _set_startup_error(window, message: str, detail: str) -> None:
    try:
        window.evaluate_js(
            f'window.setStartupError({json.dumps(message)}, {json.dumps(detail)});'
        )
    except Exception:
        pass


class RuntimeState:
    def __init__(self) -> None:
        self.server: ScannerServer | None = None


def _bootstrap(window, root: Path, state: RuntimeState) -> None:
    try:
        _set_status(window, 'Menyiapkan penyimpanan lokal...', 'Memeriksa folder data dan konfigurasi.')
        _configure_environment(root)

        _set_status(window, 'Menyiapkan layanan scanner...', 'Mencari port lokal yang tersedia.')
        port = _find_free_port()

        _set_status(window, 'Menyalakan server lokal...', 'Memuat komponen pemrosesan dokumen.')
        server = ScannerServer(port)
        state.server = server
        server.start()

        _set_status(window, 'Memeriksa database...', 'Menunggu layanan lokal siap digunakan.')
        if not _wait_until_ready(server):
            server.stop()
            detail = str(server.error) if server.error else 'Layanan lokal tidak merespons dalam batas waktu.'
            _set_startup_error(
                window,
                'KK Scanner gagal disiapkan',
                f'{detail} Tutup aplikasi lalu coba kembali.',
            )
            return

        _set_status(window, 'Membuka KK Scanner...', 'Semua komponen siap.')
        time.sleep(0.18)
        window.load_url(f'http://{HOST}:{port}/')
    except Exception as exc:
        if state.server is not None:
            state.server.stop()
        _set_startup_error(
            window,
            'KK Scanner gagal disiapkan',
            f'{exc} Tutup aplikasi lalu coba kembali.',
        )


def main() -> int:
    root = _data_root()
    state = RuntimeState()

    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True

    window = webview.create_window(
        'KK Scanner',
        html=_splash_html(),
        width=1366,
        height=820,
        min_size=(1024, 650),
        resizable=True,
        text_select=True,
        background_color='#F4F7FB',
    )

    icon_path = _icon_path()
    try:
        webview.start(
            _bootstrap,
            (window, root, state),
            debug=False,
            private_mode=False,
            storage_path=str(root / 'webview'),
            icon=str(icon_path) if icon_path else None,
        )
    except Exception as exc:
        _show_error(
            'KK Scanner tidak dapat membuka jendela aplikasi. '
            'Pastikan Microsoft Edge WebView2 Runtime tersedia.\n\n'
            f'Detail: {exc}'
        )
        return 1
    finally:
        if state.server is not None:
            state.server.stop()
            state.server.join(timeout=10)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
