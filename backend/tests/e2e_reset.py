"""Reset mutable collections between Playwright runs.

seed.py alone only upserts the fixed IDs; it doesn't clear collections
that accumulate across runs (shortlists, broadcasts, EOIs, deliverables,
engagements created via /assemble or accept, revision_requests,
payment_transactions). Playwright has no equivalent to the pytest
conftest.clean_db autouse fixture, so we run this before seed.py in the
`make e2e` target — the two together make each Playwright run start
from a known state."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deps import db  # noqa: E402


COLLECTIONS = (
    "shortlists",
    "broadcasts",
    "broadcast_runs",
    "eois",
    "revision_requests",
    "deliverables",
    "engagements",
    "payment_transactions",
    "dispute_fee_transactions",
    "refund_audit_receipts",
    "notifications",
    "grievances",
    "reviews",
    "reference_checks",
    "audit_log",
)


async def _reset() -> None:
    for c in COLLECTIONS:
        await db[c].delete_many({})


if __name__ == "__main__":
    asyncio.run(_reset())
    print(f"reset: cleared {len(COLLECTIONS)} collection(s)")
