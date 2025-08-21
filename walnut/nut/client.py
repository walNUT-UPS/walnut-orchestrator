"""
NUT (Network UPS Tools) client wrapper.

This module provides an asynchronous client for interacting with a NUT server,
using the synchronous python-nut2 library. It uses asyncio.to_thread to run
blocking I/O operations in a separate thread.
"""

import asyncio
import logging
from typing import Any, Dict

from pynut2.nut2 import PyNUTClient

from ..config import settings

logger = logging.getLogger(__name__)


class NUTError(Exception):
    """Base exception for NUT client errors."""
    pass


class NUTConnectionError(NUTError):
    """Exception for NUT connection errors."""
    pass


class NUTClient:
    """
    An asynchronous client for NUT servers.
    """

    def __init__(
        self,
        host: str = settings.NUT_HOST,
        port: int = settings.NUT_PORT,
        username: str | None = settings.NUT_USERNAME,
        password: str | None = settings.NUT_PASSWORD,
    ):
        """
        Initialize the NUT client.

        Args:
            host: The NUT server hostname or IP address.
            port: The NUT server port.
            username: The username for authentication.
            password: The password for authentication.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._client = PyNUTClient(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password
        )
        logger.info("Initialized NUT client host=%s port=%s user=%s", self.host, self.port, bool(self.username))

    async def list_ups(self) -> Dict[str, str]:
        """
        List the available UPS devices on the NUT server.

        Returns:
            A dictionary of UPS devices, where the key is the UPS name and
            the value is the UPS description.

        Raises:
            NUTConnectionError: If there is an error communicating with the server.
        """
        try:
            logger.debug("Listing UPS devices from %s:%s", self.host, self.port)
            data = await asyncio.to_thread(self._client.list_ups)
            logger.info("NUT list_ups ok: %d devices", len(data) if data else 0)
            return data
        except Exception as e:
            raise NUTConnectionError(f"Failed to list UPS devices from {self.host}:{self.port}") from e

    async def get_vars(self, ups_name: str) -> Dict[str, Any]:
        """
        Get all variables for a specific UPS.

        Args:
            ups_name: The name of the UPS device.

        Returns:
            A dictionary of variables for the specified UPS.

        Raises:
            NUTConnectionError: If there is an error communicating with the server.
        """
        try:
            logger.debug("Fetching vars for UPS '%s'", ups_name)
            vars_ = await asyncio.to_thread(self._client.get_vars, ups_name)
            logger.info("NUT get_vars ok for '%s' (%d vars)", ups_name, len(vars_) if vars_ else 0)
            return vars_
        except Exception as e:
            raise NUTConnectionError(f"Failed to get variables for UPS '{ups_name}'") from e

    async def get_var(self, ups_name: str, var: str) -> Any:
        """
        Get a single variable for a specific UPS.

        Args:
            ups_name: The name of the UPS device.
            var: The name of the variable to fetch.

        Returns:
            The value of the specified variable.

        Raises:
            NUTConnectionError: If there is an error communicating with the server.
        """
        try:
            logger.debug("Fetching var '%s' for UPS '%s'", var, ups_name)
            value = await asyncio.to_thread(self._client.get_var, ups_name, var)
            logger.info("NUT get_var ok '%s' for '%s'", var, ups_name)
            return value
        except Exception as e:
            raise NUTConnectionError(f"Failed to get variable '{var}' for UPS '{ups_name}'") from e
