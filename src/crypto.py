"""
Модуль криптографии для SecureTermChat

Реализует функции шифрования и дешифрования сообщений, генерации ключей,
и другие криптографические примитивы.
"""

import os
import json
import base64
import logging
import time
import asyncio
from typing import Dict, Tuple, Optional, Any, Union, List
from datetime import datetime
import hashlib

import nacl.utils
import nacl.secret
import nacl.public
from nacl.public import PrivateKey, PublicKey, Box
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger("securetermchat.crypto")

class CryptoManager:
    """Менеджер криптографии для приложения"""
    
    def __init__(self, config=None):
        """Initialize the crypto manager"""
        self.config = config
        private_key = PrivateKey.generate()
        self.private_key = private_key
        self.public_key = private_key.public_key
        self.contact_keys = {}  # contact_id -> PublicKey
        self.encryption_boxes = {}  # contact_id -> Box
        self.group_keys = {}  # group_id -> (key, timestamp)
        self.key_rotation_interval = 3600  # 1 hour
        self.last_key_rotation = time.time()
        
    async def init(self):
        """Initialize any async resources"""
        if not self.private_key:
            keypair = generate_keypair()
            self.private_key, self.public_key = load_keypair(keypair)
        # Start key rotation
        self._rotation_task = asyncio.create_task(self._key_rotation_loop())
        
    async def stop(self):
        """Stop the crypto manager"""
        if hasattr(self, '_rotation_task'):
            self._rotation_task.cancel()
            try:
                await self._rotation_task
            except asyncio.CancelledError:
                pass

    def set_private_key(self, private_key: PrivateKey):
        """Set the private key for this node"""
        self.private_key = private_key
        self.public_key = private_key.public_key
        
    def get_public_key(self) -> PublicKey:
        """Get the public key for this node"""
        return self.public_key
        
    def add_contact_key(self, contact_id: str, public_key_or_b64: Union[str, PublicKey]):
        """Add a contact's public key"""
        try:
            if isinstance(public_key_or_b64, str):
                public_key = PublicKey(base64.b64decode(public_key_or_b64))
            else:
                public_key = public_key_or_b64
                
            self.contact_keys[contact_id] = public_key
            self.encryption_boxes[contact_id] = Box(self.private_key, public_key)
        except Exception as e:
            raise Exception(f"Invalid public key: {e}")
            
    def remove_contact_key(self, contact_id: str):
        """Remove a contact's key"""
        if contact_id in self.contact_keys:
            del self.contact_keys[contact_id]
        if contact_id in self.encryption_boxes:
            del self.encryption_boxes[contact_id]
            
    def encrypt_message(self, message: str, recipient_id: str) -> str:
        """Encrypt a message for a specific recipient"""
        if recipient_id not in self.contact_keys:
            raise ValueError(f"Нет ключа для контакта {recipient_id}")
            
        box = self.encryption_boxes[recipient_id]
        nonce = nacl.utils.random(Box.NONCE_SIZE)
        encrypted = box.encrypt(message.encode(), nonce)
        return base64.b64encode(encrypted).decode()
        
    def decrypt_message(self, encrypted: str) -> str:
        """Decrypt a message"""
        try:
            encrypted_bytes = base64.b64decode(encrypted)
            # Try each contact's box
            for box in self.encryption_boxes.values():
                try:
                    decrypted = box.decrypt(encrypted_bytes)
                    return decrypted.decode()
                except:
                    continue
            raise Exception("Could not decrypt message with any known key")
        except Exception as e:
            raise Exception(f"Error decrypting message: {e}")

    def generate_group_key(self, group_id: str) -> str:
        """Generate a new key for a group"""
        key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
        self.group_keys[group_id] = (key, time.time())
        return base64.b64encode(key).decode()

    def get_group_key(self, group_id: str) -> Optional[bytes]:
        """Get group key for a specific group."""
        return self.group_keys.get(group_id)

    def encrypt_group_message(self, message: str, group_id: str) -> str:
        """Encrypt a message for a group"""
        key = self.get_group_key(group_id)
        box = nacl.secret.SecretBox(key)
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        encrypted = box.encrypt(message.encode(), nonce)
        return base64.b64encode(encrypted).decode()

    def decrypt_group_message(self, encrypted: str, group_id: str) -> str:
        """Decrypt a message from a group"""
        try:
            encrypted_bytes = base64.b64decode(encrypted)
            key = self.get_group_key(group_id)
            box = nacl.secret.SecretBox(key)
            decrypted = box.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            raise Exception(f"Error decrypting group message: {e}")

    async def _key_rotation_loop(self):
        """Background task for key rotation"""
        while True:
            try:
                now = time.time()
                if now - self.last_key_rotation >= self.key_rotation_interval:
                    await self._rotate_keys()
                    self.last_key_rotation = now
                await asyncio.sleep(0.1)  # Check more frequently for tests
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in key rotation: {e}")
                await asyncio.sleep(5)

    async def _rotate_keys(self):
        """Rotate all keys"""
        # Rotate group keys
        for group_id in list(self.group_keys.keys()):
            key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
            self.group_keys[group_id] = (key, time.time())
            
        # Clear box cache to force regeneration
        self.encryption_boxes.clear()
        
        logger.info("Keys rotated successfully")

    def generate_ephemeral_key(self) -> bytes:
        """Generate a new ephemeral key for challenge-response."""
        return nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)

    def generate_random_bytes(self, size: int) -> bytes:
        """Генерирует случайные байты заданного размера"""
        return nacl.utils.random(size)

    def hash(self, data: bytes) -> bytes:
        """Вычисляет хеш данных"""
        return hashlib.sha256(data).digest()

class CryptoError(Exception):
    """Custom exception for crypto-related errors."""
    pass

def generate_keypair() -> Dict[str, str]:
    """
    Генерирует новую пару ключей для end-to-end шифрования
    
    Returns:
        Dict[str, str]: Словарь, содержащий приватный и публичный ключи в base64
    """
    private_key = PrivateKey.generate()
    public_key = private_key.public_key
    
    return {
        "private_key": base64.b64encode(private_key.encode()).decode('utf-8'),
        "public_key": base64.b64encode(public_key.encode()).decode('utf-8')
    }

def load_keypair(key_data: Dict[str, str]) -> Tuple[PrivateKey, PublicKey]:
    """
    Загружает пару ключей из сохраненных данных
    
    Args:
        key_data (Dict[str, str]): Словарь с ключами в формате base64
        
    Returns:
        Tuple[PrivateKey, PublicKey]: Пара ключей NaCl
    """
    private_key_bytes = base64.b64decode(key_data["private_key"])
    private_key = PrivateKey(private_key_bytes)
    public_key = private_key.public_key
    
    # Проверка соответствия публичного ключа
    loaded_public_key = base64.b64decode(key_data["public_key"])
    if not public_key.encode() == loaded_public_key:
        logger.warning("Загруженный публичный ключ не соответствует приватному!")
    
    return private_key, public_key

def encrypt_message(message: str, sender_private_key: PrivateKey, 
                   recipient_public_key: PublicKey) -> Dict[str, str]:
    """
    Шифрует сообщение для получателя с использованием X25519 и XChaCha20-Poly1305
    
    Args:
        message (str): Сообщение для шифрования
        sender_private_key (PrivateKey): Приватный ключ отправителя
        recipient_public_key (PublicKey): Публичный ключ получателя
        
    Returns:
        Dict[str, str]: Шифротекст и метаданные в base64
    """
    # Создаем Box для обмена с получателем
    box = Box(sender_private_key, recipient_public_key)
    
    # Генерируем уникальный nonce
    nonce = nacl.utils.random(Box.NONCE_SIZE)
    
    # Шифруем сообщение
    encrypted = box.encrypt(message.encode('utf-8'), nonce)
    
    # Формируем результат
    result = {
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode('utf-8'),
        "nonce": base64.b64encode(encrypted.nonce).decode('utf-8'),
        "timestamp": str(int(os.time())),
        "protocol_version": "1.0"
    }
    
    return result

def decrypt_message(encrypted_data: Dict[str, str], recipient_private_key: PrivateKey,
                   sender_public_key: PublicKey) -> str:
    """
    Дешифрует сообщение от отправителя
    
    Args:
        encrypted_data (Dict[str, str]): Шифротекст и метаданные в base64
        recipient_private_key (PrivateKey): Приватный ключ получателя
        sender_public_key (PublicKey): Публичный ключ отправителя
        
    Returns:
        str: Дешифрованное сообщение
    """
    # Создаем Box для обмена с отправителем
    box = Box(recipient_private_key, sender_public_key)
    
    # Извлекаем данные
    ciphertext = base64.b64decode(encrypted_data["ciphertext"])
    nonce = base64.b64decode(encrypted_data["nonce"])
    
    # Дешифруем сообщение
    plaintext = box.decrypt(ciphertext, nonce)
    
    return plaintext.decode('utf-8')

def generate_onion_layers(hops: int) -> Dict[str, Any]:
    """
    Генерирует слои шифрования для луковой маршрутизации
    
    Args:
        hops (int): Количество промежуточных узлов
        
    Returns:
        Dict[str, Any]: Структура ключей для каждого слоя
    """
    layers = {}
    
    for i in range(hops):
        # Генерируем ключи для каждого узла в цепочке
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        
        layers[f"hop_{i}"] = {
            "private_key": base64.b64encode(private_key.encode()).decode('utf-8'),
            "public_key": base64.b64encode(public_key.encode()).decode('utf-8')
        }
    
    return layers

def wrap_in_onion_layers(message: dict, node_public_keys: list) -> dict:
    """Wrap a message in onion layers for routing"""
    try:
        current_layer = message
        for pubkey_b64 in reversed(node_public_keys):
            # Generate ephemeral key pair for this hop
            ephemeral_private = PrivateKey.generate()
            ephemeral_public = ephemeral_private.public_key
            
            # Decode the node's public key from base64
            pubkey = PublicKey(base64.b64decode(pubkey_b64))
            
            # Create box for encryption
            box = Box(ephemeral_private, pubkey)
            
            # Encrypt the current layer
            nonce = nacl.utils.random(Box.NONCE_SIZE)
            encrypted = box.encrypt(json.dumps(current_layer).encode(), nonce)
            
            # Create the new layer
            current_layer = {
                "ciphertext": base64.b64encode(encrypted).decode(),
                "next_hop": base64.b64encode(ephemeral_public.encode()).decode()
            }
            
        return current_layer
    except Exception as e:
        logger.error(f"Error in wrap_in_onion_layers at hop {len(node_public_keys)}: {e}")
        raise

def unwrap_onion_layer(layer: dict, private_key: PrivateKey) -> dict:
    """Unwrap one layer of onion routing"""
    try:
        # Extract the ephemeral public key
        ephemeral_public = PublicKey(base64.b64decode(layer["next_hop"]))
        
        # Create box for decryption
        box = Box(private_key, ephemeral_public)
        
        # Decrypt the layer
        encrypted = base64.b64decode(layer["ciphertext"])
        decrypted = box.decrypt(encrypted)
        
        # Parse the decrypted content
        return json.loads(decrypted.decode())
    except Exception as e:
        logger.error(f"Error unwrapping onion layer: {e}")
        raise 