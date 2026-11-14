# PyInstaller runtime hook: point Panda3D at the plugins (OpenGL display, OpenAL audio, ffmpeg) and its
# Config.prc inside the bundle, before anything imports panda3d.core.
import os
import sys

_panda_dir = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "panda3d")
os.environ.setdefault("PANDA_PRC_DIR", os.path.join(_panda_dir, "etc"))
os.environ.setdefault("PANDA_PRC_PATH", os.path.join(_panda_dir, "etc"))

from panda3d.core import Filename, loadPrcFileData  # noqa: E402

loadPrcFileData("astro-play-bundle", "plugin-path " + Filename.from_os_specific(_panda_dir).get_fullpath())
