"""Adapters between the drill and a room transport."""

from firedrill.adapters.base import AdapterError, NotSupported, RoomBus
from firedrill.adapters.local import LocalAdapter
from firedrill.adapters.mattermost import MattermostAdapter
from firedrill.adapters.switch import SwitchAdapter

__all__ = [
    "AdapterError",
    "LocalAdapter",
    "NotSupported",
    "MattermostAdapter",
    "RoomBus",
    "SwitchAdapter",
]
