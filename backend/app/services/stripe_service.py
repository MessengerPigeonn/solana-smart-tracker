from __future__ import annotations
import stripe
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.user import User, Tier
from app.models.payment import Payment, PaymentMethod

settings = get_settings()
stripe.api_key = settings.stripe_secret_key

TIER_PRICES = {
    "pro": settings.stripe_pro_price_id,
    "legend": settings.stripe_legend_price_id,
}

TIER_DURATION_DAYS = {
    "pro": 30,
    "legend": 30,
}


async def create_checkout_session(user: User, tier: str) -> str:
    """Create a Stripe checkout session and return the URL."""
    price_id = TIER_PRICES.get(tier)
    if not price_id:
        raise ValueError(f"Invalid tier: {tier}")

    session = stripe.checkout.Session.create(
        customer_email=user.email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.frontend_url}/dashboard?payment=success",
        cancel_url=f"{settings.frontend_url}/pricing?payment=cancelled",
        metadata={"user_id": user.id, "tier": tier},
    )
    return session.url


async def handle_checkout_completed(
    db: AsyncSession, session_data: dict
) -> None:
    """Handle successful Stripe checkout webhook."""
    user_id = session_data.get("metadata", {}).get("user_id")
    tier_str = session_data.get("metadata", {}).get("tier", "pro")
    amount = (session_data.get("amount_total", 0) or 0) / 100

    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    tier = Tier.pro if tier_str == "pro" else Tier.legend
    duration = TIER_DURATION_DAYS.get(tier_str, 30)

    user.tier = tier
    user.subscription_expires = datetime.now(timezone.utc) + timedelta(days=duration)
    user.stripe_customer_id = session_data.get("customer")

    payment = Payment(
        user_id=user.id,
        method=PaymentMethod.stripe,
        amount=amount,
        tier=tier,
        tx_signature=session_data.get("id", ""),
    )
    db.add(payment)
    await db.flush()
