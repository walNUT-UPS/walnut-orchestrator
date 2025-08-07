"""
Encrypted credential storage and management for SSH connections.

Uses SQLCipher encryption to securely store passwords, keys, and other
sensitive authentication data in the secrets table.
"""

import json
import logging
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

from walnut.database.connection import get_db_session
from walnut.database.models import Secret

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Manages encrypted credential storage using additional encryption
    layer on top of SQLCipher for extra security.
    """
    
    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize credential manager.
        
        Args:
            encryption_key: Optional encryption key (auto-generated if None)
        """
        if encryption_key:
            self._fernet = Fernet(encryption_key)
        else:
            # Generate key from environment or create new one
            key = self._get_or_create_encryption_key()
            self._fernet = Fernet(key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for credential storage."""
        # First try environment variable
        key_b64 = os.environ.get('WALNUT_CREDENTIAL_KEY')
        if key_b64:
            try:
                return base64.urlsafe_b64decode(key_b64)
            except Exception as e:
                logger.warning(f"Invalid credential key in environment: {e}")
        
        # Generate new key and warn user
        key = Fernet.generate_key()
        logger.warning(
            "Generated new credential encryption key. "
            f"Set WALNUT_CREDENTIAL_KEY={base64.urlsafe_b64encode(key).decode()} "
            "to persist credentials across restarts."
        )
        return key
    
    def _encrypt_data(self, data: Dict[str, Any]) -> bytes:
        """Encrypt credential data."""
        json_data = json.dumps(data, sort_keys=True)
        return self._fernet.encrypt(json_data.encode('utf-8'))
    
    def _decrypt_data(self, encrypted_data: bytes) -> Dict[str, Any]:
        """Decrypt credential data."""
        decrypted_bytes = self._fernet.decrypt(encrypted_data)
        return json.loads(decrypted_bytes.decode('utf-8'))
    
    async def store_credentials(
        self,
        name: str,
        credentials: Dict[str, Any],
        overwrite: bool = False,
    ) -> int:
        """
        Store encrypted credentials.
        
        Args:
            name: Unique credential name
            credentials: Credential data dictionary
            overwrite: Whether to overwrite existing credentials
            
        Returns:
            Secret record ID
            
        Raises:
            ValueError: If credentials already exist and overwrite=False
        """
        async with get_db_session() as session:
            # Check if credentials already exist
            existing = await session.get(Secret, {'name': name})
            if existing and not overwrite:
                raise ValueError(f"Credentials '{name}' already exist")
            
            # Encrypt credential data
            encrypted_data = self._encrypt_data(credentials)
            
            if existing:
                # Update existing
                existing.encrypted_data = encrypted_data
                await session.commit()
                logger.info(f"Updated credentials: {name}")
                return existing.id
            else:
                # Create new
                secret = Secret(
                    name=name,
                    encrypted_data=encrypted_data,
                )
                session.add(secret)
                await session.commit()
                logger.info(f"Stored new credentials: {name}")
                return secret.id
    
    async def get_credentials(self, secret_id: int) -> Dict[str, Any]:
        """
        Retrieve and decrypt credentials by ID.
        
        Args:
            secret_id: Secret record ID
            
        Returns:
            Decrypted credential data
            
        Raises:
            ValueError: If secret not found
        """
        async with get_db_session() as session:
            secret = await session.get(Secret, secret_id)
            if not secret:
                raise ValueError(f"Secret with ID {secret_id} not found")
            
            try:
                return self._decrypt_data(secret.encrypted_data)
            except Exception as e:
                logger.error(f"Failed to decrypt credentials {secret_id}: {e}")
                raise ValueError(f"Failed to decrypt credentials: {e}")
    
    async def get_credentials_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve and decrypt credentials by name.
        
        Args:
            name: Credential name
            
        Returns:
            Decrypted credential data or None if not found
        """
        from sqlalchemy import select
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Secret).where(Secret.name == name)
            )
            secret = result.scalar_one_or_none()
            
            if not secret:
                return None
            
            try:
                return self._decrypt_data(secret.encrypted_data)
            except Exception as e:
                logger.error(f"Failed to decrypt credentials '{name}': {e}")
                return None
    
    async def list_credentials(self) -> Dict[str, int]:
        """
        List all stored credential names and their IDs.
        
        Returns:
            Dictionary mapping credential names to IDs
        """
        from sqlalchemy import select
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Secret.name, Secret.id).order_by(Secret.name)
            )
            return {name: secret_id for name, secret_id in result.fetchall()}
    
    async def delete_credentials(self, name: str) -> bool:
        """
        Delete stored credentials.
        
        Args:
            name: Credential name
            
        Returns:
            True if deleted, False if not found
        """
        from sqlalchemy import select
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Secret).where(Secret.name == name)
            )
            secret = result.scalar_one_or_none()
            
            if not secret:
                return False
            
            await session.delete(secret)
            await session.commit()
            logger.info(f"Deleted credentials: {name}")
            return True
    
    async def store_ssh_key_credentials(
        self,
        name: str,
        username: str,
        private_key_path: Optional[str] = None,
        private_key_data: Optional[str] = None,
        passphrase: Optional[str] = None,
        overwrite: bool = False,
    ) -> int:
        """
        Store SSH key-based credentials.
        
        Args:
            name: Credential name
            username: SSH username
            private_key_path: Path to private key file
            private_key_data: Private key data as string
            passphrase: Key passphrase (if encrypted)
            overwrite: Whether to overwrite existing credentials
            
        Returns:
            Secret record ID
        """
        credentials = {
            'type': 'ssh_key',
            'username': username,
        }
        
        if private_key_path:
            credentials['private_key_path'] = private_key_path
        
        if private_key_data:
            credentials['private_key'] = private_key_data
        
        if passphrase:
            credentials['passphrase'] = passphrase
        
        return await self.store_credentials(name, credentials, overwrite)
    
    async def store_ssh_password_credentials(
        self,
        name: str,
        username: str,
        password: str,
        overwrite: bool = False,
    ) -> int:
        """
        Store SSH password-based credentials.
        
        Args:
            name: Credential name
            username: SSH username
            password: SSH password
            overwrite: Whether to overwrite existing credentials
            
        Returns:
            Secret record ID
        """
        credentials = {
            'type': 'ssh_password',
            'username': username,
            'password': password,
        }
        
        return await self.store_credentials(name, credentials, overwrite)


# Utility functions for common credential operations

async def create_ssh_key_secret(
    name: str,
    username: str,
    private_key_path: Optional[str] = None,
    private_key_data: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> int:
    """
    Create SSH key credentials.
    
    Args:
        name: Unique credential name
        username: SSH username  
        private_key_path: Path to private key file
        private_key_data: Private key content
        passphrase: Key passphrase if needed
        
    Returns:
        Secret ID
    """
    manager = CredentialManager()
    return await manager.store_ssh_key_credentials(
        name=name,
        username=username,
        private_key_path=private_key_path,
        private_key_data=private_key_data,
        passphrase=passphrase,
    )


async def create_ssh_password_secret(
    name: str,
    username: str,
    password: str,
) -> int:
    """
    Create SSH password credentials.
    
    Args:
        name: Unique credential name
        username: SSH username
        password: SSH password
        
    Returns:
        Secret ID
    """
    manager = CredentialManager()
    return await manager.store_ssh_password_credentials(
        name=name,
        username=username,
        password=password,
    )


async def get_ssh_credentials(secret_id: int) -> Dict[str, Any]:
    """
    Get SSH credentials by ID.
    
    Args:
        secret_id: Secret record ID
        
    Returns:
        Credential data
    """
    manager = CredentialManager()
    return await manager.get_credentials(secret_id)