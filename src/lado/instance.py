"""Process-lifetime advisory lock. The file contains no input or identifiers."""
import fcntl
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return True

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
