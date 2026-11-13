"""
Warm plugin worker for the FC engine: one long-lived Python process that imports the SDK and its common libraries once,
then runs each plugin job in a fresh forked child, so a run skips interpreter startup and imports but stays isolated.

The engine starts it with ``connect_tagbio_py --worker --engine_pid <pid>``. The worker listens on a localhost port and
prints ``TAGBIO_WORKER_READY <port> <token>``. Per job the engine connects, sends one JSON line
``{"token", "args", "cwd", "stdout", "stderr"}`` (args = the usual connect_tagbio_py arguments), and reads
``STARTED <pid>`` then ``EXIT <code>``; a connection that closes without EXIT means the child died. The worker exits
when the engine process is gone.
"""
import json
import os
import random
import secrets
import selectors
import socket
import sys
import time

# Imported once here, shared by every child. papermill/jupyter stay out: their ZeroMQ/asyncio state is not fork-safe.
PRELOAD = ['pandas', 'numpy', 'pyarrow', 'plotly.express', 'plotly.io', 'tagbiopy.cli', 'tagbiopy.report']


def _preload():
    import importlib
    for name in PRELOAD:
        try:
            importlib.import_module(name)
        except Exception:
            pass


def _engine_alive(pid):
    if pid is None:
        return os.getppid() != 1
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _reap():
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _run_child(connection, job):
    """In the forked child: redirect output, run the plugin as connect_tagbio_py would, report the exit code."""
    code = 1
    try:
        connection.sendall(f'STARTED {os.getpid()}\n'.encode())
        out = os.open(job['stdout'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        err = os.open(job['stderr'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(out, 1)
        os.dup2(err, 2)
        os.chdir(job['cwd'])
        # every child would otherwise continue the parent's random sequence
        random.seed()
        if 'numpy' in sys.modules:
            sys.modules['numpy'].random.seed()
        sys.argv = ['connect_tagbio_py'] + list(job['args'])
        from tagbiopy import cli
        try:
            cli.main()
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BaseException:
            import traceback
            traceback.print_exc()
            code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        try:
            connection.sendall(f'EXIT {code}\n'.encode())
            connection.close()
        except Exception:
            pass
        os._exit(code if 0 <= code < 256 else 1)


def _read_job(connection, token):
    connection.settimeout(10)
    data = b''
    while not data.endswith(b'\n'):
        chunk = connection.recv(65536)
        if not chunk:
            return None
        data += chunk
    job = json.loads(data.decode())
    return job if secrets.compare_digest(str(job.get('token', '')), token) else None


def serve(engine_pid=None):
    _preload()
    token = secrets.token_hex(16)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 0))
    server.listen(64)
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ)
    print(f'TAGBIO_WORKER_READY {server.getsockname()[1]} {token}', flush=True)
    while _engine_alive(engine_pid):
        for _ in selector.select(timeout=1.0):
            try:
                connection, _ = server.accept()
            except BlockingIOError:
                continue
            connection.setblocking(True)
            try:
                job = _read_job(connection, token)
            except Exception:
                job = None
            if job is None:
                connection.close()
                continue
            pid = os.fork()
            if pid == 0:
                selector.close()
                server.close()
                _run_child(connection, job)
            connection.close()
        _reap()
    server.close()


def main(argv):
    engine_pid = None
    if '--engine_pid' in argv:
        engine_pid = int(argv[argv.index('--engine_pid') + 1])
    serve(engine_pid)
