"""
Модуль для цифровых подписей сообщений

Использует Ed25519 для создания и проверки подписей.
"""

from typing import Tuple, Optional
import nacl.signing
import nacl.encoding
import base64
import json
from datetime import datetime

class SignatureError(Exception):
    """Базовый класс для ошибок подписи"""
    pass

class SignatureVerificationError(SignatureError):
    """Ошибка проверки подписи"""
    pass

class MessageSigner:
    def __init__(self):
        """Инициализация подписчика"""
        self._signing_key = nacl.signing.SigningKey.generate()
        self._verify_key = self._signing_key.verify_key
        
    def get_public_key(self) -> str:
        """Получить публичный ключ в base64"""
        return base64.b64encode(self._verify_key.encode()).decode()
        
    def sign_message(self, message: str) -> Tuple[str, str]:
        """
        Подписать сообщение
        
        Args:
            message (str): Сообщение для подписи
            
        Returns:
            Tuple[str, str]: (подпись, публичный ключ)
        """
        try:
            # Создаем подпись
            signature = self._signing_key.sign(message.encode())
            
            # Кодируем подпись в base64
            signature_b64 = base64.b64encode(signature.signature).decode()
            
            return signature_b64, self.get_public_key()
            
        except Exception as e:
            raise SignatureError(f"Ошибка при подписи сообщения: {e}")
            
    @staticmethod
    def verify_signature(message: str, signature: str, public_key: str) -> bool:
        """
        Проверить подпись сообщения
        
        Args:
            message (str): Исходное сообщение
            signature (str): Подпись в base64
            public_key (str): Публичный ключ в base64
            
        Returns:
            bool: True если подпись верна
        """
        try:
            # Декодируем ключ и подпись
            verify_key = nacl.signing.VerifyKey(
                base64.b64decode(public_key)
            )
            signature_bytes = base64.b64decode(signature)
            
            # Проверяем подпись
            verify_key.verify(message.encode(), signature_bytes)
            return True
            
        except Exception as e:
            raise SignatureVerificationError(f"Ошибка проверки подписи: {e}")
            
    def sign_json_message(self, data: dict) -> dict:
        """
        Подписать JSON сообщение
        
        Args:
            data (dict): Данные для подписи
            
        Returns:
            dict: Данные с подписью
        """
        # Добавляем timestamp
        data['timestamp'] = datetime.utcnow().isoformat()
        
        # Сериализуем в JSON
        message = json.dumps(data, sort_keys=True)
        
        # Подписываем
        signature, public_key = self.sign_message(message)
        
        # Добавляем подпись и ключ
        data['signature'] = signature
        data['public_key'] = public_key
        
        return data
        
    @staticmethod
    def verify_json_message(data: dict) -> bool:
        """
        Проверить подпись JSON сообщения
        
        Args:
            data (dict): Данные с подписью
            
        Returns:
            bool: True если подпись верна
        """
        try:
            # Извлекаем подпись и ключ
            signature = data.pop('signature')
            public_key = data.pop('public_key')
            
            # Сериализуем в JSON
            message = json.dumps(data, sort_keys=True)
            
            # Проверяем подпись
            return MessageSigner.verify_signature(message, signature, public_key)
            
        except Exception as e:
            raise SignatureVerificationError(f"Ошибка проверки JSON сообщения: {e}") 