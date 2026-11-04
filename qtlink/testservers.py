"""Máy chủ FTP và sFTP cục bộ để thử nghiệm (mô phỏng máy chủ Sở TNMT). CHỈ DÙNG DEMO."""
from __future__ import annotations
import os
import socket
import threading

import paramiko


# ---------------- FTP (pyftpdlib) ----------------
def start_ftp(root: str, port=2121, user="demo", password="demo", host="0.0.0.0"):
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import ThreadedFTPServer
    os.makedirs(root, exist_ok=True)
    auth = DummyAuthorizer()
    auth.add_user(user, password, root, perm="elradfmwMT")
    handler = type("H", (FTPHandler,), {"authorizer": auth, "passive_ports": range(30000, 30010)})
    srv = ThreadedFTPServer((host, port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[ftp] FTP test tại {host}:{port} -> {root}")
    return srv


# ---------------- sFTP (paramiko) ----------------
class _Server(paramiko.ServerInterface):
    def __init__(self, user, password):
        self.user, self.password = user, password

    def check_auth_password(self, u, p):
        return paramiko.AUTH_SUCCESSFUL if (u, p) == (self.user, self.password) else paramiko.AUTH_FAILED

    def get_allowed_auths(self, u):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


def _make_sftp_iface(root):
    class Handle(paramiko.SFTPHandle):
        def stat(self):
            return paramiko.SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))

    class Iface(paramiko.SFTPServerInterface):
        def _p(self, path):
            full = os.path.realpath(os.path.join(root, path.lstrip("/")))
            if not full.startswith(os.path.realpath(root)):
                raise PermissionError
            return full

        def _err(self, e):
            return paramiko.SFTPServer.convert_errno(e.errno) if hasattr(e, "errno") and e.errno else paramiko.SFTP_FAILURE

        def list_folder(self, path):
            try:
                p = self._p(path)
                out = []
                for n in os.listdir(p):
                    a = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(p, n)))
                    a.filename = n
                    out.append(a)
                return out
            except OSError as e:
                return self._err(e)

        def stat(self, path):
            try:
                return paramiko.SFTPAttributes.from_stat(os.stat(self._p(path)))
            except OSError as e:
                return self._err(e)

        lstat = stat

        def open(self, path, flags, attr):
            try:
                p = self._p(path)
                fd = os.open(p, flags, 0o644)
                mode = "wb" if flags & (os.O_WRONLY | os.O_RDWR) else "rb"
                if flags & os.O_RDWR:
                    mode = "r+b"
                f = os.fdopen(fd, mode)
                h = Handle(flags)
                h.filename = p
                h.readfile = h.writefile = f
                return h
            except OSError as e:
                return self._err(e)

        def mkdir(self, path, attr):
            try:
                os.mkdir(self._p(path))
                return paramiko.SFTP_OK
            except OSError as e:
                return self._err(e)

        def remove(self, path):
            try:
                os.remove(self._p(path))
                return paramiko.SFTP_OK
            except OSError as e:
                return self._err(e)

        def rename(self, old, new):
            try:
                os.replace(self._p(old), self._p(new))
                return paramiko.SFTP_OK
            except OSError as e:
                return self._err(e)

        def canonicalize(self, path):
            return "/" + path.strip("/") if path not in (".", "") else "/"

    return Iface


def start_sftp(root: str, port=2222, user="demo", password="demo", host="0.0.0.0", key_path="data/sftp_host_key"):
    os.makedirs(root, exist_ok=True)
    if os.path.exists(key_path):
        key = paramiko.RSAKey.from_private_key_file(key_path)
    else:
        os.makedirs(os.path.dirname(key_path) or ".", exist_ok=True)
        key = paramiko.RSAKey.generate(2048)
        key.write_private_key_file(key_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(20)
    iface = _make_sftp_iface(root)

    def client(conn):
        t = paramiko.Transport(conn)
        t.add_server_key(key)
        t.set_subsystem_handler("sftp", paramiko.SFTPServer, iface)
        try:
            t.start_server(server=_Server(user, password))
            while t.is_active():
                t.join(1)
        except Exception:  # noqa: BLE001
            pass

    def accept():
        while True:
            conn, _ = sock.accept()
            threading.Thread(target=client, args=(conn,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    print(f"[sftp] sFTP test tại {host}:{port} -> {root}")
    return sock
