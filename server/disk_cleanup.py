"""
Disk cleanup: preview the list, then confirm -- same click-to-apply pattern as
everything else in Matrix, not silent auto-delete.

Scope is deliberately narrow for this batch: just this user's own temporary-files
folder (%TEMP%), the same category Windows' own Disk Cleanup calls "Temporary
files." It's always safe to clear as the signed-in user -- no elevation needed --
unlike Windows Update Cleanup or the Recycle Bin's other categories, which need
an admin prompt or extra APIs this batch doesn't take on. Rob's been doing this
by hand through Windows' own tool (41.6 MB reclaimed on his first pass); this
just saves the trip, for the one category that's unambiguously safe either way.
"""

import os
import tempfile

import collectors as c

TEMP_ID = "temp"


def _temp_dir():
    return tempfile.gettempdir()


def _walk_files(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            yield os.path.join(dirpath, name)


def scan():
    """What's reclaimable right now, without deleting anything."""
    if not c.IS_WINDOWS:
        return {"supported": False, "items": []}
    root = _temp_dir()
    total_bytes, file_count = 0, 0
    for path in _walk_files(root):
        try:
            total_bytes += os.path.getsize(path)
            file_count += 1
        except OSError:
            continue  # gone, or a permissions quirk -- doesn't count either way
    return {
        "supported": True,
        "items": [{
            "id": TEMP_ID,
            "label": "Temporary files",
            "detail": f"{root} -- files left behind by installers and apps; safe to clear, "
                      "same category as Windows' own Disk Cleanup.",
            "sizeBytes": total_bytes,
            "fileCount": file_count,
        }],
    }


def clean(item_ids):
    """Delete the confirmed items. Returns what actually happened, including what
    couldn't be removed -- a file still open in another program is expected and
    not an error."""
    if not c.IS_WINDOWS:
        raise ValueError("Disk cleanup only works on Windows.")
    if TEMP_ID not in (item_ids or []):
        return {"deletedBytes": 0, "deletedFiles": 0, "skippedFiles": 0}
    root = _temp_dir()
    deleted_bytes = deleted_files = skipped_files = 0
    for path in list(_walk_files(root)):
        try:
            size = os.path.getsize(path)
            os.remove(path)
            deleted_bytes += size
            deleted_files += 1
        except OSError:
            skipped_files += 1  # in use, or already gone -- leave it, don't fail the whole run
    return {"deletedBytes": deleted_bytes, "deletedFiles": deleted_files, "skippedFiles": skipped_files}
