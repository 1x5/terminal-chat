"""
Модуль для управления репутацией пиров

Реализует систему оценки надежности узлов и защиту от атак.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("securetermchat.reputation")

class ReputationEvent(Enum):
    """Типы событий, влияющих на репутацию"""
    MESSAGE_RECEIVED = 1      # Получено сообщение
    MESSAGE_SENT = 2         # Отправлено сообщение
    INVALID_SIGNATURE = -5   # Неверная подпись
    INVALID_ENCRYPTION = -5  # Неверное шифрование
    CONNECTION_DROPPED = -2  # Разрыв соединения
    SPAM_DETECTED = -10      # Обнаружен спам
    SYBIL_ATTACK = -20       # Обнаружена Sybil-атака

@dataclass
class PeerStats:
    """Статистика пира"""
    reputation: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    last_seen: datetime = datetime.utcnow()
    events: List[Dict] = None
    
    def __post_init__(self):
        if self.events is None:
            self.events = []
            
    def to_dict(self) -> dict:
        return {
            "reputation": self.reputation,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "last_seen": self.last_seen.isoformat(),
            "events": self.events
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'PeerStats':
        return cls(
            reputation=data["reputation"],
            messages_sent=data["messages_sent"],
            messages_received=data["messages_received"],
            last_seen=datetime.fromisoformat(data["last_seen"]),
            events=data["events"]
        )

class ReputationManager:
    def __init__(self, config_path: str = ".reputation"):
        """
        Инициализация менеджера репутации
        
        Args:
            config_path (str): Путь к файлу с данными репутации
        """
        self.config_path = config_path
        self.peers: Dict[str, PeerStats] = {}
        self.min_reputation = -50.0  # Минимальная репутация
        self.max_reputation = 100.0  # Максимальная репутация
        self.decay_rate = 0.1        # Скорость уменьшения репутации
        self.load_data()
        
    def load_data(self) -> None:
        """Загрузка данных о репутации"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                for peer_id, stats in data.items():
                    self.peers[peer_id] = PeerStats.from_dict(stats)
        except FileNotFoundError:
            logger.info("No reputation data found, starting fresh")
            
    def save_data(self) -> None:
        """Сохранение данных о репутации"""
        data = {peer_id: stats.to_dict() for peer_id, stats in self.peers.items()}
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)
            
    def update_reputation(self, peer_id: str, event: ReputationEvent) -> None:
        """
        Обновление репутации пира
        
        Args:
            peer_id (str): ID пира
            event (ReputationEvent): Событие
        """
        if peer_id not in self.peers:
            self.peers[peer_id] = PeerStats()
            
        stats = self.peers[peer_id]
        
        # Обновляем статистику
        if event == ReputationEvent.MESSAGE_RECEIVED:
            stats.messages_received += 1
        elif event == ReputationEvent.MESSAGE_SENT:
            stats.messages_sent += 1
            
        # Обновляем репутацию
        stats.reputation += event.value
        
        # Ограничиваем репутацию
        stats.reputation = max(self.min_reputation, min(self.max_reputation, stats.reputation))
        
        # Обновляем время последнего контакта
        stats.last_seen = datetime.utcnow()
        
        # Добавляем событие в историю
        stats.events.append({
            "type": event.name,
            "value": event.value,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Ограничиваем историю событий
        if len(stats.events) > 100:
            stats.events = stats.events[-100:]
            
        # Сохраняем изменения
        self.save_data()
        
    def get_reputation(self, peer_id: str) -> float:
        """Получить текущую репутацию пира"""
        if peer_id not in self.peers:
            return 0.0
        return self.peers[peer_id].reputation
        
    def is_trusted(self, peer_id: str) -> bool:
        """Проверить, является ли пир доверенным"""
        return self.get_reputation(peer_id) >= 0
        
    def decay_reputation(self) -> None:
        """Уменьшение репутации со временем"""
        now = datetime.utcnow()
        for peer_id, stats in self.peers.items():
            # Уменьшаем репутацию для неактивных пиров
            if now - stats.last_seen > timedelta(hours=24):
                stats.reputation -= self.decay_rate
                stats.reputation = max(self.min_reputation, stats.reputation)
                
        self.save_data()
        
    def get_peer_stats(self, peer_id: str) -> Optional[PeerStats]:
        """Получить статистику пира"""
        return self.peers.get(peer_id)
        
    def get_top_peers(self, limit: int = 10) -> List[tuple]:
        """Получить список пиров с наивысшей репутацией"""
        return sorted(
            [(peer_id, stats.reputation) for peer_id, stats in self.peers.items()],
            key=lambda x: x[1],
            reverse=True
        )[:limit] 