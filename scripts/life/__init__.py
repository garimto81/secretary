"""
Life Event Management Module for Secretary Phase 5

Components:
- lunar_converter: Lunar/Solar calendar conversion
- event_manager: Life event management and reminders
"""

from scripts.life.lunar_converter import lunar_to_solar, solar_to_lunar
from scripts.life.event_manager import LifeEvent, LifeEventManager

__all__ = [
    "lunar_to_solar",
    "solar_to_lunar",
    "LifeEvent",
    "LifeEventManager",
]
