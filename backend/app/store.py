"""Holds the loaded domains and the index connection, and serialises access.

`version` increments on every change so the frontend can poll cheaply and know
whether anything actually moved.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable

from . import edits, eventlog, index, loader, state, writer, xp
from .models import Domain, DomainError


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.conn = index.connect()
        self.domains: list[Domain] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.indexed = 0
        self.version = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.reindex()
        self.reload_domains()

    def reload_domains(self) -> None:
        """Re-read the TOML files. Called at startup and by the file watcher."""
        domains, errors = loader.load_all()
        with self._lock:
            self.domains = domains
            self.errors = errors
            self.version += 1

    def reindex(self) -> None:
        """Throw the index away and replay the log.

        Reconnects first: if the sqlite file was deleted out from under us the
        old handle still points at an unlinked inode and silently writes into
        nothing. Reconnecting is cheap and this runs rarely.
        """
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = index.connect()
            self.indexed, self.warnings = index.rebuild(self.conn)
            self.version += 1

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # -- reads -------------------------------------------------------------

    def domain(self, domain_id: str) -> Domain | None:
        with self._lock:
            for d in self.domains:
                if d.id == domain_id:
                    return d
        return None

    def dashboard(self) -> dict:
        with self._lock:
            payload = state.build_dashboard(self.conn, self.domains, self.errors)
            # Derived alongside the board, and stored nowhere.
            #
            # This used to carry a rule that XP could never affect what the
            # board showed. That rule is gone: `state.py` imports `xp` and
            # seals every node above tier I until its price is paid. What is
            # left is narrower — the *totals* below are a read-only fold, so
            # retuning a constant in `xp.py` re-scores all history at once and
            # needs no migration.
            payload["xp"] = xp.build(self.conn, self.domains)
        payload["version"] = self.version
        return payload

    def domain_view(self, domain_id: str) -> dict | None:
        with self._lock:
            domain = self.domain(domain_id)
            if domain is None:
                return None
            payload = state.build_domain_view(self.conn, domain)
        payload["version"] = self.version
        return payload

    # -- writes ------------------------------------------------------------

    def record(
        self,
        domain_id: str,
        node_id: str,
        kind: str,
        text: str = "",
        value: float | None = None,
    ) -> dict:
        """Append to the log, then mirror into the index. Log first, always —
        if the process dies between the two, a reindex recovers the truth."""
        domain = self.domain(domain_id)
        if domain is None:
            raise DomainError(f"unknown domain `{domain_id}`")
        if domain.node(node_id) is None:
            raise DomainError(f"unknown node `{node_id}` in domain `{domain_id}`")

        with self._lock:
            event = eventlog.append(
                domain_id, node_id, kind, text=text, value=value
            )
            index.add(self.conn, event)
            self.version += 1
        return event

    def spend_unlock(self, domain_id: str, node_id: str, price: float) -> dict:
        """Buy a node's unlock, if the bank covers it.

        The balance check and the write happen under one lock. Split them and
        two unlocks fired together could both see enough XP and both spend it —
        the only place in this app where a race could put a number below zero.
        """
        domain = self.domain(domain_id)
        if domain is None:
            raise DomainError(f"unknown domain `{domain_id}`")
        if domain.node(node_id) is None:
            raise DomainError(f"unknown node `{node_id}` in domain `{domain_id}`")

        with self._lock:
            bank = xp.build(self.conn, self.domains)["bank"]
            if bank < price:
                raise DomainError(
                    f"{price:g} XP needed, {bank:g} banked — {price - bank:g} short"
                )
            event = eventlog.append(
                domain_id, node_id, eventlog.UNLOCK, value=price
            )
            index.add(self.conn, event)
            self.version += 1
        return event

    # -- structural edits --------------------------------------------------

    def mutate(self, domain_id: str, change: Callable[[Domain], Domain]) -> Domain:
        """Apply an edit to a domain, validate it, then write the file.

        The foundation is compiled in and has no file, so there is nothing to
        write and nothing to delete. Refusing here rather than in the handlers
        means every structural endpoint is covered by one check.

        Validation runs before the write, so a rejected edit leaves the file on
        disk untouched.
        """
        with self._lock:
            domain = self.domain(domain_id)
            if domain is None:
                raise DomainError(f"unknown domain `{domain_id}`")
            if domain.foundation:
                raise DomainError(
                    f"`{domain_id}` is built into the app and cannot be edited"
                )

            updated = loader.validate(change(domain))
            if updated.id != domain.id:
                raise DomainError("a domain's id cannot be changed")
            writer.save(updated)
            self._replace(updated)
        return updated

    def create_domain(self, **fields) -> Domain:
        with self._lock:
            taken = {d.id for d in self.domains}
            domain = loader.validate(edits.create_domain(taken=taken, **fields))
            writer.save(domain)
            self.reload_domains()
        return domain

    def delete_domain(self, domain_id: str) -> None:
        """Removes the file only. Its log events stay on disk, harmless and
        ignored, so deleting by mistake loses no history."""
        with self._lock:
            existing = self.domain(domain_id)
            if existing is None:
                raise DomainError(f"unknown domain `{domain_id}`")
            if existing.foundation:
                raise DomainError(
                    f"`{domain_id}` is built into the app and cannot be deleted"
                )
            writer.delete(domain_id)
            self.reload_domains()

    def _replace(self, updated: Domain) -> None:
        """Swap one domain in place without re-reading every file from disk."""
        self.domains = sorted(
            [d for d in self.domains if d.id != updated.id] + [updated],
            key=lambda d: (d.priority, d.title),
        )
        self.version += 1


store = Store()
