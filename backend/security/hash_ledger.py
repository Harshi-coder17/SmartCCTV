"""
SmartCCTV SIH26187 — SHA-256 Append-Only Hash Ledger.

Implements a tamper-evident hash chain using SQLite as the backing store,
with a clean abstract interface designed for future migration to
Hyperledger Fabric without changes to calling code.

Chain invariant:
    entry[0].chain_hash = SHA-256("GENESIS" + entry[0].file_hash)
    entry[n].chain_hash = SHA-256(entry[n].file_hash + entry[n-1].chain_hash)
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from backend.config import settings

logger = logging.getLogger(__name__)

_GENESIS_PREV = "GENESIS"


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """Represents a single entry in the hash ledger."""

    evidence_type: str
    reference_id: str
    file_hash: str               # SHA-256 hex of the evidence file
    actor_id: Optional[str] = None
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entry_index: int = 0
    prev_hash: str = _GENESIS_PREV
    chain_hash: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Abstract Interface — Hyperledger Fabric Contract
# ---------------------------------------------------------------------------


class HashLedgerBackend(ABC):
    """Abstract ledger backend.

    Any Hyperledger Fabric, IPFS, or SQL implementation must satisfy
    this interface.  The SQLiteLedger below is the reference implementation.
    """

    @abstractmethod
    async def append(self, entry: LedgerEntry) -> str:
        """Append an entry to the ledger and return its chain_hash.

        Args:
            entry: LedgerEntry with evidence_type, reference_id, file_hash,
                   and optional actor_id populated.

        Returns:
            The computed chain_hash for this entry.
        """
        ...

    @abstractmethod
    async def verify_chain(self) -> bool:
        """Replay the entire chain and confirm every chain_hash is valid.

        Returns:
            True if the chain is intact; False if any tampering is detected.
        """
        ...

    @abstractmethod
    async def get_entry(self, reference_id: str) -> Optional[LedgerEntry]:
        """Retrieve the latest ledger entry for a given reference_id.

        Args:
            reference_id: The evidence object's UUID.

        Returns:
            LedgerEntry if found, else None.
        """
        ...

    @abstractmethod
    async def get_entry_by_index(self, index: int) -> Optional[LedgerEntry]:
        """Retrieve a ledger entry by its sequential index.

        Args:
            index: 0-based chain index.

        Returns:
            LedgerEntry if found, else None.
        """
        ...


# ---------------------------------------------------------------------------
# SQLite Implementation
# ---------------------------------------------------------------------------


class SQLiteLedger(HashLedgerBackend):
    """SHA-256 append-only hash chain backed by aiosqlite.

    Thread-safety: aiosqlite serialises writes automatically.
    Each call to append() holds an exclusive transaction to prevent
    race conditions on entry_index and prev_hash retrieval.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the ledger.

        Args:
            db_path: Path to the SQLite ledger file.
        """
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _ensure_table(self, conn: aiosqlite.Connection) -> None:
        """Create the ledger table if it does not exist."""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                entry_id     TEXT PRIMARY KEY,
                entry_index  INTEGER NOT NULL UNIQUE,
                evidence_type TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                file_hash    TEXT NOT NULL,
                prev_hash    TEXT NOT NULL,
                chain_hash   TEXT NOT NULL,
                timestamp    TEXT NOT NULL,
                actor_id     TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ref ON ledger(reference_id)"
        )
        await conn.commit()

    @staticmethod
    def _compute_chain_hash(file_hash: str, prev_hash: str) -> str:
        """Compute chain_hash = SHA-256(file_hash || prev_hash)."""
        return hashlib.sha256((file_hash + prev_hash).encode()).hexdigest()

    async def append(self, entry: LedgerEntry) -> str:
        """Append an entry atomically and return its chain_hash."""
        async with aiosqlite.connect(str(self._db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_table(conn)

            # Exclusive transaction: read tip, compute, insert.
            await conn.execute("BEGIN EXCLUSIVE")

            cursor = await conn.execute(
                "SELECT entry_index, chain_hash FROM ledger ORDER BY entry_index DESC LIMIT 1"
            )
            tip = await cursor.fetchone()

            if tip is None:
                new_index = 0
                prev_chain = _GENESIS_PREV
            else:
                new_index = tip["entry_index"] + 1
                prev_chain = tip["chain_hash"]

            chain_hash = self._compute_chain_hash(entry.file_hash, prev_chain)

            await conn.execute(
                """
                INSERT INTO ledger
                    (entry_id, entry_index, evidence_type, reference_id,
                     file_hash, prev_hash, chain_hash, timestamp, actor_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    new_index,
                    entry.evidence_type,
                    entry.reference_id,
                    entry.file_hash,
                    prev_chain,
                    chain_hash,
                    entry.timestamp.isoformat(),
                    entry.actor_id,
                ),
            )
            await conn.commit()

        entry.entry_index = new_index
        entry.prev_hash = prev_chain
        entry.chain_hash = chain_hash
        logger.info(
            "Ledger entry appended index=%d ref=%s chain_hash=%s…",
            new_index,
            entry.reference_id,
            chain_hash[:16],
        )
        return chain_hash

    async def verify_chain(self) -> bool:
        """Replay every entry and verify the chain invariant holds.

        Returns:
            True if valid; False and logs first violation found.
        """
        async with aiosqlite.connect(str(self._db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_table(conn)
            cursor = await conn.execute(
                "SELECT * FROM ledger ORDER BY entry_index ASC"
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.info("Ledger is empty — trivially valid.")
            return True

        prev_chain = _GENESIS_PREV
        for row in rows:
            expected = self._compute_chain_hash(row["file_hash"], prev_chain)
            if expected != row["chain_hash"]:
                logger.error(
                    "Ledger chain violation at index=%d ref=%s "
                    "expected=%s got=%s",
                    row["entry_index"],
                    row["reference_id"],
                    expected,
                    row["chain_hash"],
                )
                return False
            # Also verify stored prev_hash matches what we computed last round.
            if row["prev_hash"] != prev_chain:
                logger.error(
                    "prev_hash mismatch at index=%d", row["entry_index"]
                )
                return False
            prev_chain = row["chain_hash"]

        logger.info("Ledger chain verified — %d entries intact.", len(rows))
        return True

    async def get_entry(self, reference_id: str) -> Optional[LedgerEntry]:
        """Return the most recent ledger entry for a reference_id."""
        async with aiosqlite.connect(str(self._db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_table(conn)
            cursor = await conn.execute(
                "SELECT * FROM ledger WHERE reference_id = ? ORDER BY entry_index DESC LIMIT 1",
                (reference_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return LedgerEntry(
            entry_id=row["entry_id"],
            entry_index=row["entry_index"],
            evidence_type=row["evidence_type"],
            reference_id=row["reference_id"],
            file_hash=row["file_hash"],
            prev_hash=row["prev_hash"],
            chain_hash=row["chain_hash"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            actor_id=row["actor_id"],
        )

    async def get_entry_by_index(self, index: int) -> Optional[LedgerEntry]:
        """Return a ledger entry by sequential index."""
        async with aiosqlite.connect(str(self._db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_table(conn)
            cursor = await conn.execute(
                "SELECT * FROM ledger WHERE entry_index = ?", (index,)
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return LedgerEntry(
            entry_id=row["entry_id"],
            entry_index=row["entry_index"],
            evidence_type=row["evidence_type"],
            reference_id=row["reference_id"],
            file_hash=row["file_hash"],
            prev_hash=row["prev_hash"],
            chain_hash=row["chain_hash"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            actor_id=row["actor_id"],
        )


# ---------------------------------------------------------------------------
# Hyperledger Fabric Stub
# ---------------------------------------------------------------------------


class HyperledgerFabricLedger(HashLedgerBackend):
    """Hyperledger Fabric ledger adapter — migration stub.

    Migration Guide (when Fabric network is provisioned):
    -------------------------------------------------------
    1. Install the Fabric Python SDK:  pip install hf-fabric-sdk
    2. Provision a channel "smartcctv-evidence" with chaincode
       "EvidenceLedger" that exposes:
           - AppendEntry(entry_json) -> chain_hash
           - VerifyChain() -> bool
           - QueryByReferenceId(ref_id) -> entry_json
    3. Replace each `raise NotImplementedError` below with the SDK call:
           self._network.get_contract("EvidenceLedger").submit_transaction(...)
    4. Set LEDGER_BACKEND=fabric in .env and the factory will auto-select this class.
    5. Run scripts/migrate_ledger_to_fabric.py to replay the SQLite chain into Fabric.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "HyperledgerFabricLedger is not yet operational. "
            "See migration guide in the docstring above. "
            "Set LEDGER_BACKEND=sqlite in .env to use the production-ready SQLite ledger."
        )

    async def append(self, entry: LedgerEntry) -> str:
        raise NotImplementedError("Hyperledger Fabric adapter not implemented.")

    async def verify_chain(self) -> bool:
        raise NotImplementedError("Hyperledger Fabric adapter not implemented.")

    async def get_entry(self, reference_id: str) -> Optional[LedgerEntry]:
        raise NotImplementedError("Hyperledger Fabric adapter not implemented.")

    async def get_entry_by_index(self, index: int) -> Optional[LedgerEntry]:
        raise NotImplementedError("Hyperledger Fabric adapter not implemented.")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_LEDGER_BACKENDS = {
    "sqlite": SQLiteLedger,
    "fabric": HyperledgerFabricLedger,
}

_ledger_instance: Optional[HashLedgerBackend] = None


def get_ledger(backend: str = "sqlite") -> HashLedgerBackend:
    """Return the singleton ledger instance for the given backend.

    Args:
        backend: 'sqlite' (default) or 'fabric'.

    Returns:
        A HashLedgerBackend instance.

    Raises:
        ValueError: If an unknown backend name is provided.
    """
    global _ledger_instance
    if _ledger_instance is None:
        if backend not in _LEDGER_BACKENDS:
            raise ValueError(
                f"Unknown ledger backend: '{backend}'. "
                f"Choose one of: {list(_LEDGER_BACKENDS.keys())}"
            )
        cls = _LEDGER_BACKENDS[backend]
        if backend == "sqlite":
            _ledger_instance = cls(settings.HASH_LEDGER_PATH)  # type: ignore[call-arg]
        else:
            _ledger_instance = cls()
    return _ledger_instance


async def init_ledger(db_path: str = "") -> HashLedgerBackend:
    """
    Initialise the ledger singleton with an explicit path at startup.
    Creates the database and table if they don't exist.
    """
    global _ledger_instance
    from backend.config import get_settings
    import aiosqlite
    cfg = get_settings()
    path = Path(db_path) if db_path else cfg.HASH_LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-create the table via a direct connection
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hash_ledger (
                entry_id     TEXT    PRIMARY KEY,
                entry_index  INTEGER NOT NULL,
                evidence_type TEXT   NOT NULL,
                reference_id TEXT    NOT NULL,
                file_hash    TEXT    NOT NULL,
                prev_hash    TEXT    NOT NULL,
                chain_hash   TEXT    NOT NULL,
                timestamp    TEXT    NOT NULL,
                actor_id     TEXT
            )
        """)
        await conn.commit()
    _ledger_instance = SQLiteLedger(path)
    return _ledger_instance
