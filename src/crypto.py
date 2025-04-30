"""
Модуль криптографии для SecureTermChat

Реализует функции шифрования и дешифрования сообщений, генерации ключей,
и другие криптографические примитивы.
"""

import os
import json
import base64
import logging
from typing import Dict, Tuple, Optional, Any, Union
from datetime import datetime

import nacl.utils
import nacl.secret
import nacl.public
from nacl.public import PrivateKey, PublicKey, Box
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger("securetermchat.crypto")

class CryptoManager:
    """Менеджер криптографии для приложения"""
    
    def __init__(self):
        """Initialize the crypto manager"""
        self.private_key = None
        self.public_key = None
        self.boxes = {}  # Cache for encryption boxes
        
    def set_private_key(self, private_key: PrivateKey):
        """Set the private key for this node"""
        self.private_key = private_key
        self.public_key = private_key.public_key
        
    def get_box_for_peer(self, peer_public_key: PublicKey) -> Box:
        """Get or create a Box for communication with a peer"""
        if peer_public_key not in self.boxes:
            self.boxes[peer_public_key] = Box(self.private_key, peer_public_key)
        return self.boxes[peer_public_key]
        
    def encrypt(self, message: str, peer_public_key: PublicKey = None) -> str:
        """Encrypt a message"""
        if isinstance(message, dict):
            message = json.dumps(message)
            
        if peer_public_key:
            box = self.get_box_for_peer(peer_public_key)
        else:
            # For backward compatibility, use secret box
            box = nacl.secret.SecretBox(self.private_key.encode())
            
        nonce = nacl.utils.random(Box.NONCE_SIZE)
        encrypted = box.encrypt(message.encode(), nonce)
        return base64.b64encode(encrypted).decode()
        
    def decrypt(self, encrypted: str, peer_public_key: PublicKey = None) -> str:
        """Decrypt a message"""
        try:
            encrypted_bytes = base64.b64decode(encrypted)
            
            if peer_public_key:
                box = self.get_box_for_peer(peer_public_key)
            else:
                # For backward compatibility, use secret box
                box = nacl.secret.SecretBox(self.private_key.encode())
                
            decrypted = box.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Error decrypting message: {e}")
            raise

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

def wrap_in_onion_layers(message: Dict[str, str], route_public_keys: list) -> Dict[str, str]:
    """
    Оборачивает сообщение в слои шифрования для луковой маршрутизации
    
    Args:
        message (Dict[str, str]): Исходное зашифрованное сообщение
        route_public_keys (list): Список публичных ключей узлов маршрута (в прямом порядке)
        
    Returns:
        Dict[str, str]: Сообщение, обернутое в слои шифрования
    """
    logger.info(f"Wrapping message: {message}")
    logger.info(f"Route public keys: {route_public_keys}")
    
    # Начинаем с конечного сообщения
    current_layer = message
    logger.info(f"Initial layer: {current_layer}")
    
    # Добавляем слои шифрования в прямом порядке
    for i, pubkey_b64 in enumerate(route_public_keys):
        logger.info(f"Processing hop {i}")
        try:
            # Decode public key
            pubkey_bytes = base64.b64decode(pubkey_b64)
            logger.info(f"Decoded public key bytes (len={len(pubkey_bytes)}): {pubkey_bytes.hex()[:32]}...")
            pubkey = PublicKey(pubkey_bytes)
            logger.info(f"Created PublicKey object: {base64.b64encode(pubkey.encode()).decode()}")
            
            # Генерируем временный ключ для этого слоя
            ephemeral_key = PrivateKey.generate()
            ephemeral_pubkey = ephemeral_key.public_key
            logger.info(f"Generated ephemeral key pair:")
            logger.info(f"  private (len={len(ephemeral_key.encode())}): {base64.b64encode(ephemeral_key.encode()).decode()}")
            logger.info(f"  public (len={len(ephemeral_pubkey.encode())}): {base64.b64encode(ephemeral_pubkey.encode()).decode()}")
            
            # Создаем Box для шифрования
            box = Box(pubkey, ephemeral_key)
            logger.info("Created Box for encryption")
            
            # Шифруем текущий слой
            layer_json = json.dumps(current_layer)
            logger.info(f"Layer to encrypt (len={len(layer_json)}): {layer_json}")
            layer_bytes = layer_json.encode('utf-8')
            logger.info(f"Layer bytes (len={len(layer_bytes)}): {layer_bytes.hex()[:64]}...")
            
            # Шифруем данные
            encrypted = box.encrypt(layer_bytes)
            logger.info(f"Encrypted data:")
            logger.info(f"  nonce (len={len(encrypted.nonce)}): {encrypted.nonce.hex()}")
            logger.info(f"  ciphertext (len={len(encrypted.ciphertext)}): {encrypted.ciphertext.hex()[:64]}...")
            
            # Формируем новый слой
            current_layer = {
                "nonce": base64.b64encode(encrypted.nonce).decode('utf-8'),
                "ciphertext": base64.b64encode(encrypted.ciphertext).decode('utf-8'),
                "ephemeral_pubkey": base64.b64encode(ephemeral_pubkey.encode()).decode('utf-8')
            }
            logger.info(f"Created layer {i}:")
            logger.info(f"  nonce (len={len(current_layer['nonce'])}): {current_layer['nonce']}")
            logger.info(f"  ciphertext (len={len(current_layer['ciphertext'])}): {current_layer['ciphertext'][:64]}...")
            logger.info(f"  ephemeral_pubkey (len={len(current_layer['ephemeral_pubkey'])}): {current_layer['ephemeral_pubkey']}")
        except Exception as e:
            logger.error(f"Error in wrap_in_onion_layers at hop {i}: {e}")
            raise
    
    return current_layer

class CryptoError(Exception):
    """Custom exception for crypto-related errors."""
    pass

def unwrap_onion_layer(layer: Dict[str, str], node_private_key: PrivateKey) -> Dict[str, Any]:
    """Unwrap a single layer of an onion message."""
    try:
        logger.info(f"Unwrapping layer: {layer}")
        logger.info(f"Node private key type: {type(node_private_key)}")
        logger.info(f"Node private key bytes: {base64.b64encode(node_private_key.encode()).decode()}")
        logger.info(f"Node public key bytes: {base64.b64encode(node_private_key.public_key.encode()).decode()}")
        
        # Decode the layer components
        logger.info(f"Raw nonce: {layer['nonce']}")
        logger.info(f"Raw ciphertext: {layer['ciphertext'][:64]}...")
        logger.info(f"Raw ephemeral_pubkey: {layer['ephemeral_pubkey']}")
        
        nonce = base64.b64decode(layer['nonce'])
        ciphertext = base64.b64decode(layer['ciphertext'])
        ephemeral_pubkey = base64.b64decode(layer['ephemeral_pubkey'])
        
        logger.info(f"Decoded nonce (len={len(nonce)}): {base64.b64encode(nonce).decode()}")
        logger.info(f"Decoded ciphertext (len={len(ciphertext)}): {base64.b64encode(ciphertext).decode()[:64]}...")
        logger.info(f"Decoded ephemeral pubkey bytes (len={len(ephemeral_pubkey)}): {base64.b64encode(ephemeral_pubkey).decode()}")
        
        # Create the ephemeral public key object
        ephemeral_pubkey_obj = PublicKey(ephemeral_pubkey)
        logger.info(f"Created ephemeral PublicKey object type: {type(ephemeral_pubkey_obj)}")
        logger.info(f"Ephemeral PublicKey bytes: {base64.b64encode(ephemeral_pubkey_obj.encode()).decode()}")
        
        # Создаем Box для расшифровки
        logger.info(f"Creating Box for decryption with node private key and ephemeral public key")
        logger.info(f"Node private key type: {type(node_private_key)}")
        logger.info(f"Ephemeral public key type: {type(ephemeral_pubkey_obj)}")
        box = Box(node_private_key, ephemeral_pubkey_obj)
        logger.info("Created Box for decryption")
        
        # Decrypt the message
        decrypted = box.decrypt(ciphertext, nonce)
        logger.info(f"Decrypted message (len={len(decrypted)}): {base64.b64encode(decrypted).decode()}")
        
        # Parse the decrypted message
        message = json.loads(decrypted)
        logger.info(f"Parsed message: {message}")
        
        return message
        
    except Exception as e:
        logger.error(f"Error unwrapping layer: {str(e)}")
        raise CryptoError(f"Failed to unwrap onion layer: {str(e)}") 