"""This folder holds objects that are instantiated by the CoreEngine to 'manage' certain other objects such as signals."""

from .scratch_manager import ScratchManager
from .signal_manager import SignalManager

__all__ = ['ScratchManager', 'SignalManager']
