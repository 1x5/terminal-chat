import asyncio
import random
import socket
import struct
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import logging
import time

logger = logging.getLogger(__name__)

@dataclass
class PeerInfo:
    node_id: str
    address: str
    port: int
    public_key: str
    last_seen: float
    services: Set[str] = None

class PeerDiscovery:
    def __init__(self, node_id: str, port: int, bootstrap_nodes: List[Tuple[str, int]] = None):
        self.node_id = node_id
        self.port = port
        self.bootstrap_nodes = bootstrap_nodes or []
        self.known_peers: Dict[str, PeerInfo] = {}
        self.active_peers: Set[str] = set()
        self.discovery_task: Optional[asyncio.Task] = None
        self.running = False
        
    async def start(self):
        """Start the peer discovery service"""
        if self.running:
            return
            
        self.running = True
        self.discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("Peer discovery service started")
        
    async def stop(self):
        """Останавливает процесс обнаружения пиров"""
        if not self.running:
            return
            
        self.running = False
        
        # Отменяем задачу обнаружения
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
            finally:
                self.discovery_task = None
                
        logger.info("Система обнаружения пиров остановлена")
        
    async def _discovery_loop(self):
        """Main discovery loop"""
        while self.running:
            try:
                # Bootstrap if we have no peers
                if not self.known_peers:
                    await self._bootstrap()
                    
                # Discover new peers
                await self._discover_peers()
                
                # Clean up inactive peers
                await self._cleanup_peers()
                
                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5)  # Wait before retry
                
    async def _bootstrap(self):
        """Connect to bootstrap nodes to get initial peers"""
        for address, port in self.bootstrap_nodes:
            try:
                # Create UDP socket for bootstrap
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                
                # Send discovery request
                message = struct.pack("!20s", self.node_id.encode())
                sock.sendto(message, (address, port))
                
                # Wait for response
                data, addr = sock.recvfrom(1024)
                self._process_peer_response(data, addr)
                
            except Exception as e:
                logger.error(f"Bootstrap failed for {address}:{port}: {e}")
            finally:
                sock.close()
                
    async def _discover_peers(self):
        """Discover new peers from known peers"""
        # Select random subset of known peers
        sample_size = min(5, len(self.known_peers))
        sample_peers = random.sample(list(self.known_peers.values()), sample_size)
        
        for peer in sample_peers:
            try:
                # Create UDP socket for discovery
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                
                # Send discovery request
                message = struct.pack("!20s", self.node_id.encode())
                sock.sendto(message, (peer.address, peer.port))
                
                # Wait for response
                data, addr = sock.recvfrom(1024)
                self._process_peer_response(data, addr)
                
            except Exception as e:
                logger.error(f"Discovery failed for {peer.address}:{peer.port}: {e}")
            finally:
                sock.close()
                
    def _process_peer_response(self, data: bytes, addr: Tuple[str, int]):
        """Process peer discovery response"""
        try:
            # Parse peer information from response
            # Format: node_id(20) + public_key(32) + services(4) + port(2)
            node_id = data[:20].hex()
            public_key = data[20:52].hex()
            services = struct.unpack("!I", data[52:56])[0]
            port = struct.unpack("!H", data[56:58])[0]
            
            # Create peer info
            peer = PeerInfo(
                node_id=node_id,
                address=addr[0],
                port=port,
                public_key=public_key,
                last_seen=time.time(),
                services=set()
            )
            
            # Add services based on flags
            if services & 0x01:
                peer.services.add("chat")
            if services & 0x02:
                peer.services.add("storage")
            if services & 0x04:
                peer.services.add("relay")
                
            # Update known peers
            self.known_peers[node_id] = peer
            self.active_peers.add(node_id)
            
        except Exception as e:
            logger.error(f"Error processing peer response: {e}")
            
    async def _cleanup_peers(self):
        """Remove inactive peers"""
        current_time = time.time()
        inactive_peers = [
            node_id for node_id, peer in self.known_peers.items()
            if current_time - peer.last_seen > 3600  # 1 hour timeout
        ]
        
        for node_id in inactive_peers:
            del self.known_peers[node_id]
            self.active_peers.discard(node_id)
            
    def get_peers(self, service: Optional[str] = None) -> List[PeerInfo]:
        """Get list of known peers, optionally filtered by service"""
        if service:
            return [
                peer for peer in self.known_peers.values()
                if service in peer.services
            ]
        return list(self.known_peers.values())
        
    def add_peer(self, peer: PeerInfo) -> bool:
        """Add a new peer manually"""
        try:
            self.known_peers[peer.node_id] = peer
            self.active_peers.add(peer.node_id)
            return True
        except Exception as e:
            logger.error(f"Error adding peer: {e}")
            return False
            
    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer"""
        try:
            if node_id in self.known_peers:
                del self.known_peers[node_id]
                self.active_peers.discard(node_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing peer: {e}")
            return False 