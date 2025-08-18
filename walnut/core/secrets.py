"""
Manages field-level encryption for integration secrets.

This module provides a secure way to store and retrieve sensitive data
for integration instances, such as API keys, passwords, and tokens.
It uses Fernet symmetric encryption from the cryptography library.
"""

import base64
import hashlib
from typing import Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from walnut.config import get_master_key
from walnut.database.models import IntegrationSecret


class SecretEncryptor:
    """Handles encryption and decryption of secret values."""

    def __init__(self, master_key: str):
        if not master_key or len(master_key) < 32:
            raise ValueError("Master key must be at least 32 characters long.")
        self.master_key = master_key.encode("utf-8")
        self.fernet = self._derive_key()

    def _derive_key(self) -> Fernet:
        """Derives a 32-byte encryption key from the master key using a fixed salt."""
        salt = b'walnut-secret-salt'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypts a plaintext string."""
        return self.fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, encrypted_value: bytes) -> str:
        """Decrypts an encrypted value."""
        return self.fernet.decrypt(encrypted_value).decode("utf-8")

# Global encryptor instance, initialized on startup
try:
    encryptor = SecretEncryptor(get_master_key())
except ValueError as e:
    print(f"FATAL: SecretEncryptor could not be initialized: {e}")
    encryptor = None


async def create_or_update_secret(
    db: AsyncSession,
    instance_id: int,
    field_name: str,
    secret_type: str,
    value: str
) -> IntegrationSecret:
    """
    Creates a new secret or updates an existing one for an integration instance.
    """
    if not encryptor:
        raise RuntimeError("SecretEncryptor is not initialized.")

    encrypted_value = encryptor.encrypt(value)

    stmt = select(IntegrationSecret).where(
        IntegrationSecret.instance_id == instance_id,
        IntegrationSecret.field_name == field_name
    )
    secret = (await db.execute(stmt)).scalars().first()

    if secret:
        secret.encrypted_value = encrypted_value
        secret.secret_type = secret_type
    else:
        secret = IntegrationSecret(
            instance_id=instance_id,
            field_name=field_name,
            secret_type=secret_type,
            encrypted_value=encrypted_value
        )
        db.add(secret)

    await db.commit()
    await db.refresh(secret)
    return secret


async def get_all_secrets_for_instance(db: AsyncSession, instance_id: int) -> Dict[str, str]:
    """Retrieves and decrypts all secrets for a given instance."""
    if not encryptor:
        raise RuntimeError("SecretEncryptor is not initialized.")

    stmt = select(IntegrationSecret).where(IntegrationSecret.instance_id == instance_id)
    secrets = (await db.execute(stmt)).scalars().all()

    decrypted_secrets = {}
    for secret in secrets:
        decrypted_secrets[secret.field_name] = encryptor.decrypt(secret.encrypted_value)

    return decrypted_secrets


async def delete_secret(db: AsyncSession, instance_id: int, field_name: str) -> bool:
    """Deletes a secret from the database."""
    stmt = delete(IntegrationSecret).where(
        IntegrationSecret.instance_id == instance_id,
        IntegrationSecret.field_name == field_name
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0
