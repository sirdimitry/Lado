import json
import sys


def main():
    if "--self-test" in sys.argv:
        from .engine import Buffer, Detector
        from .settings import Settings
        engine = Detector(Settings())
        assert engine.converter.convert("ghbdtn") == "привет"
        assert engine.correction("ghbdtn") == "привет"
        assert engine.correction("GHBDTN") is None
        assert engine.correction("hello") is None
        buf = Buffer(engine)
        buf.feed("ghbdtn")
        assert buf.manual().after == "привет"
        assert buf.manual().after == "ghbdtn"
        result = {"status": "ok", "version": "0.1.0", "network": "none"}
        if sys.platform == "darwin":
            from .platforms.macos import InputSources
            import ApplicationServices as A
            import Quartz as Q
            sources = InputSources()
            result["current_source"] = sources.current()
            result["available_layouts"] = sources.all()
            result["accessibility_permission"] = bool(A.AXIsProcessTrusted())
            result["event_post_permission"] = bool(Q.CGPreflightPostEventAccess())
        print(json.dumps(result, ensure_ascii=False))
        return
    if sys.platform != "darwin":
        raise SystemExit("Lado 0.1 supports macOS. The Windows adapter is planned.")
    from .app import run
    run()


if __name__ == "__main__":
    main()
