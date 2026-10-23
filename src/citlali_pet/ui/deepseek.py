"""Open the separately installed official DeepSeek Harness without blocking animation."""
import json
from http.client import HTTPConnection
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit
import webbrowser


DEFAULT_ROOT = Path(r'D:\AI\DeepSeek')
PORT = 3080
_LOCK = threading.Lock()


def installation_root():
    return Path(os.environ.get('CITLALI_DEEPSEEK_ROOT', str(DEFAULT_ROOT))).resolve()


def launch_environment(root):
    """Keep Harness state, package caches and child temporary files on its drive."""
    env = os.environ.copy()
    locations = {
        'DSH_HOME': root/'data',
        'TEMP': root/'workspace/.runtime-temp', 'TMP': root/'workspace/.runtime-temp',
        'npm_config_cache': root/'cache/npm', 'npm_config_store_dir': root/'cache/pnpm-store',
        'PNPM_HOME': root/'cache/pnpm', 'COREPACK_HOME': root/'cache/corepack',
        'XDG_CACHE_HOME': root/'cache',
    }
    for name, path in locations.items():
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env['DSH_TELEMETRY_DISABLED'] = '1'
    env['DSH_PERMISSION_MODE'] = 'workspace-write'
    return env


def local_url(value):
    """Only accept the URL announced by our loopback-only service."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                and parsed.port == PORT and not parsed.username and not parsed.password)
    except ValueError:
        return False


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    import ctypes as C
    from ctypes import wintypes as W
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel.GetExitCodeProcess.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        status = W.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, C.byref(status)) and status.value == 259)
    finally:
        kernel.CloseHandle(handle)


def service_ready(url):
    if not local_url(url):
        return False
    connection = HTTPConnection('127.0.0.1', PORT, timeout=1)
    try:
        # The bootstrap token stays in the browser handoff, never in a probe or error.
        connection.request('GET', '/')
        response = connection.getresponse()
        # Harness protects its static page too; a fresh browser exchanges the
        # announced token for a cookie. A credential-free probe receives 401.
        return response.status == 401 or (response.status == 200 and b'<html' in response.read(8192).lower())
    except OSError:
        return False
    finally:
        connection.close()


def ensure_service(root=None, timeout=60):
    root = root or installation_root()
    state_path = root/'data/pet-service.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if process_alive(state.get('pid')) and service_ready(state.get('url')):
            return state['url']
    except (OSError, ValueError, AttributeError):
        pass
    entry = root/'cli/node_modules/@deepseek-ai/dsh/lib/bin.js'
    try:
        runtime = json.loads((root/'runtime.json').read_text(encoding='utf-8-sig'))
        node = Path(runtime['node'])
        if not node.is_file() or not entry.is_file():
            raise FileNotFoundError
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError(f'尚未安装 DeepSeek。请运行 work/install_deepseek.ps1；安装目录：{root}') from None
    env = launch_environment(root)
    workspace = root/'workspace'
    workspace.mkdir(exist_ok=True)
    log = root/'logs/web.log'
    log.parent.mkdir(exist_ok=True)
    with log.open('wb') as output:
        child = subprocess.Popen(
            [str(node), str(entry), 'web', '--host', '127.0.0.1', '--port', str(PORT), '--no-open'],
            cwd=workspace, env=env, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    deadline = time.monotonic()+timeout
    try:
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f'DeepSeek 启动失败（退出码 {child.returncode}）。请查看 {log}')
            content = log.read_text(encoding='utf-8', errors='replace')
            match = re.search(r'^dsh web: (http://127\.0\.0\.1:\d+/\S*)', content, re.MULTILINE)
            if match and service_ready(match[1]):
                state_path.write_text(json.dumps({'pid': child.pid, 'url': match[1]}), encoding='utf-8')
                return match[1]
            time.sleep(.2)
        raise RuntimeError(f'DeepSeek 启动超时。请查看 {log}')
    except BaseException:
        child.terminate()
        child.wait(timeout=10)
        raise


def open_assistant(on_error):
    """Run startup and browser handoff on a worker; repeated menu clicks reuse it."""
    if not _LOCK.acquire(blocking=False):
        return

    def worker():
        try:
            url = ensure_service()
            if not webbrowser.open(url):
                raise RuntimeError(f'无法打开浏览器。请查看 {installation_root() / "logs/web.log"} 中的本机地址。')
        except Exception as error:
            on_error(str(error))
        finally:
            _LOCK.release()

    threading.Thread(target=worker, name='PetDeepSeek', daemon=True).start()
