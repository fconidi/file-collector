#!/usr/bin/python3
"""Build the Debian package from an explicit file allowlist."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main():
    parser = argparse.ArgumentParser(description="Build File Collector for Debian")
    parser.add_argument("--output-dir", type=Path, required=True)
    output = parser.parse_args().output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    modules = source / "src/file_collector"
    version = re.search(r'__version__ = "([^"]+)"', (modules / "__init__.py").read_text()).group(1)
    with tempfile.TemporaryDirectory(prefix="package-", dir=output) as temporary:
        root = Path(temporary)
        def install(origin, relative, executable=False):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            target.chmod(0o755 if executable else 0o644)
        for name in ("__init__.py", "core.py", "transfer.py", "i18n.py", "app.py", "icon.svg", "icon-small.svg", "style.css"):
            install(modules / name, f"usr/share/file-collector/file_collector/{name}")
        install(source / "packaging/file-collector", "usr/bin/file-collector", True)
        install(source / "packaging/org.syslinuxos.FileCollector.desktop", "usr/share/applications/org.syslinuxos.FileCollector.desktop")
        install(modules / "icon.svg", "usr/share/icons/hicolor/scalable/apps/org.syslinuxos.FileCollector.svg")
        for name in ("README.md", "CHANGELOG.md", "LICENSE"):
            install(source / name, f"usr/share/doc/file-collector/{name}")
        install(modules / "icon.svg", "usr/share/doc/file-collector/src/file_collector/icon.svg")
        for size in ICON_SIZES:
            artwork = modules / ("icon-small.svg" if size <= 32 else "icon.svg")
            target = root / f"usr/share/icons/hicolor/{size}x{size}/apps/org.syslinuxos.FileCollector.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            GdkPixbuf.Pixbuf.new_from_file_at_scale(str(artwork), size, size, True).savev(str(target), "png", [], [])
            target.chmod(0o644)
        control = root / "DEBIAN"
        control.mkdir()
        (control / "control").write_text(
            f"Package: file-collector\nVersion: {version}\nArchitecture: all\n"
            "Section: utils\nPriority: optional\n"
            "Maintainer: Franco Conidi <fconidi@gmail.com>\n"
            "Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, librsvg2-common\n"
            "Description: Gather files from subfolders into one destination\n"
            " Native desktop application with recursive search, collection previews,\n"
            " non-overwriting moves and assisted restore.\n")
        root.chmod(0o755)
        for directory in root.rglob("*"):
            if directory.is_dir():
                directory.chmod(0o755)
        (control / "control").chmod(0o644)
        artifact = output / f"file-collector_{version}_all.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(root), str(artifact)], check=True)
        print(artifact)


if __name__ == "__main__":
    main()
