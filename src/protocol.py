"""
Протокол обмена сообщениями для SecureTermChat

Определяет форматы сообщений и типы сообщений для обмена между узлами.
"""

from enum import Enum
from typing import Dict, Any, Optional, Type, ClassVar
import json

class MessageType(Enum):
    """Типы сообщений в протоколе"""
    HANDSHAKE = "handshake"      # Приветствие при установке соединения
    ONION = "onion"             # Сообщение с луковой маршрутизацией
    PING = "ping"               # Проверка соединения
    PONG = "pong"               # Ответ на пинг
    ERROR = "error"             # Сообщение об ошибке
    ROUTE_UPDATE = "route"      # Обновление маршрута
    NODE_INFO = "node_info"     # Информация об узле

class Message:
    """Базовый класс для всех сообщений"""
    
    # Словарь для маппинга типов сообщений на классы
    _message_classes: ClassVar[Dict[str, Type['Message']]] = {}
    
    def __init__(self, msg_type: MessageType, data: Dict[str, Any]):
        self.type = msg_type
        self.data = data
        
    def to_json(self) -> str:
        """Преобразует сообщение в JSON"""
        return json.dumps({
            "type": self.type.value,
            "data": self.data
        })
        
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Создает сообщение из JSON"""
        data = json.loads(json_str)
        msg_type = MessageType(data["type"])
        
        # Получаем класс сообщения по типу
        message_class = cls._message_classes.get(msg_type.value, cls)
        
        # Создаем экземпляр нужного класса через from_data
        return message_class.from_data(data["data"])
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'Message':
        """Создает сообщение из данных"""
        return cls(cls.type, data)
        
    def __init_subclass__(cls, **kwargs):
        """Регистрирует подклассы сообщений"""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'type'):
            Message._message_classes[cls.type.value] = cls

class HandshakeMessage(Message):
    """Сообщение приветствия"""
    
    type = MessageType.HANDSHAKE
    
    def __init__(self, public_key: str, node_id: str, version: str):
        super().__init__(self.type, {
            "public_key": public_key,
            "node_id": node_id,
            "version": version
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'HandshakeMessage':
        return cls(
            public_key=data["public_key"],
            node_id=data["node_id"],
            version=data["version"]
        )

class OnionMessage(Message):
    """Сообщение с луковой маршрутизацией"""
    
    type = MessageType.ONION
    
    def __init__(self, layer: Dict[str, Any], next_hop: Optional[str] = None):
        super().__init__(self.type, {
            "layer": layer,
            "next_hop": next_hop
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'OnionMessage':
        return cls(
            layer=data["layer"],
            next_hop=data.get("next_hop")
        )

class PingMessage(Message):
    """Сообщение проверки соединения"""
    
    type = MessageType.PING
    
    def __init__(self, timestamp: float):
        super().__init__(self.type, {
            "timestamp": timestamp
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'PingMessage':
        return cls(timestamp=data["timestamp"])

class PongMessage(Message):
    """Ответ на проверку соединения"""
    
    type = MessageType.PONG
    
    def __init__(self, timestamp: float, latency: float):
        super().__init__(self.type, {
            "timestamp": timestamp,
            "latency": latency
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'PongMessage':
        return cls(
            timestamp=data["timestamp"],
            latency=data["latency"]
        )

class ErrorMessage(Message):
    """Сообщение об ошибке"""
    
    type = MessageType.ERROR
    
    def __init__(self, code: str, message: str):
        super().__init__(self.type, {
            "code": code,
            "message": message
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'ErrorMessage':
        return cls(
            code=data["code"],
            message=data["message"]
        )

class RouteUpdateMessage(Message):
    """Сообщение обновления маршрута"""
    
    type = MessageType.ROUTE_UPDATE
    
    def __init__(self, route: Dict[str, Any]):
        super().__init__(self.type, {
            "route": route
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'RouteUpdateMessage':
        return cls(route=data["route"])

class NodeInfoMessage(Message):
    """Информация об узле"""
    
    type = MessageType.NODE_INFO
    
    def __init__(self, node_id: str, public_key: str, address: str, 
                 connections: int, version: str):
        super().__init__(self.type, {
            "node_id": node_id,
            "public_key": public_key,
            "address": address,
            "connections": connections,
            "version": version
        })
        
    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> 'NodeInfoMessage':
        return cls(
            node_id=data["node_id"],
            public_key=data["public_key"],
            address=data["address"],
            connections=data["connections"],
            version=data["version"]
        ) 