"""
Тесты для модуля криптографии
"""

import pytest
import asyncio
import time
from src.crypto import (
    CryptoManager, generate_keypair, load_keypair, generate_onion_layers,
    wrap_in_onion_layers, unwrap_onion_layer
)
from nacl.public import PrivateKey, PublicKey

def test_keypair_generation():
    """Проверяет генерацию пары ключей"""
    keypair = generate_keypair()
    assert "private_key" in keypair
    assert "public_key" in keypair
    assert len(keypair["private_key"]) > 0
    assert len(keypair["public_key"]) > 0

def test_keypair_loading():
    """Проверяет загрузку пары ключей"""
    keypair = generate_keypair()
    private_key, public_key = load_keypair(keypair)
    assert private_key is not None
    assert public_key is not None

def test_message_encryption_decryption():
    """Проверяет шифрование и дешифрование сообщений"""
    # Создаем менеджер криптографии для отправителя
    sender = CryptoManager()
    
    # Создаем менеджер криптографии для получателя
    recipient = CryptoManager()
    
    # Добавляем ключи
    sender.add_contact_key("recipient", recipient.get_public_key())
    recipient.add_contact_key(sender.get_public_key(), sender.get_public_key())
    
    # Тестовое сообщение
    message = "Тестовое сообщение"
    
    # Шифруем сообщение
    encrypted = sender.encrypt_message(message, "recipient")
    assert encrypted is not None
    assert len(encrypted) > 0
    
    # Расшифровываем сообщение
    decrypted = recipient.decrypt_message(encrypted)
    assert decrypted == message

def test_onion_layers():
    """Проверяет создание и обработку луковых слоев"""
    # Генерируем ключи для нескольких узлов
    node_keys = [generate_keypair() for _ in range(3)]
    node_public_keys = [k["public_key"] for k in node_keys]  # Уже в base64
    
    # Создаем менеджер криптографии
    crypto = CryptoManager()
    
    # Тестовое сообщение
    message = "Тестовое сообщение"
    
    # Создаем луковые слои
    layers = generate_onion_layers(3)
    assert len(layers) == 3
    
    # Проверяем структуру слоев
    for i in range(3):
        layer = layers[f"hop_{i}"]
        assert "private_key" in layer
        assert "public_key" in layer
        assert len(layer["private_key"]) > 0
        assert len(layer["public_key"]) > 0

def test_crypto_manager_initialization():
    """Проверяет инициализацию менеджера криптографии"""
    crypto = CryptoManager()
    assert crypto.private_key is not None
    assert crypto.public_key is not None
    assert len(crypto.contact_keys) == 0
    assert len(crypto.encryption_boxes) == 0

def test_contact_key_management():
    """Проверяет управление ключами контактов"""
    crypto = CryptoManager()
    
    # Добавляем ключ контакта
    contact_id = "test_contact"
    contact_keypair = generate_keypair()
    crypto.add_contact_key(contact_id, contact_keypair["public_key"])
    
    assert contact_id in crypto.contact_keys
    assert contact_id in crypto.encryption_boxes
    
    # Удаляем ключ контакта
    crypto.remove_contact_key(contact_id)
    assert contact_id not in crypto.contact_keys
    assert contact_id not in crypto.encryption_boxes

def test_invalid_contact_key():
    """Проверяет обработку невалидного ключа контакта"""
    crypto = CryptoManager()
    
    with pytest.raises(Exception):
        crypto.add_contact_key("invalid", "not-a-valid-key")
        
def test_unknown_recipient():
    """Проверяет шифрование для неизвестного получателя"""
    crypto = CryptoManager()
    
    with pytest.raises(ValueError, match="Нет ключа для контакта unknown"):
        crypto.encrypt_message("test", "unknown")
        
def test_invalid_encrypted_message():
    """Проверяет расшифровку невалидного сообщения"""
    crypto = CryptoManager()
    
    with pytest.raises(Exception):
        crypto.decrypt_message("not-a-valid-message")
        
def test_message_tampering():
    """Проверяет обнаружение подмены сообщения"""
    # Создаем отправителя и получателя
    sender = CryptoManager()
    recipient = CryptoManager()
    
    # Добавляем ключи
    sender.add_contact_key("recipient", recipient.get_public_key())
    recipient.add_contact_key(sender.get_public_key(), sender.get_public_key())
    
    # Шифруем сообщение
    message = "Тестовое сообщение"
    encrypted = sender.encrypt_message(message, "recipient")
    
    # Подменяем часть сообщения
    tampered = encrypted[:-10] + "X" * 10
    
    # Проверяем что расшифровка не удается
    with pytest.raises(Exception):
        recipient.decrypt_message(tampered)
        
def test_empty_message():
    """Проверяет шифрование/расшифровку пустого сообщения"""
    # Создаем отправителя и получателя
    sender = CryptoManager()
    recipient = CryptoManager()
    
    # Добавляем ключи
    sender.add_contact_key("recipient", recipient.get_public_key())
    recipient.add_contact_key(sender.get_public_key(), sender.get_public_key())
    
    # Шифруем пустое сообщение
    message = ""
    encrypted = sender.encrypt_message(message, "recipient")
    
    # Расшифровываем
    decrypted = recipient.decrypt_message(encrypted)
    assert decrypted == message

def test_onion_routing_full():
    """Проверяет полный цикл луковой маршрутизации"""
    # Создаем ключи для узлов
    node_keys = [generate_keypair() for _ in range(3)]
    node_public_keys = [k["public_key"] for k in node_keys]  # Уже в base64
    
    # Создаем сообщение
    message = {
        "type": "message",
        "content": "Тестовое сообщение",
        "recipient": "test_recipient"
    }
    
    # Оборачиваем в луковые слои
    wrapped = wrap_in_onion_layers(message, node_public_keys)
    
    # Проверяем структуру
    assert "ciphertext" in wrapped
    assert "next_hop" in wrapped
    
    # Последовательно разворачиваем слои
    current_layer = wrapped
    for i in range(3):
        current_layer = unwrap_onion_layer(current_layer, load_keypair(node_keys[i])[0])
        if i < 2:
            assert "next_hop" in current_layer
            assert "ciphertext" in current_layer
        else:
            assert current_layer == message
            
def test_invalid_onion_layer():
    """Проверяет обработку невалидного лукового слоя"""
    # Создаем ключи
    keypair = generate_keypair()
    private_key, _ = load_keypair(keypair)
    
    # Пробуем развернуть невалидный слой
    invalid_layer = {
        "ciphertext": "not-valid-ciphertext",
        "next_hop": "next-node"
    }
    
    with pytest.raises(Exception):
        unwrap_onion_layer(invalid_layer, private_key)
        
def test_short_route():
    """Проверяет создание маршрута с минимальным количеством узлов"""
    # Создаем один узел
    node_keypair = generate_keypair()
    node_public_key = node_keypair["public_key"]  # Уже в base64
    
    # Создаем сообщение
    message = {
        "type": "message",
        "content": "Тестовое сообщение",
        "recipient": "test_recipient"
    }
    
    # Оборачиваем в один слой
    wrapped = wrap_in_onion_layers(message, [node_public_key])
    
    # Разворачиваем
    unwrapped = unwrap_onion_layer(wrapped, load_keypair(node_keypair)[0])
    assert unwrapped == message

@pytest.fixture
def crypto_manager():
    """Create a crypto manager instance"""
    manager = CryptoManager()
    private_key = PrivateKey.generate()
    manager.set_private_key(private_key)
    return manager

@pytest.mark.asyncio
async def test_group_encryption(crypto_manager):
    """Test group message encryption/decryption"""
    group_id = "test_group"
    message = "Hello group!"
    
    # Encrypt message
    encrypted = crypto_manager.encrypt_group_message(message, group_id)
    assert encrypted != message
    
    # Decrypt message
    decrypted = crypto_manager.decrypt_group_message(encrypted, group_id)
    assert decrypted == message

@pytest.mark.asyncio
async def test_group_key_rotation(crypto_manager):
    """Test group key rotation"""
    group_id = "test_group"
    
    # Generate initial key
    key1 = crypto_manager.get_group_key(group_id)
    
    # Force key rotation
    await crypto_manager._rotate_keys()
    
    # Get new key
    key2 = crypto_manager.get_group_key(group_id)
    
    # Keys should be different
    assert key1 != key2

@pytest.mark.asyncio
async def test_group_message_after_rotation(crypto_manager):
    """Test that messages can't be decrypted with old keys after rotation"""
    group_id = "test_group"
    message = "Secret message"
    
    # Encrypt with old key
    encrypted = crypto_manager.encrypt_group_message(message, group_id)
    
    # Rotate keys
    await crypto_manager._rotate_keys()
    
    # Try to decrypt with new key (should fail)
    with pytest.raises(Exception):
        crypto_manager.decrypt_group_message(encrypted, group_id)

@pytest.mark.asyncio
async def test_multiple_groups(crypto_manager):
    """Test handling multiple groups"""
    groups = ["group1", "group2", "group3"]
    message = "Group message"
    
    # Encrypt for each group
    encrypted_messages = {}
    for group_id in groups:
        encrypted_messages[group_id] = crypto_manager.encrypt_group_message(message, group_id)
    
    # Verify each message can only be decrypted by its group
    for group_id in groups:
        # Should decrypt successfully
        decrypted = crypto_manager.decrypt_group_message(encrypted_messages[group_id], group_id)
        assert decrypted == message
        
        # Try to decrypt with wrong group (should fail)
        wrong_group = next(g for g in groups if g != group_id)
        with pytest.raises(Exception):
            crypto_manager.decrypt_group_message(encrypted_messages[group_id], wrong_group)

@pytest.mark.asyncio
async def test_key_rotation_interval(crypto_manager):
    """Test that keys are rotated at the correct interval"""
    # Initialize the crypto manager
    await crypto_manager.init()
    
    # Set short interval for testing
    crypto_manager.key_rotation_interval = 1  # 1 second
    
    # Get initial key
    group_id = "test_group"
    key1 = crypto_manager.get_group_key(group_id)
    
    # Wait for rotation
    await asyncio.sleep(1.1)
    
    # Get new key
    key2 = crypto_manager.get_group_key(group_id)
    
    # Keys should be different
    assert key1 != key2
    
    # Cleanup
    await crypto_manager.stop() 