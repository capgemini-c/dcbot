"""
Unit tests for helper functions in bot.py.
Tests random selection logic without Discord dependencies.
"""

import pytest
import sys
import os

# Add parent directory to path to import bot module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to mock the Discord imports before importing bot
import unittest.mock as mock
sys.modules['discord'] = mock.MagicMock()
sys.modules['discord.ext'] = mock.MagicMock()
sys.modules['discord.ext.commands'] = mock.MagicMock()


class TestRandomMessageSelection:
    """Test suite for random message selection without repetition."""
    
    def setup_method(self):
        """Reset the used indices before each test."""
        # Import after mocking
        import bot
        bot.used_messages_indices = set()
        bot.used_skanduotes_indices = set()
        self.bot = bot
    
    def test_get_random_message_no_repetition(self):
        """Test that messages don't repeat until all are used."""
        messages_count = len(self.bot.MESSAGES)
        selected_messages = []
        
        # Get all messages
        for _ in range(messages_count):
            msg = self.bot.get_random_message()
            selected_messages.append(msg)
        
        # All messages should be unique
        assert len(set(selected_messages)) == messages_count
        
        # All messages should be from the MESSAGES list
        for msg in selected_messages:
            assert msg in self.bot.MESSAGES
    
    def test_get_random_message_resets_after_all_used(self):
        """Test that selection resets after all messages are used."""
        messages_count = len(self.bot.MESSAGES)
        
        # Use all messages
        for _ in range(messages_count):
            self.bot.get_random_message()
        
        # Indices should be full
        assert len(self.bot.used_messages_indices) == messages_count
        
        # Get one more message - should reset
        msg = self.bot.get_random_message()
        
        # Should have reset and selected one
        assert len(self.bot.used_messages_indices) == 1
        assert msg in self.bot.MESSAGES
    
    def test_get_random_skanduote_no_repetition(self):
        """Test that skanduotes don't repeat until all are used."""
        skanduotes_count = len(self.bot.SKANDUOTES)
        selected_indices = []
        
        # Get all skanduotes
        for _ in range(skanduotes_count):
            skanduote = self.bot.get_random_skanduote()
            # Find the index
            for i, s in enumerate(self.bot.SKANDUOTES):
                if s == skanduote:
                    selected_indices.append(i)
                    break
        
        # All indices should be unique
        assert len(set(selected_indices)) == skanduotes_count
    
    def test_get_random_skanduote_resets_after_all_used(self):
        """Test that skanduote selection resets after all are used."""
        skanduotes_count = len(self.bot.SKANDUOTES)
        
        # Use all skanduotes
        for _ in range(skanduotes_count):
            self.bot.get_random_skanduote()
        
        # Indices should be full
        assert len(self.bot.used_skanduotes_indices) == skanduotes_count
        
        # Get one more - should reset
        skanduote = self.bot.get_random_skanduote()
        
        # Should have reset and selected one
        assert len(self.bot.used_skanduotes_indices) == 1
        assert skanduote in self.bot.SKANDUOTES
    
    def test_random_selection_independence(self):
        """Test that message and skanduote selections are independent."""
        # Use some messages
        self.bot.get_random_message()
        self.bot.get_random_message()
        message_indices = len(self.bot.used_messages_indices)
        
        # Use some skanduotes
        self.bot.get_random_skanduote()
        skanduote_indices = len(self.bot.used_skanduotes_indices)
        
        # Should be independent
        assert message_indices == 2
        assert skanduote_indices == 1
