"""Only explicit preferences/exceptions are written to disk; never input."""
from dataclasses import asdict, dataclass, field, fields
import json
import os
from pathlib import Path


@dataclass
class Settings:
    automatic: bool = True
    double_shift_ms: int = 400
    english_source: str = "com.apple.keylayout.ABC"
    russian_source: str = "com.apple.keylayout.Russian"
    exceptions: list[str] = field(default_factory=list)
    case_sensitive: bool = False
    excluded_apps: list[str] = field(default_factory=lambda: [
        "com.apple.Terminal", "com.googlecode.iterm2", "com.microsoft.VSCode",
        "com.apple.dt.Xcode", "com.agilebits.onepassword7", "com.1password.1password",
    ])


def settings_path() -> Path:
    return Path.home() / "Library/Application Support/Lado/settings.json"


def load(path: Path | None = None) -> Settings:
    try:
        value = json.loads((path or settings_path()).read_text())
        allowed = {f.name: f for f in fields(Settings)}
        clean = {k: v for k, v in value.items() if k in allowed}
        defaults = Settings()
        for k, v in list(clean.items()):
            if type(v) is not type(getattr(defaults, k)):
                del clean[k]
        for k in ("exceptions", "excluded_apps"):
            if k in clean:
                clean[k] = [x[:256] for x in clean[k][:5000] if isinstance(x, str)]
        if "double_shift_ms" in clean:
            clean["double_shift_ms"] = max(200, min(800, clean["double_shift_ms"]))
        return Settings(**clean)
    except (OSError, ValueError, TypeError, AttributeError):
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(temp, 0o600)
    temp.replace(target)
