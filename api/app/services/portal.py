"""Licensee portal (Phase 7, ADR-0009): onboarding checklist, document vault,
product reorders.

Orders end in the supply ledger: HQ fulfillment writes real shipment rows, so
on-hand and recall stay truthful — the order records the request, the ledger
records reality.
"""

import uuid as uuidlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import DomainError
from app.core.security import TokenClaims
from app.schemas.portal import (
    DocumentCreate,
    DocumentOut,
    FulfillRequest,
    OnboardingTaskOut,
    OrderCreate,
    OrderLineOut,
    OrderOut,
)

# The 60-day checklist template (PROJECT_CONTEXT Phase 7). Instantiated per org
# by the seed; a template table waits until per-network templates are real.
ONBOARDING_TEMPLATE: list[tuple[str, str, int]] = [
    ("Countersign license agreement", "legal", 3),
    ("Complete brand & playbook orientation", "training", 7),
    ("Provision CRM access & lead routing", "systems", 10),
    ("Credential injectors & verify licenses", "compliance", 14),
    ("Order opening product inventory", "supply", 21),
    ("Complete clinical protocols training", "training", 30),
    ("Configure revenue reporting workflow", "finance", 40),
    ("Dry-run monthly attestation with HQ", "finance", 50),
    ("Launch marketing & confirm funnel events", "marketing", 60),
]


class PortalNotFoundError(DomainError):
    code = "portal_not_found"
    status_code = 404


class OrderStateError(DomainError):
    code = "order_state"
    status_code = 409


class LotProductMismatchError(DomainError):
    code = "lot_product_mismatch"
    status_code = 422


def _actor_user_id(actor: TokenClaims) -> UUID | None:
    try:
        return uuidlib.UUID(actor.sub)
    except ValueError:
        return None


# --- Onboarding -------------------------------------------------------------


async def list_onboarding(session: AsyncSession) -> list[OnboardingTaskOut]:
    rows = (
        await session.execute(
            text(
                "SELECT t.id, t.org_id, o.name, t.title, t.category, t.sort_order,"
                " t.due_offset_days, t.completed_at"
                "  FROM onboarding_tasks t JOIN orgs o ON o.id = t.org_id"
                " ORDER BY o.name, t.sort_order"
            )
        )
    ).all()
    return [
        OnboardingTaskOut(
            id=str(tid),
            org_id=str(org_id),
            org_name=org_name,
            title=title,
            category=category,
            sort_order=sort_order,
            due_offset_days=due_offset,
            completed_at=completed_at,
        )
        for tid, org_id, org_name, title, category, sort_order, due_offset, completed_at in rows
    ]


async def complete_task(session: AsyncSession, actor: TokenClaims, task_id: UUID) -> None:
    """Idempotent completion; RLS guarantees the task belongs to the actor's org."""
    updated = (
        await session.execute(
            text(
                "UPDATE onboarding_tasks SET completed_at = now(), completed_by = :user"
                " WHERE id = :id AND completed_at IS NULL RETURNING id"
            ),
            {"id": task_id, "user": _actor_user_id(actor)},
        )
    ).scalar_one_or_none()
    if updated is None:
        exists = (
            await session.execute(
                text("SELECT 1 FROM onboarding_tasks WHERE id = :id"), {"id": task_id}
            )
        ).scalar_one_or_none()
        if exists is None:
            raise PortalNotFoundError("onboarding task not found")


# --- Document vault ---------------------------------------------------------


async def list_documents(session: AsyncSession) -> list[DocumentOut]:
    rows = (
        await session.execute(
            text(
                "SELECT d.id, d.org_id, o.name, d.title, d.category, d.body, d.created_at"
                "  FROM portal_documents d JOIN orgs o ON o.id = d.org_id"
                " ORDER BY d.created_at DESC"
            )
        )
    ).all()
    return [
        DocumentOut(
            id=str(did),
            org_id=str(org_id),
            org_name=org_name,
            title=title,
            category=category,
            body=body,
            created_at=created_at,
        )
        for did, org_id, org_name, title, category, body, created_at in rows
    ]


async def create_document(
    session: AsyncSession, actor: TokenClaims, req: DocumentCreate
) -> DocumentOut:
    doc_id = uuid7()
    org_id = UUID(actor.org_id)
    await session.execute(
        text(
            "INSERT INTO portal_documents (id, org_id, title, category, body, uploaded_by)"
            " VALUES (:id, :org, :title, :category, :body, :by)"
        ),
        {
            "id": doc_id,
            "org": org_id,
            "title": req.title,
            "category": req.category,
            "body": req.body,
            "by": _actor_user_id(actor),
        },
    )
    org_name = (
        await session.execute(text("SELECT name FROM orgs WHERE id = :id"), {"id": org_id})
    ).scalar_one()
    return DocumentOut(
        id=str(doc_id),
        org_id=str(org_id),
        org_name=org_name,
        title=req.title,
        category=req.category,
        body=req.body,
        created_at=datetime.now(UTC),
    )


# --- Product orders ---------------------------------------------------------


async def _order_out(session: AsyncSession, order_id: UUID) -> OrderOut:
    head = (
        await session.execute(
            text(
                "SELECT po.id, po.org_id, o.name, po.location_id, l.name, po.status,"
                " po.submitted_at, po.fulfilled_at"
                "  FROM product_orders po"
                "  JOIN orgs o ON o.id = po.org_id"
                "  JOIN locations l ON l.id = po.location_id"
                " WHERE po.id = :id"
            ),
            {"id": order_id},
        )
    ).one_or_none()
    if head is None:
        raise PortalNotFoundError("order not found")
    lines = (
        await session.execute(
            text(
                "SELECT pl.product_id, p.name, pl.qty"
                "  FROM product_order_lines pl JOIN products p ON p.id = pl.product_id"
                " WHERE pl.order_id = :id ORDER BY p.name"
            ),
            {"id": order_id},
        )
    ).all()
    return OrderOut(
        id=str(head[0]),
        org_id=str(head[1]),
        org_name=head[2],
        location_id=str(head[3]),
        location_name=head[4],
        status=head[5],
        submitted_at=head[6],
        fulfilled_at=head[7],
        lines=[
            OrderLineOut(product_id=str(pid), product_name=pname, qty=qty)
            for pid, pname, qty in lines
        ],
    )


async def list_orders(session: AsyncSession) -> list[OrderOut]:
    ids = (
        (await session.execute(text("SELECT id FROM product_orders ORDER BY created_at DESC")))
        .scalars()
        .all()
    )
    return [await _order_out(session, oid) for oid in ids]


async def create_order(session: AsyncSession, actor: TokenClaims, req: OrderCreate) -> OrderOut:
    loc = (
        await session.execute(
            text("SELECT id, org_id FROM locations WHERE id = :id"),
            {"id": UUID(req.location_id)},
        )
    ).one_or_none()
    if loc is None:
        raise PortalNotFoundError("location not found")
    order_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO product_orders (id, org_id, location_id, status, created_by)"
            " VALUES (:id, :org, :loc, 'draft', :by)"
        ),
        {"id": order_id, "org": loc.org_id, "loc": loc.id, "by": _actor_user_id(actor)},
    )
    for line in req.lines:
        await session.execute(
            text(
                "INSERT INTO product_order_lines (id, org_id, order_id, product_id, qty)"
                " VALUES (:id, :org, :order, :product, :qty)"
            ),
            {
                "id": uuid7(),
                "org": loc.org_id,
                "order": order_id,
                "product": UUID(line.product_id),
                "qty": line.qty,
            },
        )
    return await _order_out(session, order_id)


async def submit_order(session: AsyncSession, order_id: UUID) -> OrderOut:
    updated = (
        await session.execute(
            text(
                "UPDATE product_orders SET status = 'submitted', submitted_at = now()"
                " WHERE id = :id AND status = 'draft' RETURNING id"
            ),
            {"id": order_id},
        )
    ).scalar_one_or_none()
    if updated is None:
        current = await _order_out(session, order_id)  # 404s if truly missing
        raise OrderStateError(f"order is '{current.status}', only drafts can be submitted")
    return await _order_out(session, order_id)


async def fulfill_order(
    session: AsyncSession, actor: TokenClaims, order_id: UUID, req: FulfillRequest
) -> OrderOut:
    """HQ assigns a lot per product line; each line becomes a real shipment row
    (on-hand increments via the ledger triggers — ADR-0003)."""
    order = await _order_out(session, order_id)
    if order.status != "submitted":
        raise OrderStateError(f"order is '{order.status}', only submitted orders can be fulfilled")

    lot_by_product = {a.product_id: UUID(a.lot_id) for a in req.assignments}
    now = datetime.now(UTC)
    for line in order.lines:
        lot_id = lot_by_product.get(line.product_id)
        if lot_id is None:
            raise LotProductMismatchError(f"no lot assigned for product {line.product_name}")
        lot = (
            await session.execute(
                text("SELECT id, product_id FROM lots WHERE id = :id"), {"id": lot_id}
            )
        ).one_or_none()
        if lot is None or str(lot.product_id) != line.product_id:
            raise LotProductMismatchError(
                f"lot does not exist or holds a different product than {line.product_name}"
            )
        await session.execute(
            text(
                "INSERT INTO shipments (id, org_id, location_id, lot_id, qty, shipped_at)"
                " VALUES (:id, :org, :loc, :lot, :qty, :at)"
            ),
            {
                "id": uuid7(),
                "org": UUID(order.org_id),
                "loc": UUID(order.location_id),
                "lot": lot.id,
                "qty": line.qty,
                "at": now,
            },
        )
    await session.execute(
        text("UPDATE product_orders SET status = 'fulfilled', fulfilled_at = :at WHERE id = :id"),
        {"at": now, "id": order_id},
    )
    return await _order_out(session, order_id)
