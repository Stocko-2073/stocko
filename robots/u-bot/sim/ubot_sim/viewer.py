"""Launch the demo viewer, including macOS/uv Python library-path handling."""
import os
from pathlib import Path
import sys
import sysconfig


def main():
    args = ["-m", "ubot_sim.demo", "--viewer", *sys.argv[1:]]
    if sys.platform == "darwin":
        launcher = Path(sys.executable).parent / "mjpython"
        # mjpython dlopens the venv interpreter; uv's relative libpython path
        # otherwise resolves against the MuJoCo app bundle, not Python's home.
        libdir = sysconfig.get_config_var("LIBDIR")
        if libdir:
            previous = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "/usr/local/lib:/usr/lib")
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{libdir}:{previous}"
        args.insert(0, str(launcher))
    os.execv(sys.executable, [sys.executable, *args])


if __name__ == "__main__":
    main()
