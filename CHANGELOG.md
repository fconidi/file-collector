# Changelog

## 0.2.1 — 2026-11-07

- Filters for compound extensions such as `tar.gz` now match.
- Files whose names are not valid UTF-8 are listed and moved instead of breaking the list.
- Moving to FAT/exFAT and other filesystems without atomic no-replace rename now works.
- Copies across filesystems no longer keep setuid/setgid bits.
- Failed moves no longer appear as collections in History; a leftover duplicate after
  an interruption can be cleaned up by Restore; partial copies are removed at the next run.
- Collision suffixes respect the file name length limit and keep `.tar.gz` together.
- A FIFO in place of a file can no longer hang the move.
- Clearer results: errors are reported in the dialog title and in the empty list, and a
  destination that is also a source is explained.
- The search button stays visible; Enter in a filter field searches; language and
  appearance are locked during an operation; closing during an operation closes the
  window when it stops.
- Better contrast for entry borders; accessible names for lists, combos and progress.
- Added a round variant of the icon and a Debian copyright file.

## 0.2.0 — 2026-10-18

- New application icon, with a simplified variant for small sizes and PNG icons from 16 to 256 px.
- Redesigned interface: unified header, grouped sidebar, wider results table with right-aligned sizes, and a bottom action bar with a single highlighted "Preview and move" action.
- Language and appearance moved to a settings menu.
- Redesigned light and dark themes with clearer focus, hover and disabled states.
- Dialogs follow the selected appearance; empty results show a dedicated message.

## 0.1.0 — 2026-10-17

- Collect selected files from multiple subfolder trees into a single destination.
- Search by file type, name, size, modification date and folder depth.
- Preview destination names and preserve conflicting files with numbered suffixes.
- Move files in the background with cancellation and verified cross-filesystem copies.
- Restore eligible moves from persistent operation history.
- Add light and dark appearance, five interface languages and a scalable icon.
