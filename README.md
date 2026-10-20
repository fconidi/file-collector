<img src="src/file_collector/icon.svg" width="96" alt="File Collector icon">

# File Collector

Gather files scattered across many subfolders into one destination. A native Linux desktop application, useful for collecting comic volumes, documents, photos or music without opening each folder separately.

## How it works

1. Add one or more source folders.
2. Choose file types or enter your own extensions, and search.
3. Select the files you want to collect.
4. Choose a destination and review the preview.
5. Move the selected files in one operation.

For example, after extracting a series of ZIP archives into separate folders, select the Comics preset to gather their PDF, CBR and CBZ volumes. Archives are not extracted by the application. File types identify formats; use the source folders, name filter and selection to choose a particular series.

## Features

- Recursive search across multiple source folders, with overlapping roots deduplicated.
- Presets for comics, documents, images and audio, plus custom extensions or all files.
- Name, size, modification date, folder depth and excluded-folder filters.
- Preview with original paths and destination names.
- Keep conflicting names with numbered suffixes, or skip them. Existing files are never automatically overwritten.
- Background search and transfer, progress display and cancellation.
- Verified copies before original removal when moving between filesystems.
- Persistent history with assisted restore of unchanged files when their original paths are free.
- Light and dark appearance; automatic language selection with English, Italian, French, German and Spanish.
- System window decorations and a scalable application icon.

Source folders, unselected files and original archives remain in place. Symbolic links are excluded from recursive searches. If the destination is inside a source folder, its contents are excluded. Conflicts that appear after the preview are reported and the affected originals are preserved.

Cancellation preserves completed moves and stops further work; the history can restore eligible files. Restore is not a backup: externally modified files, occupied paths and unavailable folders require manual attention. Abrupt shutdown can leave a temporary copy alongside an intact original; review the recorded operation before retrying.

## Installation

With the [SysLinuxOS Tools APT repository](https://github.com/fconidi/SysLinuxOS-Tools) configured:

```sh
sudo apt update
sudo apt install file-collector
```

Or download the `.deb` from [GitHub Releases](https://github.com/fconidi/file-collector/releases) on Debian and compatible distributions:

```sh
sudo apt install ./file-collector_0.2.0_all.deb
```

Open **File Collector** from the applications menu or run `file-collector`.

To run directly from the source directory, install Python 3.10 or newer, PyGObject, GTK 3 and SVG support:

```sh
sudo apt install python3 python3-gi gir1.2-gtk-3.0 librsvg2-common
python3 run.py
```

The operation history is stored locally in `$XDG_STATE_HOME/file-collector/`, or `~/.local/state/file-collector/` when the variable is unset. It contains file paths and integrity hashes and is used for assisted restore. File contents are not stored in the history. The application does not upload files or use a network service.

## License

Copyright © 2026 Franco Conidi. Licensed under GPL-3.0-or-later. The application icon is included under the same license.
