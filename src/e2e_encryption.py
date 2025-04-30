"""
Модуль end-to-end шифрования

Реализует функционал для безопасного обмена сообщениями между пользователями.
"""

import os
import json
import base64
from typing import Dict, Optional, Tuple
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.exceptions import InvalidKey

class E2EEncryptionError(Exception):
    """Base exception for E2E encryption errors"""
    pass

class KeyGenerationError(E2EEncryptionError):
    """Error during key generation"""
    pass

class KeyLoadError(E2EEncryptionError):
    """Error during key loading"""
    pass

class PeerKeyError(E2EEncryptionError):
    """Error related to peer key operations"""
    pass

class E2EEncryption:
    """
    Реализует end-to-end шифрование для безопасного обмена сообщениями
    """
    
    def __init__(self, keys_dir: str = ".keys"):
        """
        Инициализирует систему шифрования
        
        Args:
            keys_dir (str): Директория для хранения ключей
        """
        self.keys_dir = Path(keys_dir)
        self.private_key: Optional[rsa.RSAPrivateKey] = None
        self.public_key: Optional[rsa.RSAPublicKey] = None
        self.peer_keys: Dict[str, rsa.RSAPublicKey] = {}
        
        # Создаем директорию для ключей если её нет
        self.keys_dir.mkdir(exist_ok=True)
        
    def generate_keys(self, key_size: int = 2048) -> None:
        """Generate new RSA key pair"""
        try:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size
            )
            self.public_key = self.private_key.public_key()
            
            # Save keys to files
            private_pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            with open(self.keys_dir / "private.pem", "wb") as f:
                f.write(private_pem)
            with open(self.keys_dir / "public.pem", "wb") as f:
                f.write(public_pem)
                
        except Exception as e:
            raise KeyGenerationError(f"Failed to generate keys: {str(e)}")

    def load_keys(self) -> None:
        """Load existing keys from files"""
        try:
            with open(self.keys_dir / "private.pem", "rb") as f:
                private_pem = f.read()
            with open(self.keys_dir / "public.pem", "rb") as f:
                public_pem = f.read()
                
            self.private_key = load_pem_private_key(private_pem, password=None)
            self.public_key = load_pem_public_key(public_pem)
            
            # Load peer keys if they exist
            peer_keys_file = self.keys_dir / "peer_keys.json"
            if peer_keys_file.exists():
                with open(peer_keys_file, "r") as f:
                    peer_keys_data = json.load(f)
                    
                for peer_id, key_b64 in peer_keys_data.items():
                    self.add_peer_key(peer_id, key_b64)
                    
        except FileNotFoundError:
            raise KeyLoadError("Key files not found")
        except Exception as e:
            raise KeyLoadError(f"Failed to load keys: {str(e)}")

    def get_public_key(self) -> str:
        """Get base64 encoded public key"""
        if not self.public_key:
            raise KeyLoadError("No public key available")
        
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(public_pem).decode()

    def add_peer_key(self, peer_id: str, public_key_b64: str) -> None:
        """Add a peer's public key"""
        try:
            public_pem = base64.b64decode(public_key_b64)
            peer_key = load_pem_public_key(public_pem)
            if not isinstance(peer_key, rsa.RSAPublicKey):
                raise ValueError("Invalid key type")
            self.peer_keys[peer_id] = peer_key
            self._save_peer_keys()
        except Exception as e:
            raise PeerKeyError(f"Failed to add peer key: {str(e)}")

    def remove_peer_key(self, peer_id: str) -> None:
        """Remove a peer's public key"""
        try:
            del self.peer_keys[peer_id]
            self._save_peer_keys()
        except KeyError:
            raise PeerKeyError(f"No key found for peer {peer_id}")

    def encrypt_message(self, peer_id: str, message: str) -> str:
        """Encrypt a message for a specific peer"""
        if peer_id not in self.peer_keys:
            raise PeerKeyError(f"No key found for peer {peer_id}")
        
        try:
            message_bytes = message.encode('utf-8')
            encrypted = self.peer_keys[peer_id].encrypt(
                message_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            raise E2EEncryptionError(f"Failed to encrypt message: {str(e)}")

    def decrypt_message(self, peer_id: str, encrypted_b64: str) -> str:
        """Decrypt a message from a specific peer
        
        Args:
            peer_id: ID of the peer who sent the message
            encrypted_b64: Base64 encoded encrypted message
            
        Returns:
            Decrypted message as string
            
        Raises:
            KeyLoadError: If private key is not available
            E2EEncryptionError: If decryption fails
        """
        if not self.private_key:
            raise KeyLoadError("No private key available")
        
        try:
            encrypted = base64.b64decode(encrypted_b64)
            decrypted = self.private_key.decrypt(
                encrypted,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return decrypted.decode('utf-8')
        except Exception as e:
            raise E2EEncryptionError(f"Failed to decrypt message from {peer_id}: {str(e)}")

    def _save_peer_keys(self) -> None:
        """Save peer public keys to file"""
        peer_keys_data = {}
        
        for peer_id, key in self.peer_keys.items():
            key_pem = key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            peer_keys_data[peer_id] = base64.b64encode(key_pem).decode()
            
        with open(self.keys_dir / "peer_keys.json", "w") as f:
            json.dump(peer_keys_data, f, indent=4) 