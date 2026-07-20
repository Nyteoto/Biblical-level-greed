"""Watches the domain files so hand-edits show up without a restart."""
from __future__ import annotations

import threading

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import DOMAINS_DIR, ensure_dirs
from .store import Store

DEBOUNCE_SECONDS = 0.3


class _Handler(FileSystemEventHandler):
    """Editors write in bursts (temp file, rename, chmod). Debounce so one save
    produces one reload."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(getattr(event, "dest_path", "") or event.src_path)
        if not path.endswith(".toml"):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                DEBOUNCE_SECONDS, self._store.reload_domains
            )
            self._timer.daemon = True
            self._timer.start()


def start(store: Store) -> Observer:
    ensure_dirs()
    observer = Observer()
    observer.schedule(_Handler(store), str(DOMAINS_DIR), recursive=False)
    observer.daemon = True
    observer.start()
    return observer
