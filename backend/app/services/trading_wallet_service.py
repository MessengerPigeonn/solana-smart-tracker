from __future__ import annotations
import base64
import hashlib
import logging
import os
from typing import Optional, Tuple
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """Derive a 32-byte AES key from the configured encryption key."""
    raw_key = settings.copy_trade_encryption_key
    if not raw_key:
        raise ValueError("copy_trade_encryption_key is not configured")
    if len(raw_key) == 64:
        try:
            return bytes.fromhex(raw_key)
        except ValueError:
            pass
    return hashlib.sha256(raw_key.encode()).digest()


def encrypt_private_key(private_key_bytes: bytes) -> Tuple[str, str]:
    """Encrypt a private key using AES-256-GCM. Returns (encrypted_b64, iv_b64)."""
    key = _get_encryption_key()
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(iv, private_key_bytes, None)
    return base64.b64encode(encrypted).decode(), base64.b64encode(iv).decode()


def decrypt_private_key(encrypted_b64: str, iv_b64: str) -> bytes:
    """Decrypt a private key from AES-256-GCM encrypted form."""
    key = _get_encryption_key()
    encrypted = base64.b64decode(encrypted_b64)
    iv = base64.b64decode(iv_b64)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, encrypted, None)


def generate_wallet() -> dict:
    """Generate a new Solana keypair. Returns dict with public_key, encrypted_private_key, encryption_iv."""
    try:
        from solders.keypair import Keypair

        kp = Keypair()
        pubkey = str(kp.pubkey())
        secret_bytes = bytes(kp)
        encrypted_pk, iv = encrypt_private_key(secret_bytes)
        return {
            "public_key": pubkey,
            "encrypted_private_key": encrypted_pk,
            "encryption_iv": iv,
        }
    except ImportError:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base58

        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes_raw()
        public_bytes = private_key.public_key().public_bytes_raw()
        full_keypair = private_bytes + public_bytes
        pubkey = base58.b58encode(public_bytes).decode()
        encrypted_pk, iv = encrypt_private_key(full_keypair)
        return {
            "public_key": pubkey,
            "encrypted_private_key": encrypted_pk,
            "encryption_iv": iv,
        }


async def get_wallet_balance(pubkey: str) -> Optional[float]:
    """Get SOL balance for a wallet via Helius RPC."""
    helius_rpc = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                helius_rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [pubkey],
                },
            )
            result = resp.json()
            if "error" in result:
                logger.error(f"getBalance error for {pubkey}: {result['error']}")
                return None
            lamports = result.get("result", {}).get("value", 0)
            return lamports / 1_000_000_000
    except Exception as e:
        logger.error(f"Failed to get balance for {pubkey}: {e}")
        return None
