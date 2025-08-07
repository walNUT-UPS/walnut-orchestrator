"""
Host management and discovery for coordinated shutdown operations.

Provides host registration, configuration, health checking, and 
automatic discovery of systems that can be managed during power events.
"""

import asyncio
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from walnut.database.connection import get_db_session
from walnut.database.models import Host, create_host, create_event
from walnut.ssh.client import SSHClient, SSHConnectionConfig
from walnut.ssh.credentials import CredentialManager

logger = logging.getLogger(__name__)


class HostManager:
    """
    Manages host configurations and SSH connections for shutdown operations.
    
    Provides centralized management of hosts that can be shut down during
    power events, with health monitoring and connection testing.
    """
    
    def __init__(self, ssh_client: Optional[SSHClient] = None):
        self.ssh_client = ssh_client or SSHClient()
        self.credential_manager = CredentialManager()
    
    async def add_host(
        self,
        hostname: str,
        ip_address: Optional[str] = None,
        os_type: Optional[str] = None,
        connection_type: str = "ssh",
        credentials_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        private_key_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        port: int = 22,
    ) -> Host:
        """
        Add a new managed host.
        
        Args:
            hostname: Host name or identifier
            ip_address: IP address (resolved from hostname if None)
            os_type: Operating system type
            connection_type: Connection method (ssh, winrm, etc.)
            credentials_name: Name for stored credentials
            username: SSH username
            password: SSH password (if using password auth)
            private_key_path: Path to SSH private key
            metadata: Additional host metadata
            port: SSH port number
            
        Returns:
            Created Host instance
            
        Raises:
            ValueError: If host configuration is invalid
        """
        # Resolve IP address if not provided
        if not ip_address:
            try:
                ip_address = socket.gethostbyname(hostname)
                logger.debug(f"Resolved {hostname} to {ip_address}")
            except socket.gaierror:
                logger.warning(f"Could not resolve hostname: {hostname}")
        
        # Store credentials if provided
        credentials_ref = None
        if username and (password or private_key_path):
            if not credentials_name:
                credentials_name = f"{hostname}_ssh_credentials"
            
            try:
                if password:
                    credentials_ref = await self.credential_manager.store_ssh_password_credentials(
                        name=credentials_name,
                        username=username,
                        password=password,
                        overwrite=True,
                    )
                elif private_key_path:
                    credentials_ref = await self.credential_manager.store_ssh_key_credentials(
                        name=credentials_name,
                        username=username,
                        private_key_path=private_key_path,
                        overwrite=True,
                    )
                logger.info(f"Stored credentials for {hostname} as {credentials_name}")
            except Exception as e:
                logger.error(f"Failed to store credentials for {hostname}: {e}")
                raise ValueError(f"Failed to store credentials: {e}")
        
        # Create host metadata with port info
        host_metadata = metadata or {}
        host_metadata.update({
            'ssh_port': port,
            'added_by': 'host_manager',
            'version': '1.0',
        })
        
        # Create host record
        async with get_db_session() as session:
            try:
                host = create_host(
                    hostname=hostname,
                    ip_address=ip_address,
                    os_type=os_type,
                    connection_type=connection_type,
                    credentials_ref=credentials_ref,
                    metadata=host_metadata,
                )
                
                session.add(host)
                await session.commit()
                await session.refresh(host)
                
                logger.info(f"Added host: {hostname} ({ip_address})")
                
                # Log event
                event = create_event(
                    event_type="HOST_ADDED",
                    description=f"Added host {hostname} for shutdown management",
                    severity="INFO",
                    metadata={
                        'hostname': hostname,
                        'ip_address': ip_address,
                        'connection_type': connection_type,
                    }
                )
                session.add(event)
                await session.commit()
                
                return host
                
            except IntegrityError as e:
                await session.rollback()
                raise ValueError(f"Host {hostname} already exists or invalid configuration")
    
    async def get_host_by_name(self, hostname: str) -> Optional[Host]:
        """Get host by hostname."""
        async with get_db_session() as session:
            result = await session.execute(
                select(Host).where(Host.hostname == hostname)
            )
            return result.scalar_one_or_none()
    
    async def get_host_by_id(self, host_id: int) -> Optional[Host]:
        """Get host by ID."""
        async with get_db_session() as session:
            return await session.get(Host, host_id)
    
    async def list_hosts(
        self,
        connection_type: Optional[str] = None,
        os_type: Optional[str] = None,
    ) -> List[Host]:
        """
        List all managed hosts with optional filtering.
        
        Args:
            connection_type: Filter by connection type
            os_type: Filter by OS type
            
        Returns:
            List of Host instances
        """
        async with get_db_session() as session:
            query = select(Host).order_by(Host.hostname)
            
            if connection_type:
                query = query.where(Host.connection_type == connection_type)
            
            if os_type:
                query = query.where(Host.os_type == os_type)
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def remove_host(self, hostname: str) -> bool:
        """
        Remove a managed host.
        
        Args:
            hostname: Host name to remove
            
        Returns:
            True if removed, False if not found
        """
        async with get_db_session() as session:
            # Get host first
            result = await session.execute(
                select(Host).where(Host.hostname == hostname)
            )
            host = result.scalar_one_or_none()
            
            if not host:
                return False
            
            # Clean up credentials if they exist
            if host.credentials_ref:
                try:
                    # Note: We don't automatically delete credentials as they might be shared
                    logger.info(f"Host {hostname} has credentials_ref {host.credentials_ref}")
                except Exception as e:
                    logger.warning(f"Could not check credentials for {hostname}: {e}")
            
            # Delete host
            await session.delete(host)
            await session.commit()
            
            logger.info(f"Removed host: {hostname}")
            
            # Log event
            event = create_event(
                event_type="HOST_REMOVED",
                description=f"Removed host {hostname} from shutdown management",
                severity="INFO",
                metadata={'hostname': hostname}
            )
            session.add(event)
            await session.commit()
            
            return True
    
    async def test_host_connection(self, hostname: str) -> Dict[str, Any]:
        """
        Test SSH connection to a host.
        
        Args:
            hostname: Host name to test
            
        Returns:
            Connection test results
        """
        host = await self.get_host_by_name(hostname)
        if not host:
            return {
                'success': False,
                'error': f"Host {hostname} not found",
                'hostname': hostname,
            }
        
        try:
            # Create SSH connection config
            config = await self.ssh_client.connect_to_host(host)
            
            # Test connection
            success = await self.ssh_client.test_connection(config)
            
            result = {
                'success': success,
                'hostname': hostname,
                'ip_address': host.ip_address,
                'connection_type': host.connection_type,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
            if success:
                # Get additional host info
                try:
                    host_info = await self.ssh_client.get_host_info(config)
                    result['host_info'] = host_info
                except Exception as e:
                    logger.debug(f"Could not get host info for {hostname}: {e}")
                    result['host_info_error'] = str(e)
            
            return result
            
        except Exception as e:
            logger.error(f"Connection test failed for {hostname}: {e}")
            return {
                'success': False,
                'error': str(e),
                'hostname': hostname,
                'ip_address': host.ip_address if host else None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
    
    async def health_check_all_hosts(self) -> Dict[str, Any]:
        """
        Run health checks on all managed hosts.
        
        Returns:
            Summary of health check results
        """
        hosts = await self.list_hosts(connection_type="ssh")
        
        if not hosts:
            return {
                'total_hosts': 0,
                'healthy_hosts': 0,
                'failed_hosts': 0,
                'results': [],
            }
        
        # Run tests concurrently
        tasks = [self.test_host_connection(host.hostname) for host in hosts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        healthy_count = 0
        failed_count = 0
        processed_results = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'hostname': hosts[i].hostname,
                    'success': False,
                    'error': str(result),
                    'exception': True,
                })
                failed_count += 1
            else:
                processed_results.append(result)
                if result.get('success', False):
                    healthy_count += 1
                else:
                    failed_count += 1
        
        return {
            'total_hosts': len(hosts),
            'healthy_hosts': healthy_count,
            'failed_hosts': failed_count,
            'results': processed_results,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    async def update_host_metadata(
        self,
        hostname: str,
        metadata: Dict[str, Any],
        merge: bool = True,
    ) -> bool:
        """
        Update host metadata.
        
        Args:
            hostname: Host name
            metadata: Metadata to update
            merge: Whether to merge with existing metadata
            
        Returns:
            True if updated, False if host not found
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Host).where(Host.hostname == hostname)
            )
            host = result.scalar_one_or_none()
            
            if not host:
                return False
            
            if merge and host.host_metadata:
                # Merge with existing metadata
                updated_metadata = host.host_metadata.copy()
                updated_metadata.update(metadata)
            else:
                # Replace metadata
                updated_metadata = metadata
            
            # Update timestamp
            updated_metadata['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Update host
            host.host_metadata = updated_metadata
            await session.commit()
            
            logger.info(f"Updated metadata for host {hostname}")
            return True


class HostDiscovery:
    """
    Automatic host discovery for SSH-accessible systems.
    
    Scans network ranges and tests common credentials to find
    hosts that can be managed for shutdown operations.
    """
    
    def __init__(self, host_manager: Optional[HostManager] = None):
        self.host_manager = host_manager or HostManager()
    
    def _generate_ip_range(self, network: str) -> List[str]:
        """Generate IP addresses from network CIDR or range."""
        # Simple implementation for common cases
        # For production, consider using ipaddress module
        
        if '/' in network:
            # CIDR notation (basic implementation)
            base_ip = network.split('/')[0]
            octets = base_ip.split('.')
            if len(octets) == 4:
                # Generate /24 range for simplicity
                base = '.'.join(octets[:3])
                return [f"{base}.{i}" for i in range(1, 255)]
        
        elif '-' in network:
            # Range notation like 192.168.1.1-254
            if '.' in network:
                parts = network.split('.')
                if len(parts) == 4 and '-' in parts[-1]:
                    start, end = parts[-1].split('-')
                    base = '.'.join(parts[:3])
                    return [f"{base}.{i}" for i in range(int(start), int(end) + 1)]
        
        # Single IP
        return [network]
    
    async def scan_network(
        self,
        network: str,
        port: int = 22,
        timeout: int = 5,
        max_concurrent: int = 50,
    ) -> List[str]:
        """
        Scan network for SSH-accessible hosts.
        
        Args:
            network: Network range (CIDR, range, or single IP)
            port: SSH port to test
            timeout: Connection timeout
            max_concurrent: Maximum concurrent connections
            
        Returns:
            List of accessible IP addresses
        """
        ip_list = self._generate_ip_range(network)
        logger.info(f"Scanning {len(ip_list)} addresses for SSH access")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def test_ssh_port(ip: str) -> Optional[str]:
            async with semaphore:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port),
                        timeout=timeout
                    )
                    writer.close()
                    await writer.wait_closed()
                    return ip
                except Exception:
                    return None
        
        # Run concurrent port scans
        tasks = [test_ssh_port(ip) for ip in ip_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful connections
        accessible_hosts = [
            result for result in results 
            if isinstance(result, str) and result is not None
        ]
        
        logger.info(f"Found {len(accessible_hosts)} SSH-accessible hosts")
        return accessible_hosts
    
    async def discover_host_info(
        self,
        ip_address: str,
        username: str = "root",
        common_keys: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Discover information about a host using common credentials.
        
        Args:
            ip_address: IP address to probe
            username: Username to try
            common_keys: List of common SSH key paths to try
            
        Returns:
            Host information if accessible, None otherwise
        """
        if not common_keys:
            common_keys = [
                "~/.ssh/id_rsa",
                "~/.ssh/id_ed25519",
                "~/.ssh/id_ecdsa",
            ]
        
        # Try key-based authentication
        for key_path in common_keys:
            try:
                config = SSHConnectionConfig(
                    hostname=ip_address,
                    username=username,
                    private_key_path=key_path,
                    connect_timeout=10,
                    command_timeout=10,
                )
                
                success = await self.host_manager.ssh_client.test_connection(config)
                if success:
                    # Get host information
                    host_info = await self.host_manager.ssh_client.get_host_info(config)
                    
                    return {
                        'ip_address': ip_address,
                        'username': username,
                        'key_path': key_path,
                        'accessible': True,
                        'host_info': host_info,
                    }
            
            except Exception as e:
                logger.debug(f"Key {key_path} failed for {ip_address}: {e}")
                continue
        
        return None
    
    async def auto_discover(
        self,
        network: str,
        add_discovered: bool = False,
        username: str = "root",
    ) -> List[Dict[str, Any]]:
        """
        Automatically discover and optionally add SSH-accessible hosts.
        
        Args:
            network: Network range to scan
            add_discovered: Whether to automatically add discovered hosts
            username: Username to use for discovery
            
        Returns:
            List of discovered host information
        """
        logger.info(f"Starting host discovery on network: {network}")
        
        # Step 1: Port scan
        accessible_ips = await self.scan_network(network)
        
        if not accessible_ips:
            logger.info("No SSH-accessible hosts found")
            return []
        
        # Step 2: Credential testing
        discovery_tasks = [
            self.discover_host_info(ip, username) 
            for ip in accessible_ips
        ]
        discovery_results = await asyncio.gather(*discovery_tasks, return_exceptions=True)
        
        # Process results
        discovered_hosts = []
        for result in discovery_results:
            if isinstance(result, dict) and result.get('accessible'):
                discovered_hosts.append(result)
        
        logger.info(f"Successfully discovered {len(discovered_hosts)} accessible hosts")
        
        # Step 3: Add to management (if requested)
        if add_discovered:
            for host_info in discovered_hosts:
                try:
                    hostname = host_info.get('host_info', {}).get('hostname', host_info['ip_address'])
                    
                    await self.host_manager.add_host(
                        hostname=hostname.strip(),
                        ip_address=host_info['ip_address'],
                        username=host_info['username'],
                        private_key_path=host_info['key_path'],
                        metadata={
                            'discovered': True,
                            'discovery_method': 'auto_scan',
                            'discovery_timestamp': datetime.now(timezone.utc).isoformat(),
                            'host_info': host_info.get('host_info', {}),
                        }
                    )
                    logger.info(f"Added discovered host: {hostname}")
                    
                except Exception as e:
                    logger.error(f"Failed to add discovered host {host_info['ip_address']}: {e}")
        
        return discovered_hosts