"""
Unit tests for PlayerManager class.
Tests player lifecycle management without Discord dependencies.
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock

# Add parent directory to path to import music module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import PlayerManager, MusicPlayer


class TestPlayerManager:
    """Test suite for PlayerManager class."""
    
    def setup_method(self):
        """Create a fresh PlayerManager for each test."""
        self.manager = PlayerManager()
        
        # Create mock bot and guild
        self.mock_bot = MagicMock()
        self.mock_guild = MagicMock()
        self.mock_guild.id = 12345
        self.mock_guild.name = "Test Guild"
    
    def test_initialization(self):
        """Test that PlayerManager initializes with empty dict."""
        assert len(self.manager._players) == 0
    
    def test_get_nonexistent_player(self):
        """Test getting a player that doesn't exist returns None."""
        player = self.manager.get(999)
        assert player is None
    
    def test_create_player(self):
        """Test creating a new player."""
        player = self.manager.create_player(self.mock_bot, self.mock_guild)
        
        assert player is not None
        assert isinstance(player, MusicPlayer)
        assert player.guild == self.mock_guild
        assert player.bot == self.mock_bot
        assert len(self.manager._players) == 1
    
    def test_get_existing_player(self):
        """Test getting a player that exists."""
        # Create player first
        player1 = self.manager.create_player(self.mock_bot, self.mock_guild)
        
        # Get it back
        player2 = self.manager.get(self.mock_guild.id)
        
        assert player2 is player1  # Same instance
    
    def test_get_or_create_when_not_exists(self):
        """Test get_or_create creates player when it doesn't exist."""
        player = self.manager.get_or_create(self.mock_bot, self.mock_guild)
        
        assert player is not None
        assert isinstance(player, MusicPlayer)
        assert len(self.manager._players) == 1
    
    def test_get_or_create_when_exists(self):
        """Test get_or_create returns existing player."""
        # Create player first
        player1 = self.manager.create_player(self.mock_bot, self.mock_guild)
        
        # Get or create should return same instance
        player2 = self.manager.get_or_create(self.mock_bot, self.mock_guild)
        
        assert player2 is player1
        assert len(self.manager._players) == 1  # Still only one
    
    def test_remove_player(self):
        """Test removing a player."""
        # Create player
        self.manager.create_player(self.mock_bot, self.mock_guild)
        assert len(self.manager._players) == 1
        
        # Remove it
        self.manager.remove(self.mock_guild.id)
        assert len(self.manager._players) == 0
    
    def test_remove_nonexistent_player(self):
        """Test removing a player that doesn't exist (should not error)."""
        self.manager.remove(999)  # Should not raise exception
        assert len(self.manager._players) == 0
    
    def test_multiple_guilds(self):
        """Test managing players for multiple guilds."""
        # Create second guild
        mock_guild2 = MagicMock()
        mock_guild2.id = 67890
        mock_guild2.name = "Test Guild 2"
        
        # Create players for both guilds
        player1 = self.manager.create_player(self.mock_bot, self.mock_guild)
        player2 = self.manager.create_player(self.mock_bot, mock_guild2)
        
        assert len(self.manager._players) == 2
        assert self.manager.get(self.mock_guild.id) is player1
        assert self.manager.get(mock_guild2.id) is player2
    
    def test_has_player_true(self):
        """Test has_player returns True when player exists."""
        self.manager.create_player(self.mock_bot, self.mock_guild)
        assert self.manager.has_player(self.mock_guild.id) is True
    
    def test_has_player_false(self):
        """Test has_player returns False when player doesn't exist."""
        assert self.manager.has_player(999) is False
    
    def test_count_players(self):
        """Test counting number of active players."""
        assert self.manager.count() == 0
        
        self.manager.create_player(self.mock_bot, self.mock_guild)
        assert self.manager.count() == 1
        
        mock_guild2 = MagicMock()
        mock_guild2.id = 67890
        self.manager.create_player(self.mock_bot, mock_guild2)
        assert self.manager.count() == 2
        
        self.manager.remove(self.mock_guild.id)
        assert self.manager.count() == 1
