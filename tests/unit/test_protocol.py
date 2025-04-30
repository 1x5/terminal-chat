"""
Тесты для протокола обмена сообщениями
"""

import pytest
import json
import time
from src.protocol import (
    Message, MessageType, HandshakeMessage, OnionMessage,
    PingMessage, PongMessage, ErrorMessage, RouteUpdateMessage,
    NodeInfoMessage
)

def test_message_serialization():
    """Тест сериализации/десериализации сообщений"""
    # Создаем тестовые данные
    public_key = "test_public_key"
    node_id = "test_node_id"
    version = "1.0.0"
    
    # Создаем сообщение
    message = HandshakeMessage(public_key, node_id, version)
    
    # Сериализуем в JSON
    json_str = message.to_json()
    data = json.loads(json_str)
    
    # Проверяем структуру
    assert data["type"] == MessageType.HANDSHAKE.value
    assert data["data"]["public_key"] == public_key
    assert data["data"]["node_id"] == node_id
    assert data["data"]["version"] == version
    
    # Десериализуем обратно
    restored = Message.from_json(json_str)
    assert isinstance(restored, HandshakeMessage)
    assert restored.data["public_key"] == public_key
    assert restored.data["node_id"] == node_id
    assert restored.data["version"] == version

def test_onion_message():
    """Тест сообщения с луковой маршрутизацией"""
    layer = {
        "ciphertext": "encrypted_data",
        "nonce": "test_nonce",
        "ephemeral_pubkey": "test_pubkey"
    }
    next_hop = "next_node_id"
    
    message = OnionMessage(layer, next_hop)
    json_str = message.to_json()
    restored = Message.from_json(json_str)
    
    assert isinstance(restored, OnionMessage)
    assert restored.data["layer"] == layer
    assert restored.data["next_hop"] == next_hop

def test_ping_pong():
    """Тест пинг/понг сообщений"""
    timestamp = time.time()
    
    # Тест пинга
    ping = PingMessage(timestamp)
    json_str = ping.to_json()
    restored_ping = Message.from_json(json_str)
    
    assert isinstance(restored_ping, PingMessage)
    assert restored_ping.data["timestamp"] == timestamp
    
    # Тест понга
    latency = 0.1
    pong = PongMessage(timestamp, latency)
    json_str = pong.to_json()
    restored_pong = Message.from_json(json_str)
    
    assert isinstance(restored_pong, PongMessage)
    assert restored_pong.data["timestamp"] == timestamp
    assert restored_pong.data["latency"] == latency

def test_error_message():
    """Тест сообщения об ошибке"""
    code = "CONNECTION_ERROR"
    message = "Connection failed"
    
    error = ErrorMessage(code, message)
    json_str = error.to_json()
    restored = Message.from_json(json_str)
    
    assert isinstance(restored, ErrorMessage)
    assert restored.data["code"] == code
    assert restored.data["message"] == message

def test_route_update():
    """Тест сообщения обновления маршрута"""
    route = {
        "nodes": ["node1", "node2", "node3"],
        "public_keys": ["key1", "key2", "key3"]
    }
    
    update = RouteUpdateMessage(route)
    json_str = update.to_json()
    restored = Message.from_json(json_str)
    
    assert isinstance(restored, RouteUpdateMessage)
    assert restored.data["route"] == route

def test_node_info():
    """Тест сообщения с информацией об узле"""
    node_id = "test_node"
    public_key = "test_key"
    address = "localhost:8000"
    connections = 5
    version = "1.0.0"
    
    info = NodeInfoMessage(node_id, public_key, address, connections, version)
    json_str = info.to_json()
    restored = Message.from_json(json_str)
    
    assert isinstance(restored, NodeInfoMessage)
    assert restored.data["node_id"] == node_id
    assert restored.data["public_key"] == public_key
    assert restored.data["address"] == address
    assert restored.data["connections"] == connections
    assert restored.data["version"] == version 