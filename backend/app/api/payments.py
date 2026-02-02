from __future__ import annotations
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database import get_db
from app.models.user import User, Tier
from app.middleware.auth import get_current_user

TIER_LEVEL = {Tier.free: 0, Tier.pro: 1, Tier.legend: 2}
REQUESTED_TIER = {"pro": Tier.pro, "legend": Tier.legend}
from app.services.stripe_service import (
    create_checkout_session,
    handle_checkout_completed,
    handle_invoice_paid,
    handle_subscription_deleted,
    create_billing_portal_session,
)
from app.services.sol_payments import verify_sol_payment

settings = get_settings()
router = APIRouter(prefix="/api/payments", tags=["payments"])


class CheckoutRequest(BaseModel):
    tier: str  # "pro" or "legend"


class SolVerifyRequest(BaseModel):
    tx_signature: str
    tier: str  # "pro" or "legend"


@router.post("/stripe/checkout")
async def stripe_checkout(
    req: CheckoutRequest,
    user: User = Depends(get_current_user),
):
    if req.tier not in ("pro", "legend"):
        raise HTTPException(status_code=400, detail="Invalid tier")

    requested = REQUESTED_TIER[req.tier]
    if TIER_LEVEL[user.tier] >= TIER_LEVEL[requested]:
        raise HTTPException(
            status_code=400,
            detail=f"You already have {user.tier.value} tier. You can only upgrade to a higher tier.",
        )

    try:
        url = await create_checkout_session(user, req.tier)
        return {"checkout_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        await handle_checkout_completed(db, event["data"]["object"])
    elif event["type"] == "invoice.payment_succeeded":
        await handle_invoice_paid(db, event["data"]["object"])
    elif event["type"] == "customer.subscription.deleted":
        await handle_subscription_deleted(db, event["data"]["object"])

    return {"status": "ok"}


@router.post("/stripe/portal")
async def stripe_portal(
    user: User = Depends(get_current_user),
):
    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer found. Subscribe with card first.",
        )

    try:
        url = await create_billing_portal_session(user)
        return {"portal_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user),
):
    return {
        "tier": user.tier.value,
        "expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
        "stripe_subscription_id": user.stripe_subscription_id,
        "has_stripe": bool(user.stripe_customer_id),
    }


@router.post("/sol/verify")
async def sol_verify(
    req: SolVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.tier not in ("pro", "legend"):
        raise HTTPException(status_code=400, detail="Invalid tier")

    requested = REQUESTED_TIER[req.tier]
    if TIER_LEVEL[user.tier] >= TIER_LEVEL[requested]:
        raise HTTPException(
            status_code=400,
            detail=f"You already have {user.tier.value} tier. You can only upgrade to a higher tier.",
        )

    success = await verify_sol_payment(db, user, req.tx_signature, req.tier)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. Ensure you sent the correct amount to the treasury wallet.",
        )

    return {"status": "activated", "tier": req.tier}
