"""File transports: FTP / FTPS / sFTP. Creates remote dirs (e.g. /StationA/yyyy/mm/dd), uploads as .part then renames."""
from __future__ import annotations
import ftplib
import os
import posixpath


def _ftp_makedirs(ftp: ftplib.FTP, path: str):
    ftp.cwd("/")
    for part in [p for p in path.split("/") if p]:
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def upload_ftp(dest: dict, local_path: str, remote_dir: str):
    cls = ftplib.FTP_TLS if dest["protocol"] == "ftps" else ftplib.FTP
    ftp = cls()
    ftp.connect(dest["host"], int(dest.get("port", 21)), timeout=float(dest.get("timeout", 15)))
    try:
        ftp.login(dest.get("username", "anonymous"), password(dest))
        if dest["protocol"] == "ftps":
            ftp.prot_p()
        ftp.set_pasv(bool(dest.get("passive", True)))
        _ftp_makedirs(ftp, remote_dir)
        name = os.path.basename(local_path)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {name}.part", f)
        ftp.rename(f"{name}.part", name)
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            ftp.close()


def upload_sftp(dest: dict, local_path: str, remote_dir: str):
    import paramiko
    t = paramiko.Transport((dest["host"], int(dest.get("port", 22))))
    t.banner_timeout = float(dest.get("timeout", 15))
    try:
        key = None
        if dest.get("key_file"):
            key = paramiko.RSAKey.from_private_key_file(dest["key_file"])
        t.connect(username=dest["username"], password=None if key else password(dest), pkey=key)
        sftp = paramiko.SFTPClient.from_transport(t)
        cur = ""
        for part in [p for p in remote_dir.split("/") if p]:
            cur = f"{cur}/{part}" if remote_dir.startswith("/") or cur else part
            try:
                sftp.stat(cur)
            except IOError:
                sftp.mkdir(cur)
        name = os.path.basename(local_path)
        tmp = posixpath.join(remote_dir, name + ".part")
        sftp.put(local_path, tmp)
        final = posixpath.join(remote_dir, name)
        try:
            sftp.remove(final)
        except IOError:
            pass
        sftp.rename(tmp, final)
        sftp.close()
    finally:
        t.close()


def password(dest: dict) -> str:
    """Secret from an environment variable (password_env) so it never lives in the config file."""
    if dest.get("password_env"):
        return os.environ.get(dest["password_env"], "")
    return dest.get("password", "")

