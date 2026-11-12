# Run through scripts/build.py; source files and assets resolve relative to this file.
from pathlib import Path
import sys

project = Path(SPECPATH).parent
analysis = Analysis(
    [str(project / "app.py")], pathex=[str(project)],
    binaries=[], datas=[(str(project / "static"), "static"), (str(project / "templates"), "templates")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["playwright", "pytest", "unittest"] + (["tkinter", "_tkinter"] if sys.platform == "win32" else []), noarchive=False,
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive, analysis.scripts, analysis.binaries, analysis.datas, [],
    name="git-folder-dashboard", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
)
