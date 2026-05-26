import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Keys assigned in order: 1-9, then a-z (35 total)
_KEYS: list[str] = [str(i) for i in range(1, 10)] + list('abcdefghijklmnopqrstuvwxyz')
MAX_ENTRIES = len(_KEYS)


@dataclass(frozen=True)
class Entry:
    key: str        # single character used to select this entry
    path: Path      # absolute path to .ansi.gz file
    title: str      # display name shown in the menu


def discover(output_dir: Path) -> list[Entry]:
    """Scan output_dir for .ansi.gz files and assign sequential keys."""
    if not output_dir.is_dir():
        log.warning(f'Output directory not found: {output_dir}')
        return []

    files = sorted(output_dir.glob('*.ansi.gz'))
    entries: list[Entry] = []

    for path in files:
        if len(entries) >= MAX_ENTRIES:
            log.warning(f'Catalog full ({MAX_ENTRIES} max); skipping {path.name}')
            break
        title = path.name.removesuffix('.ansi.gz')
        entries.append(Entry(key=_KEYS[len(entries)], path=path, title=title))

    if not entries:
        log.warning(f'No .ansi.gz files found in {output_dir}')

    return entries


def build_key_map(entries: list[Entry]) -> dict[str, Entry]:
    """Return a lowercase-keyed lookup dict for use in session input handling."""
    return {e.key.lower(): e for e in entries}
