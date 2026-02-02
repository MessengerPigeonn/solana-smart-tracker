from __future__ import annotations
import stripe
from datetime import datetime, timezone
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


async def create_checkout_session(user: User, tier: str) -> str:
    """Create a Stripe checkout session and return the URL."""
    price_id = TIER_PRICES.get(tier)
    if not price_id:
        raise ValueError(f"Invalid tier: {tier}")

    params: dict = {
        "payment_method_types": ["card"],
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode": "subscription",
        "success_url": f"{settings.frontend_url}/dashboard/billing?payment=success",
        "cancel_url": f"{settings.frontend_url}/pricing?payment=cancelled",
        "metadata": {"user_id": user.id, "tier": tier},
        "subscription_data": {
            "metadata": {"user_id": user.id, "tier": tier},
        },
    }

    # Reuse existing Stripe customer to prevent duplicates
    if user.stripe_customer_id:
        params["customer"] = user.stripe_customer_id
    else:
        params["customer_email"] = user.email

    session = stripe.checkout.Session.create(**params)
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

    # Store subscription info and sync expiry from Stripe's billing cycle
    subscription_id = session_data.get("subscription")
    user.tier = tier
    user.stripe_customer_id = session_data.get("customer")
    user.stripe_subscription_id = subscription_id

    if subscription_id:
        sub = stripe.Subscription.retrieve(subscription_id)
        user.subscription_expires = datetime.fromtimestamp(
            sub.current_period_end, tz=timezone.utc
        )
    else:
        # Fallback — shouldn't happen with mode="subscription"
        from datetime import timedelta
        user.subscription_expires = datetime.now(timezone.utc) + timedelta(days=30)

    payment = Payment(
        user_id=user.id,
        method=PaymentMethod.stripe,
        amount=amount,
        tier=tier,
        tx_signature=session_data.get("id", ""),
    )
    db.add(payment)
    await db.flush()


async def handle_invoice_paid(db: AsyncSession, invoice_data: dict) -> None:
    """Handle invoice.payment_succeeded webhook for subscription renewals."""
    # Skip initial subscription creation — already handled by checkout.session.completed
    if invoice_data.get("billing_reason") == "subscription_create":
        return

    subscription_id = invoice_data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    # Retrieve subscription to get updated period end
    sub = stripe.Subscription.retrieve(subscription_id)
    user.subscription_expires = datetime.fromtimestamp(
        sub.current_period_end, tz=timezone.utc
    )

    # Determine tier from subscription metadata or current user tier
    tier_str = sub.get("metadata", {}).get("tier", user.tier.value)
    tier = Tier.pro if tier_str == "pro" else Tier.legend
    user.tier = tier

    amount = (invoice_data.get("amount_paid", 0) or 0) / 100
    payment = Payment(
        user_id=user.id,
        method=PaymentMethod.stripe,
        amount=amount,
        tier=tier,
        tx_signature=invoice_data.get("id", ""),
    )
    db.add(payment)
    await db.flush()


async def handle_subscription_deleted(
    db: AsyncSession, subscription_data: dict
) -> None:
    """Handle customer.subscription.deleted webhook — downgrade user."""
    subscription_id = subscription_data.get("id")
    if not subscription_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    user.tier = Tier.free
    user.subscription_expires = None
    user.stripe_subscription_id = None
    await db.flush()


async def create_billing_portal_session(user: User) -> str:
    """Create a Stripe billing portal session and return the URL."""
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.frontend_url}/dashboard/billing",
    )
    return session.url
