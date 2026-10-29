"""Optional GitHub release checks, isolated from all keyboard/text processing.

Only a fixed public release endpoint is requested. No account, token, device ID,
typed text, exceptions or document information is accepted by this module.
Installers open in the default browser only after the user chooses Update.
"""
from dataclasses import dataclass
import json
import platform
from queue import Empty, SimpleQueue
import re
import threading
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_URL = "https://api.github.com/repos/sirdimitry/Lado/releases?per_page=10"
INTERVAL = 3600
MAX_RESPONSE = 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(\d{1,5})\.(\d{1,5})\.(\d{1,5})(?:-(alpha|beta|rc|preview)(?:[.-]?(\d{1,5}))?)?(?:\+[0-9A-Za-z.-]+)?$")


def version_key(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    match = VERSION_PATTERN.fullmatch(value)
    if not match:
        return None
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch),
            {None: 3, "rc": 2, "beta": 1, "alpha": 0, "preview": 0}[stage], int(number or 0))


def trusted_download(url, filename):
    if not isinstance(url, str) or not isinstance(filename, str):
        return False
    try:
        parts = urlsplit(url)
        path = unquote(parts.path)
        return (parts.scheme == "https" and parts.hostname == "github.com"
                and parts.port in (None, 443) and not parts.username and not parts.password
                and not parts.query and not parts.fragment and "\\" not in path
                and "\x00" not in path and ".." not in path.split("/")
                and path.startswith("/sirdimitry/Lado/releases/download/")
                and path.rsplit("/", 1)[-1] == filename
                and filename.lower().startswith("lado-") and filename.lower().endswith(".dmg"))
    except ValueError:
        return False


@dataclass(frozen=True)
class Update:
    version: str
    url: str
    filename: str


def find_update(releases, current, architecture=None):
    current_key = version_key(current)
    if current_key is None or not isinstance(releases, list):
        return None
    arch = (architecture or platform.machine()).lower()
    arch = "arm64" if arch in ("arm64", "aarch64") else "x86_64" if arch in ("x86_64", "amd64") else ""
    if not arch:
        return None
    candidates = []
    for release in releases[:100]:
        if not isinstance(release, dict) or release.get("draft", False):
            continue
        tag = release.get("tag_name")
        key = version_key(tag)
        if key is None or key <= current_key:
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        for asset in assets[:100]:
            if not isinstance(asset, dict) or asset.get("state", "uploaded") != "uploaded":
                continue
            name, url = asset.get("name"), asset.get("browser_download_url")
            if not trusted_download(url, name):
                continue
            lower = name.lower()
            if not lower.startswith("lado-" + tag.removeprefix("v").lower() + "-macos-"):
                continue
            rank = 2 if lower.endswith(f"-macos-{arch}.dmg") else 1 if lower.endswith("-macos-universal2.dmg") else 0
            if rank:
                candidates.append((key, rank, Update(tag.removeprefix("v"), url, name)))
    return max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fetch_releases(etag=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Lado",
               "X-GitHub-Api-Version": "2026-03-10"}
    if isinstance(etag, str) and len(etag) <= 512 and "\n" not in etag and "\r" not in etag:
        headers["If-None-Match"] = etag
    request = Request(API_URL, headers=headers, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                return None, None, "unavailable"
            payload = json.loads(data)
            if not isinstance(payload, list):
                return None, None, "unavailable"
            return payload, response.headers.get("ETag"), "ok"
    except HTTPError as error:
        error.close()
        if error.code == 304:
            return None, etag, "not_modified"
        if error.code == 404:
            return [], None, "ok"
        return None, None, "unavailable"
    except (URLError, OSError, ValueError):
        return None, None, "unavailable"


@dataclass(frozen=True)
class CheckResult:
    status: str
    update: Update | None
    manual: bool


class UpdateService:
    """One daemon worker; the AppKit timer polls a thread-safe result queue."""
    def __init__(self, current, architecture=None, fetcher=fetch_releases, clock=monotonic):
        self.current, self.architecture = current, architecture
        self.fetcher, self.clock = fetcher, clock
        self.next_check = clock() + 10
        self.busy = False
        self.etag = None
        self.available = None
        self.results = SimpleQueue()

    def due(self):
        return not self.busy and self.clock() >= self.next_check

    def check(self, manual=False):
        if self.busy:
            return False
        self.busy = True
        def work():
            try:
                releases, etag, status = self.fetcher(self.etag)
                if status == "ok":
                    self.available = find_update(releases, self.current, self.architecture)
                    self.etag = etag
                result = CheckResult("ok" if status in ("ok", "not_modified") else "unavailable",
                                     self.available if status in ("ok", "not_modified") else None, manual)
            except Exception:
                result = CheckResult("unavailable", None, manual)
            self.results.put(result)
        threading.Thread(target=work, name="Lado release check", daemon=True).start()
        return True

    def poll(self):
        try:
            result = self.results.get_nowait()
        except Empty:
            return None
        self.busy = False
        self.next_check = self.clock() + INTERVAL
        return result
