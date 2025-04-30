import pytest
import asyncio
import json
from unittest.mock import Mock, patch
from src.network import P2PConnection
from src.crypto import CryptoManager
from src.security import SecurityManager
import pytest_asyncio
import websockets
import random

@pytest_asyncio.fixture
async def crypto_manager():
    cm = CryptoManager()
    await cm.init()
    return cm

@pytest_asyncio.fixture
async def security_manager(crypto_manager):
    sm = SecurityManager(crypto_manager)
    await sm.init()
    return sm

@pytest_asyncio.fixture
async def server_port():
    return random.randint(8000, 9000)

@pytest_asyncio.fixture
async def server(server_port):
    async def echo(websocket):
        async for message in websocket:
            await websocket.send(message)

    server = await websockets.serve(echo, "localhost", server_port)
    yield server
    server.close()
    await server.wait_closed()

@pytest_asyncio.fixture
async def connection(crypto_manager, security_manager, server, server_port):
    conn = P2PConnection(
        host="localhost",
        port=server_port,
        node_id="test_node",
        public_key="test_key",
        crypto_manager=crypto_manager,
        security_manager=security_manager
    )
    await conn.init()
    yield conn
    await conn.stop()

@pytest.mark.asyncio
async def test_connection_establishment(connection):
    async with connection as conn:
        await conn.connect()
        assert conn.connected
        assert conn.connection_state == "connected"

@pytest.mark.asyncio
async def test_connection_error_handling(connection):
    async with connection as conn:
        await conn.connect()
        # Simulate error by closing connection
        await conn.stop()
        assert not conn.connected
        assert conn.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_message_sending(connection):
    async with connection as conn:
        await conn.connect()
        message_type = "test"
        message_data = {"data": "test_data"}
        await conn.send_message(message_type, message_data)
        # Add assertions for message sending

@pytest.mark.asyncio
async def test_ping(connection):
    async with connection as conn:
        await conn.connect()
        await conn.ping()
        # Add assertions for ping response

@pytest.mark.asyncio
async def test_connection_cleanup(connection):
    async with connection as conn:
        await conn.connect()
        await conn.stop()
        assert not conn.connected
        assert conn.connection_state == "disconnected" 
import asyncio
import json
from unittest.mock import Mock, patch
from src.network import P2PConnection
from src.crypto import CryptoManager
from src.security import SecurityManager
import pytest_asyncio
import websockets
import random

@pytest_asyncio.fixture
async def crypto_manager():
    cm = CryptoManager()
    await cm.init()
    return cm

@pytest_asyncio.fixture
async def security_manager(crypto_manager):
    sm = SecurityManager(crypto_manager)
    await sm.init()
    return sm

@pytest_asyncio.fixture
async def server_port():
    return random.randint(8000, 9000)

@pytest_asyncio.fixture
async def server(server_port):
    async def echo(websocket):
        async for message in websocket:
            await websocket.send(message)

    server = await websockets.serve(echo, "localhost", server_port)
    yield server
    server.close()
    await server.wait_closed()

@pytest_asyncio.fixture
async def connection(crypto_manager, security_manager, server, server_port):
    conn = P2PConnection(
        host="localhost",
        port=server_port,
        node_id="test_node",
        public_key="test_key",
        crypto_manager=crypto_manager,
        security_manager=security_manager
    )
    await conn.init()
    yield conn
    await conn.stop()

@pytest.mark.asyncio
async def test_connection_establishment(connection):
    async with connection as conn:
        await conn.connect()
        assert conn.connected
        assert conn.connection_state == "connected"

@pytest.mark.asyncio
async def test_connection_error_handling(connection):
    async with connection as conn:
        await conn.connect()
        # Simulate error by closing connection
        await conn.stop()
        assert not conn.connected
        assert conn.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_message_sending(connection):
    async with connection as conn:
        await conn.connect()
        message_type = "test"
        message_data = {"data": "test_data"}
        await conn.send_message(message_type, message_data)
        # Add assertions for message sending

@pytest.mark.asyncio
async def test_ping(connection):
    async with connection as conn:
        await conn.connect()
        await conn.ping()
        # Add assertions for ping response

@pytest.mark.asyncio
async def test_connection_cleanup(connection):
    async with connection as conn:
        await conn.connect()
        await conn.stop()
        assert not conn.connected
        assert conn.connection_state == "disconnected" 