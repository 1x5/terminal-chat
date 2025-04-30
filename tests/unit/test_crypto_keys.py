import base64
import pytest
from nacl.public import PrivateKey, PublicKey, Box

from src.crypto import generate_keypair, load_keypair

def test_keypair_generation():
    """Тест генерации пары ключей"""
    # Генерируем пару ключей
    keypair = generate_keypair()
    
    # Проверяем наличие обоих ключей
    assert "private_key" in keypair
    assert "public_key" in keypair
    
    # Проверяем что ключи в формате base64
    private_key_bytes = base64.b64decode(keypair["private_key"])
    public_key_bytes = base64.b64decode(keypair["public_key"])
    
    # Проверяем длину ключей (32 байта для Ed25519)
    assert len(private_key_bytes) == 32
    assert len(public_key_bytes) == 32
    
    # Проверяем что можем создать объекты ключей
    private_key = PrivateKey(private_key_bytes)
    public_key = PublicKey(public_key_bytes)
    
    # Проверяем что публичный ключ соответствует приватному
    assert private_key.public_key.encode() == public_key.encode()

def test_keypair_loading():
    """Тест загрузки пары ключей"""
    # Генерируем тестовую пару ключей
    original_keypair = generate_keypair()
    
    # Загружаем ключи
    private_key, public_key = load_keypair(original_keypair)
    
    # Проверяем что загруженные ключи соответствуют оригинальным
    assert base64.b64encode(private_key.encode()).decode() == original_keypair["private_key"]
    assert base64.b64encode(public_key.encode()).decode() == original_keypair["public_key"]

def test_box_creation():
    """Тест создания Box для шифрования/дешифрования"""
    # Генерируем ключи для отправителя и получателя
    sender_keypair = generate_keypair()
    recipient_keypair = generate_keypair()
    
    # Загружаем ключи
    sender_private, sender_public = load_keypair(sender_keypair)
    recipient_private, recipient_public = load_keypair(recipient_keypair)
    
    # Создаем Box для шифрования (у отправителя)
    encryption_box = Box(sender_private, recipient_public)
    
    # Создаем Box для дешифрования (у получателя)
    decryption_box = Box(recipient_private, sender_public)
    
    # Тестируем шифрование/дешифрование
    message = b"Test message"
    encrypted = encryption_box.encrypt(message)
    decrypted = decryption_box.decrypt(encrypted)
    
    assert decrypted == message

def test_box_encryption_order():
    """Тест порядка ключей при создании Box"""
    # Генерируем ключи
    alice_private = PrivateKey.generate()
    alice_public = alice_private.public_key
    bob_private = PrivateKey.generate()
    bob_public = bob_private.public_key
    
    # Создаем Box для Алисы (отправитель)
    alice_box = Box(alice_private, bob_public)
    
    # Создаем Box для Боба (получатель)
    bob_box = Box(bob_private, alice_public)
    
    # Тестируем шифрование/дешифрование
    message = b"Test message"
    encrypted = alice_box.encrypt(message)
    decrypted = bob_box.decrypt(encrypted)
    
    assert decrypted == message
    
    # Проверяем что обратный порядок ключей не работает
    with pytest.raises(Exception):
        wrong_box = Box(alice_public, bob_private)  # Неправильный порядок

def test_ephemeral_key_generation():
    """Тест генерации временных ключей"""
    # Генерируем временную пару ключей
    ephemeral_private = PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key
    
    # Проверяем длину ключей
    assert len(ephemeral_private.encode()) == 32
    assert len(ephemeral_public.encode()) == 32
    
    # Проверяем что публичный ключ соответствует приватному
    assert ephemeral_private.public_key.encode() == ephemeral_public.encode()
    
    # Проверяем что каждая новая пара ключей уникальна
    another_ephemeral = PrivateKey.generate()
    assert ephemeral_private.encode() != another_ephemeral.encode()

def test_key_encoding_decoding():
    """Тест кодирования и декодирования ключей"""
    # Генерируем ключи
    private_key = PrivateKey.generate()
    public_key = private_key.public_key
    
    # Кодируем в base64
    private_b64 = base64.b64encode(private_key.encode()).decode()
    public_b64 = base64.b64encode(public_key.encode()).decode()
    
    # Декодируем обратно
    decoded_private = PrivateKey(base64.b64decode(private_b64))
    decoded_public = PublicKey(base64.b64decode(public_b64))
    
    # Проверяем что ключи совпадают
    assert decoded_private.encode() == private_key.encode()
    assert decoded_public.encode() == public_key.encode()
    
    # Проверяем что публичные ключи соответствуют приватным
    assert decoded_private.public_key.encode() == decoded_public.encode() 