"""
Тесты для луковой маршрутизации
"""
import pytest
import asyncio
from src.crypto import CryptoManager, generate_onion_layers, wrap_in_onion_layers, unwrap_onion_layer
from src.network import P2PNetwork
from src.config import Config
import pytest_asyncio
import json
import nacl
import base64
import logging
from nacl.public import PublicKey
from nacl.public import PrivateKey
from nacl.public import Box

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Also set debug level for other loggers
logging.getLogger("securetermchat.crypto").setLevel(logging.DEBUG)
logging.getLogger("securetermchat.network").setLevel(logging.DEBUG)

@pytest_asyncio.fixture
async def onion_network():
    """Create a network of nodes for onion routing testing."""
    # Create 3 nodes for testing onion routing
    configs = []
    networks = []
    cryptos = []
    
    for i in range(3):
        config = Config()
        config.port = 8001 + i
        config.peer_discovery_port = 7001 + i
        configs.append(config)
        
        crypto = CryptoManager()
        cryptos.append(crypto)
        
        network = P2PNetwork(config, crypto)
        networks.append(network)
        await network.start()
        logger.info(f"Started network node {i} on port {config.port}")
    
    # Connect nodes in a chain: 2 -> 1 -> 0
    for i in range(2):
        remote_port = configs[i].port
        remote_address = f"ws://localhost:{remote_port}"
        logger.info(f"Connecting node {i+1} to {remote_address}")
        await networks[i+1].connect(remote_address)
        logger.info(f"Connected node {i+1} to node {i}")
        
        # Wait for connection to establish
        await asyncio.sleep(0.1)
        
        # Verify connection
        assert len(networks[i+1].connections) > 0, f"Node {i+1} has no connections"
        assert len(networks[i].connections) > 0, f"Node {i} has no connections"
    
    yield networks
    
    # Cleanup
    for network in networks:
        await network.stop()

@pytest.mark.asyncio
async def test_onion_layers_generation():
    """Test generation of onion layers."""
    layers = generate_onion_layers(3)
    
    assert len(layers) == 3
    for i in range(3):
        assert f"hop_{i}" in layers
        assert "private_key" in layers[f"hop_{i}"]
        assert "public_key" in layers[f"hop_{i}"]

@pytest.mark.asyncio
async def test_onion_message_wrapping():
    """Test wrapping a message in onion layers."""
    # Generate layers
    layers = generate_onion_layers(3)
    
    # Create a test message
    message = {
        "type": "chat",
        "content": "Hello, onion world!",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    
    # Get public keys in forward order (from first hop to last)
    route_public_keys = [layers[f"hop_{i}"]["public_key"] for i in range(3)]
    
    # Wrap message
    wrapped = wrap_in_onion_layers(message, route_public_keys)
    
    assert "nonce" in wrapped
    assert "ciphertext" in wrapped
    assert "ephemeral_pubkey" in wrapped

@pytest.mark.asyncio
async def test_onion_message_unwrapping():
    """Test unwrapping a message from onion layers."""
    # Generate layers
    layers = generate_onion_layers(3)
    
    # Create a test message
    message = {
        "type": "chat",
        "content": "Hello, onion world!",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    
    # Get public keys in forward order (from first hop to last)
    route_public_keys = [layers[f"hop_{i}"]["public_key"] for i in range(3)]
    logger.info(f"Route public keys (forward order): {route_public_keys}")
    
    # Wrap message
    wrapped = wrap_in_onion_layers(message, route_public_keys)
    logger.info(f"Wrapped message: {wrapped}")
    
    # Unwrap at each hop (in forward order)
    current_layer = wrapped
    for i in range(3):
        private_key_str = layers[f"hop_{i}"]["private_key"]
        private_key = PrivateKey(base64.b64decode(private_key_str))
        logger.info(f"Unwrapping layer {i} with private key: {base64.b64encode(private_key.encode()).decode()}")
        current_layer = unwrap_onion_layer(current_layer, private_key)
        logger.info(f"Unwrapped layer {i}: {current_layer}")
        
        if i < 2:  # Not the final hop
            assert "nonce" in current_layer
            assert "ciphertext" in current_layer
            assert "ephemeral_pubkey" in current_layer
        else:  # Final hop
            assert current_layer == message

@pytest.mark.asyncio
async def test_onion_routing_through_network(onion_network):
    """Test sending a message through onion routing network."""
    networks = onion_network
    messages = []
    
    async def on_message(conn, msg):
        logger.info(f"Message handler called with message (len={len(msg)}): {msg[:200]}...")
        try:
            # Parse as JSON
            data = json.loads(msg)
            logger.info(f"Parsed message as JSON: {data}")
            if isinstance(data, dict):
                if data.get("type") == "onion":
                    # Unwrap onion layer
                    logger.info("Unwrapping onion layer")
                    network = next(n for n in networks if any(c == conn for c in n.connections))
                    logger.info(f"Found network for connection: port={network.config.port}")
                    
                    # Get the payload from the message
                    payload = data["payload"]
                    logger.info(f"Processing payload: {payload}")
                    logger.info(f"Network private key (len={len(network.crypto.private_key.encode())}): {base64.b64encode(network.crypto.private_key.encode()).decode()}")
                    logger.info(f"Network public key (len={len(network.crypto.private_key.public_key.encode())}): {base64.b64encode(network.crypto.private_key.public_key.encode()).decode()}")
                    
                    # Unwrap the layer using the network's private key
                    try:
                        unwrapped = unwrap_onion_layer(payload, network.crypto.private_key)
                        logger.info(f"Unwrapped layer: {unwrapped}")
                        
                        # If this is a chat message
                        if isinstance(unwrapped, dict) and unwrapped.get("type") == "chat":
                            logger.info(f"Found chat message: {unwrapped}")
                            messages.append(unwrapped)
                        elif isinstance(unwrapped, dict) and "ciphertext" in unwrapped:
                            # Forward to next hop
                            next_hop = None
                            for n in networks:
                                if n != network and any(c.remote_address.endswith(str(n.config.port)) for c in network.connections):
                                    next_hop = n
                                    break
                                    
                            if next_hop:
                                logger.info(f"Forwarding to next hop: port={next_hop.config.port}")
                                next_message = {
                                    "type": "onion",
                                    "circuit_id": data["circuit_id"],
                                    "payload": unwrapped
                                }
                                # Send to first connection of next hop
                                if next_hop.connections:
                                    next_msg = json.dumps(next_message)
                                    logger.info(f"Sending message to next hop (len={len(next_msg)}): {next_msg[:200]}...")
                                    await next_hop.send_message(
                                        next_hop.connections[0].remote_address,
                                        next_msg
                                    )
                    except Exception as e:
                        logger.error(f"Error unwrapping layer: {e}")
                        raise
                else:
                    # Regular message
                    logger.info(f"Adding regular message to list: {data}")
                    messages.append(data)
        except json.JSONDecodeError:
            # Try to decrypt as raw message
            logger.info("Trying to decrypt as raw message")
            network = next(n for n in networks if any(c == conn for c in n.connections))
            try:
                decrypted = network.crypto.decrypt(msg)
                logger.info(f"Decrypted message: {decrypted}")
                data = json.loads(decrypted)
                logger.info(f"Adding decrypted message to list: {data}")
                messages.append(data)
            except Exception as e:
                logger.warning(f"Failed to decrypt message: {e}")
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            raise  # Add raise for debugging
    
    # Set message handler on all nodes
    for network in networks:
        network.set_message_handler(on_message)
    
    # Create a test message
    message = {
        "type": "chat",
        "content": "Hello through onion network!",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    logger.info(f"Original message: {message}")
    
    # Generate onion layers
    layers = generate_onion_layers(3)
    # Get public keys in forward order (from first hop to last)
    route_public_keys = [layers[f"hop_{i}"]["public_key"] for i in range(3)]
    logger.info(f"Route public keys (forward order):")
    for i, pubkey in enumerate(route_public_keys):
        logger.info(f"  hop_{i}: {pubkey}")
    
    # Set private keys
    for i, network in enumerate(networks):
        private_key = PrivateKey(base64.b64decode(layers[f"hop_{i}"]["private_key"]))
        network.crypto.set_private_key(private_key)
        logger.info(f"Node {i} (hop {i}):")
        logger.info(f"  private key (len={len(private_key.encode())}): {base64.b64encode(private_key.encode()).decode()}")
        logger.info(f"  public key (len={len(private_key.public_key.encode())}): {base64.b64encode(private_key.public_key.encode()).decode()}")
    
    # Wrap message in reverse order (from last hop to first)
    wrapped = wrap_in_onion_layers(message, route_public_keys)
    logger.info(f"Wrapped message: {wrapped}")
    
    # Send through the network
    initial_message = {
        "type": "onion",
        "circuit_id": "test_circuit",
        "payload": wrapped
    }
    initial_msg = json.dumps(initial_message)
    logger.info(f"Sending initial message (len={len(initial_msg)}): {initial_msg[:200]}...")
    await networks[0].send_message(networks[0].connections[0].remote_address, initial_msg)
    
    # Wait for message to be received
    await asyncio.sleep(2)  # Increase wait time
    
    # Check that we got the original message
    assert len(messages) > 0, "No messages received"
    assert messages[-1] == message, f"Expected {message}, got {messages[-1]}"

@pytest.mark.asyncio
async def test_onion_layer_encryption_decryption():
    """Test single layer encryption and decryption."""
    # Generate test keys for recipient
    recipient_private_key = PrivateKey.generate()
    recipient_public_key = recipient_private_key.public_key
    
    # Create test message
    message = {
        "type": "chat",
        "content": "Test message",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    
    # Generate ephemeral key pair for sender
    sender_ephemeral_private_key = PrivateKey.generate()
    sender_ephemeral_public_key = sender_ephemeral_private_key.public_key
    
    # Create Box for encryption using sender's ephemeral private key and recipient's public key
    box = Box(sender_ephemeral_private_key, recipient_public_key)
    
    # Encrypt message
    message_json = json.dumps(message)
    encrypted = box.encrypt(message_json.encode('utf-8'))
    
    # Create layer
    layer = {
        "nonce": base64.b64encode(encrypted.nonce).decode('utf-8'),
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode('utf-8'),
        "ephemeral_pubkey": base64.b64encode(sender_ephemeral_public_key.encode()).decode('utf-8')
    }
    
    # Decrypt layer using recipient's private key
    decrypted = unwrap_onion_layer(layer, recipient_private_key)
    assert decrypted == message

@pytest.mark.asyncio
async def test_onion_layer_chain():
    """Test chain of onion layers."""
    # Generate test keys
    keys = []
    for _ in range(3):
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        keys.append((private_key, public_key))
    
    # Create test message
    message = {
        "type": "chat",
        "content": "Test message",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    
    # Wrap message in layers
    current_layer = message
    for _, public_key in reversed(keys):
        sender_ephemeral_private_key = PrivateKey.generate()
        sender_ephemeral_public_key = sender_ephemeral_private_key.public_key
        box = Box(sender_ephemeral_private_key, public_key)  # Sender's ephemeral private key, recipient's public key
        
        layer_json = json.dumps(current_layer)
        encrypted = box.encrypt(layer_json.encode('utf-8'))
        
        current_layer = {
            "nonce": base64.b64encode(encrypted.nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(encrypted.ciphertext).decode('utf-8'),
            "ephemeral_pubkey": base64.b64encode(sender_ephemeral_public_key.encode()).decode('utf-8')
        }
    
    # Unwrap layers
    for private_key, _ in keys:
        current_layer = unwrap_onion_layer(current_layer, private_key)
    
    assert current_layer == message

@pytest.mark.asyncio
async def test_onion_network_message_flow(onion_network):
    """Test message flow through network with detailed logging."""
    networks = onion_network
    messages = []
    message_flow = []
    
    async def on_message(conn, msg):
        logger.info(f"Message handler called with message (len={len(msg)}): {msg[:200]}...")
        try:
            data = json.loads(msg)
            logger.info(f"Parsed message as JSON: {data}")
            
            if isinstance(data, dict) and data.get("type") == "onion":
                network = next(n for n in networks if any(c == conn for c in n.connections))
                logger.info(f"Processing onion message on node {network.config.port}")
                logger.info(f"Network private key (len={len(network.crypto.private_key.encode())}): {base64.b64encode(network.crypto.private_key.encode()).decode()}")
                logger.info(f"Network public key (len={len(network.crypto.private_key.public_key.encode())}): {base64.b64encode(network.crypto.private_key.public_key.encode()).decode()}")
                
                payload = data["payload"]
                logger.info(f"Payload before unwrapping: {payload}")
                
                try:
                    unwrapped = unwrap_onion_layer(payload, network.crypto.private_key)
                    logger.info(f"Unwrapped payload: {unwrapped}")
                    
                    message_flow.append({
                        "node": network.config.port,
                        "payload": payload,
                        "unwrapped": unwrapped
                    })
                    
                    if isinstance(unwrapped, dict) and unwrapped.get("type") == "chat":
                        logger.info(f"Found chat message: {unwrapped}")
                        messages.append(unwrapped)
                    elif isinstance(unwrapped, dict) and "ciphertext" in unwrapped:
                        next_hop = next((n for n in networks if n != network), None)
                        if next_hop:
                            logger.info(f"Forwarding to next hop: port={next_hop.config.port}")
                            next_message = {
                                "type": "onion",
                                "circuit_id": data["circuit_id"],
                                "payload": unwrapped
                            }
                            if next_hop.connections:
                                next_msg = json.dumps(next_message)
                                logger.info(f"Sending message to next hop (len={len(next_msg)}): {next_msg[:200]}...")
                                await next_hop.send_message(
                                    next_hop.connections[0].remote_address,
                                    next_msg
                                )
                except Exception as e:
                    logger.error(f"Error in node {network.config.port}: {e}")
                    raise
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            raise
    
    # Set message handler on all nodes
    for network in networks:
        network.set_message_handler(on_message)
    
    # Create test message
    message = {
        "type": "chat",
        "content": "Test message",
        "timestamp": "2024-03-20T12:00:00Z"
    }
    
    # Generate layers
    layers = generate_onion_layers(3)
    route_public_keys = [layers[f"hop_{i}"]["public_key"] for i in range(3)]
    logger.info(f"Route public keys (forward order):")
    for i, pubkey in enumerate(route_public_keys):
        logger.info(f"  hop_{i}: {pubkey}")
    
    # Set private keys
    for i, network in enumerate(networks):
        private_key = PrivateKey(base64.b64decode(layers[f"hop_{i}"]["private_key"]))
        network.crypto.set_private_key(private_key)
        logger.info(f"Node {i} (hop {i}):")
        logger.info(f"  private key (len={len(private_key.encode())}): {base64.b64encode(private_key.encode()).decode()}")
        logger.info(f"  public key (len={len(private_key.public_key.encode())}): {base64.b64encode(private_key.public_key.encode()).decode()}")
    
    # Wrap message
    wrapped = wrap_in_onion_layers(message, route_public_keys)
    logger.info(f"Wrapped message: {wrapped}")
    
    # Send message
    initial_message = {
        "type": "onion",
        "circuit_id": "test_circuit",
        "payload": wrapped
    }
    initial_msg = json.dumps(initial_message)
    logger.info(f"Sending initial message (len={len(initial_msg)}): {initial_msg[:200]}...")
    await networks[0].send_message(networks[0].connections[0].remote_address, initial_msg)
    
    # Wait for processing
    await asyncio.sleep(2)
    
    # Verify message flow
    assert len(message_flow) > 0, "No message flow recorded"
    for flow in message_flow:
        logger.info(f"Message flow on node {flow['node']}:")
        logger.info(f"  Payload: {flow['payload']}")
        logger.info(f"  Unwrapped: {flow['unwrapped']}")
    
    # Verify final message
    assert len(messages) > 0, "No messages received"
    assert messages[-1] == message, f"Expected {message}, got {messages[-1]}" 