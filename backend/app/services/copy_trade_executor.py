from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.callout import Callout
from app.models.copy_trade_config import CopyTradeConfig
from app.models.copy_trade import CopyTrade, TradeSide, TxStatus, SellTrigger
from app.models.trading_wallet import TradingWallet
from app.services.jupiter_swap import jupiter_swap, SOL_MINT, LAMPORTS_PER_SOL
from app.services.trading_wallet_service import decrypt_private_key, get_wallet_balance

settings = get_settings()
logger = logging.getLogger(__name__)


def evaluate_callout(callout: Callout, config: CopyTradeConfig) -> Tuple[bool, str]:
    """Check whether a callout passes the user's safety rules."""
    if not settings.copy_trade_enabled:
        return False, "Copy trading is globally disabled"
    if not config.enabled:
        return False, "User copy trading is disabled"
    if not config.trading_wallet_pubkey:
        return False, "No trading wallet configured"

    signal_types = config.signal_types or ["buy"]
    if callout.signal.value not in signal_types:
        return False, f"Signal type {callout.signal.value} not in {signal_types}"
    if callout.score < config.min_score:
        return False, f"Score {callout.score} below minimum {config.min_score}"
    if config.max_rug_risk is not None and callout.rug_risk_score is not None:
        if callout.rug_risk_score > config.max_rug_risk:
            return False, f"Rug risk {callout.rug_risk_score} exceeds max {config.max_rug_risk}"
    if callout.liquidity is not None and callout.liquidity < config.min_liquidity:
        return False, f"Liquidity ${callout.liquidity} below minimum ${config.min_liquidity}"
    if callout.market_cap is not None and callout.market_cap < config.min_market_cap:
        return False, f"Market cap ${callout.market_cap} below minimum ${config.min_market_cap}"
    if config.skip_print_scan and callout.scan_source == "print_scan":
        return False, "Print scan tokens skipped by config"

    # Bundle risk gate
    bundle_risk = getattr(callout, "bundle_risk", None)
    if bundle_risk == "high":
        return False, "High bundle risk detected"
    if bundle_risk == "medium" and config.skip_bundled_tokens:
        return False, "Medium bundle risk — skipped by config"

    # Bundle dump gate
    bundle_pct = getattr(callout, "bundle_pct", 0) or 0
    bundle_held_pct = getattr(callout, "bundle_held_pct", 0) or 0
    if bundle_pct > 15 and bundle_held_pct < bundle_pct * 0.3:
        return False, "Bundlers actively dumping"

    # Deployer rug gate
    deployer_rug_count = getattr(callout, "deployer_rug_count", 0) or 0
    if deployer_rug_count >= 2:
        return False, f"Serial rugger deployer ({deployer_rug_count} rugs)"

    # Conviction gate
    conviction_score = getattr(callout, "conviction_score", None)
    if conviction_score is not None and conviction_score < 20:
        return False, f"Low conviction score ({conviction_score:.0f}) — early buyers dumping"

    # Strict safety score floor
    if config.strict_safety and callout.score < 60:
        return False, f"Score {callout.score} below strict safety floor (60)"

    return True, "Eligible"


async def _check_daily_limit(db: AsyncSession, user_id: str, config: CopyTradeConfig) -> float:
    """Return remaining SOL allowance for today."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(CopyTrade.sol_amount), 0.0)).where(
            CopyTrade.user_id == user_id,
            CopyTrade.side == TradeSide.buy,
            CopyTrade.tx_status != TxStatus.failed,
            CopyTrade.created_at >= today_start,
        )
    )
    spent_today = result.scalar() or 0.0
    max_daily = min(config.max_daily_sol, settings.copy_trade_max_sol_per_day)
    return max(0.0, max_daily - spent_today)


async def _check_cooldown(db: AsyncSession, user_id: str, token_address: str, cooldown_seconds: int) -> bool:
    """Check if cooldown has passed since last trade for this token."""
    if cooldown_seconds <= 0:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    result = await db.execute(
        select(CopyTrade).where(
            CopyTrade.user_id == user_id,
            CopyTrade.token_address == token_address,
            CopyTrade.side == TradeSide.buy,
            CopyTrade.created_at >= cutoff,
        ).limit(1)
    )
    return result.scalar_one_or_none() is None


async def execute_buy(
    config: CopyTradeConfig,
    callout: Callout,
    db: AsyncSession,
) -> Optional[CopyTrade]:
    """Execute a buy trade for a callout."""
    user_id = config.user_id

    eligible, reason = evaluate_callout(callout, config)
    if not eligible:
        logger.info(f"Callout {callout.id} not eligible for user {user_id}: {reason}")
        return None

    cooldown_ok = await _check_cooldown(db, user_id, callout.token_address, config.cooldown_seconds)
    if not cooldown_ok:
        logger.info(f"Cooldown active for {callout.token_symbol} user {user_id}")
        return None

    remaining_sol = await _check_daily_limit(db, user_id, config)
    if remaining_sol <= 0:
        logger.info(f"Daily SOL limit reached for user {user_id}")
        return None

    trade_sol = min(config.max_trade_sol, settings.copy_trade_max_sol_per_trade, remaining_sol)
    if trade_sol < 0.001:
        return None

    wallet_result = await db.execute(
        select(TradingWallet).where(TradingWallet.user_id == user_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if not wallet:
        logger.warning(f"No trading wallet for user {user_id}")
        return None

    balance = await get_wallet_balance(wallet.public_key)
    if balance is None or balance < trade_sol + 0.01:
        trade = CopyTrade(
            user_id=user_id, callout_id=callout.id,
            token_address=callout.token_address, token_symbol=callout.token_symbol,
            side=TradeSide.buy, sol_amount=trade_sol, token_amount=0,
            price_at_execution=callout.price_at_callout, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, error_message=f"Insufficient balance: {balance} SOL",
        )
        db.add(trade)
        return trade

    amount_lamports = int(trade_sol * LAMPORTS_PER_SOL)
    quote = await jupiter_swap.get_quote(
        input_mint=SOL_MINT, output_mint=callout.token_address,
        amount_lamports=amount_lamports, slippage_bps=config.slippage_bps,
    )
    if not quote:
        trade = CopyTrade(
            user_id=user_id, callout_id=callout.id,
            token_address=callout.token_address, token_symbol=callout.token_symbol,
            side=TradeSide.buy, sol_amount=trade_sol, token_amount=0,
            price_at_execution=callout.price_at_callout, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, error_message="Failed to get Jupiter quote",
        )
        db.add(trade)
        return trade

    swap_result = await jupiter_swap.get_swap_transaction(quote, wallet.public_key)
    if not swap_result or "swapTransaction" not in swap_result:
        trade = CopyTrade(
            user_id=user_id, callout_id=callout.id,
            token_address=callout.token_address, token_symbol=callout.token_symbol,
            side=TradeSide.buy, sol_amount=trade_sol, token_amount=0,
            price_at_execution=callout.price_at_callout, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, jupiter_route=quote,
            error_message="Failed to get swap transaction",
        )
        db.add(trade)
        return trade

    try:
        keypair_bytes = decrypt_private_key(wallet.encrypted_private_key, wallet.encryption_iv)
    except Exception as e:
        logger.error(f"Failed to decrypt wallet key for user {user_id}: {e}")
        trade = CopyTrade(
            user_id=user_id, callout_id=callout.id,
            token_address=callout.token_address, token_symbol=callout.token_symbol,
            side=TradeSide.buy, sol_amount=trade_sol, token_amount=0,
            price_at_execution=callout.price_at_callout, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, error_message="Wallet decryption failed",
        )
        db.add(trade)
        return trade

    tx_signature = await jupiter_swap.execute_swap(swap_result["swapTransaction"], keypair_bytes)

    out_amount = float(quote.get("outAmount", 0))
    token_decimals = quote.get("outputDecimals", 6)
    token_amount = out_amount / (10 ** token_decimals) if token_decimals else out_amount
    price = trade_sol / token_amount if token_amount > 0 else callout.price_at_callout

    if not tx_signature:
        trade = CopyTrade(
            user_id=user_id, callout_id=callout.id,
            token_address=callout.token_address, token_symbol=callout.token_symbol,
            side=TradeSide.buy, sol_amount=trade_sol, token_amount=token_amount,
            price_at_execution=price, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, jupiter_route=quote,
            error_message="Transaction send failed",
        )
        db.add(trade)
        return trade

    trade = CopyTrade(
        user_id=user_id, callout_id=callout.id,
        token_address=callout.token_address, token_symbol=callout.token_symbol,
        side=TradeSide.buy, sol_amount=trade_sol, token_amount=token_amount,
        price_at_execution=price, slippage_bps=config.slippage_bps,
        tx_signature=tx_signature, tx_status=TxStatus.pending, jupiter_route=quote,
    )
    db.add(trade)
    await db.flush()

    confirmed = await jupiter_swap.confirm_transaction(tx_signature)
    trade.tx_status = TxStatus.confirmed if confirmed else TxStatus.failed
    if not confirmed:
        trade.error_message = "Transaction not confirmed"

    logger.info(
        f"Copy trade {'confirmed' if confirmed else 'failed'}: "
        f"{callout.token_symbol} {trade_sol} SOL -> {token_amount} tokens, "
        f"tx={tx_signature}, user={user_id}"
    )
    return trade


async def execute_sell(
    trade: CopyTrade,
    config: CopyTradeConfig,
    db: AsyncSession,
    sell_pct: float = 100.0,
    trigger: SellTrigger = SellTrigger.manual,
) -> Optional[CopyTrade]:
    """Execute a sell trade for an existing position."""
    wallet_result = await db.execute(
        select(TradingWallet).where(TradingWallet.user_id == config.user_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if not wallet:
        return None

    sell_token_amount = trade.token_amount * (sell_pct / 100.0)
    if sell_token_amount <= 0:
        return None

    token_decimals = 6
    if trade.jupiter_route and "outputDecimals" in trade.jupiter_route:
        token_decimals = trade.jupiter_route["outputDecimals"]

    raw_amount = int(sell_token_amount * (10 ** token_decimals))

    quote = await jupiter_swap.get_quote(
        input_mint=trade.token_address, output_mint=SOL_MINT,
        amount_lamports=raw_amount, slippage_bps=config.slippage_bps,
    )
    if not quote:
        sell_trade = CopyTrade(
            user_id=config.user_id, callout_id=trade.callout_id,
            token_address=trade.token_address, token_symbol=trade.token_symbol,
            side=TradeSide.sell, sol_amount=0, token_amount=sell_token_amount,
            price_at_execution=0, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, parent_trade_id=trade.id,
            sell_trigger=trigger, error_message="Failed to get sell quote",
        )
        db.add(sell_trade)
        return sell_trade

    swap_result = await jupiter_swap.get_swap_transaction(quote, wallet.public_key)
    if not swap_result or "swapTransaction" not in swap_result:
        sell_trade = CopyTrade(
            user_id=config.user_id, callout_id=trade.callout_id,
            token_address=trade.token_address, token_symbol=trade.token_symbol,
            side=TradeSide.sell, sol_amount=0, token_amount=sell_token_amount,
            price_at_execution=0, slippage_bps=config.slippage_bps,
            tx_status=TxStatus.failed, parent_trade_id=trade.id,
            sell_trigger=trigger, jupiter_route=quote,
            error_message="Failed to get sell swap transaction",
        )
        db.add(sell_trade)
        return sell_trade

    try:
        keypair_bytes = decrypt_private_key(wallet.encrypted_private_key, wallet.encryption_iv)
    except Exception:
        return None

    tx_signature = await jupiter_swap.execute_swap(swap_result["swapTransaction"], keypair_bytes)

    sol_out = float(quote.get("outAmount", 0)) / LAMPORTS_PER_SOL
    price = sol_out / sell_token_amount if sell_token_amount > 0 else 0
    entry_cost = trade.sol_amount * (sell_pct / 100.0) if trade.sol_amount else 0
    pnl_sol = sol_out - entry_cost if entry_cost else None
    pnl_pct = ((sol_out / entry_cost) - 1) * 100 if entry_cost and entry_cost > 0 else None

    sell_trade = CopyTrade(
        user_id=config.user_id, callout_id=trade.callout_id,
        token_address=trade.token_address, token_symbol=trade.token_symbol,
        side=TradeSide.sell, sol_amount=sol_out, token_amount=sell_token_amount,
        price_at_execution=price, slippage_bps=config.slippage_bps,
        tx_signature=tx_signature,
        tx_status=TxStatus.pending if tx_signature else TxStatus.failed,
        parent_trade_id=trade.id, sell_trigger=trigger, jupiter_route=quote,
        pnl_sol=pnl_sol, pnl_pct=pnl_pct,
        error_message=None if tx_signature else "Transaction send failed",
    )
    db.add(sell_trade)

    if tx_signature:
        await db.flush()
        confirmed = await jupiter_swap.confirm_transaction(tx_signature)
        sell_trade.tx_status = TxStatus.confirmed if confirmed else TxStatus.failed
        if not confirmed:
            sell_trade.error_message = "Transaction not confirmed"

    return sell_trade
