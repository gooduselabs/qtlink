"""Backward-compatible shim: use qtlink.sinks."""
from .sinks import send as upload, upload_ftp, upload_sftp  # noqa: F401
