"""
SSH module for walNUT UPS Management Platform.

Provides secure SSH connections for remote host management and shutdown operations.
"""

from walnut.ssh.client import SSHClient
from walnut.ssh.credentials import CredentialManager

__all__ = ["SSHClient", "CredentialManager"]