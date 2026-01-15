"""
Unit tests for MusicQueue class.
Tests core queue operations without Discord dependencies.
"""

import pytest
from collections import deque
import sys
import os

# Add parent directory to path to import music module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import MusicQueue, Song


class TestMusicQueue:
    """Test suite for MusicQueue class."""
    
    def test_queue_initialization(self):
        """Test that queue initializes with correct default values."""
        queue = MusicQueue()
        assert isinstance(queue.queue, deque)
        assert len(queue.queue) == 0
        assert queue.current is None
        assert queue.loop is False
    
    def test_add_song(self):
        """Test adding songs to the queue."""
        queue = MusicQueue()
        song1 = Song(title="Song 1", url="http://example.com/1")
        song2 = Song(title="Song 2", url="http://example.com/2")
        
        queue.add(song1)
        assert len(queue.queue) == 1
        assert queue.queue[0] == song1
        
        queue.add(song2)
        assert len(queue.queue) == 2
        assert queue.queue[1] == song2
    
    def test_next_without_loop(self):
        """Test getting next song without loop mode."""
        queue = MusicQueue()
        song1 = Song(title="Song 1", url="http://example.com/1")
        song2 = Song(title="Song 2", url="http://example.com/2")
        
        queue.add(song1)
        queue.add(song2)
        
        # Get first song
        next_song = queue.next()
        assert next_song == song1
        assert queue.current == song1
        assert len(queue.queue) == 1
        
        # Get second song
        next_song = queue.next()
        assert next_song == song2
        assert queue.current == song2
        assert len(queue.queue) == 0
        
        # Queue empty
        next_song = queue.next()
        assert next_song is None
        assert queue.current is None
    
    def test_next_with_loop(self):
        """Test getting next song with loop mode enabled."""
        queue = MusicQueue()
        song1 = Song(title="Song 1", url="http://example.com/1")
        song2 = Song(title="Song 2", url="http://example.com/2")
        
        queue.add(song1)
        queue.add(song2)
        
        # Get first song
        queue.next()
        assert queue.current == song1
        
        # Enable loop
        queue.loop = True
        
        # Next should return same song
        next_song = queue.next()
        assert next_song == song1
        assert queue.current == song1
        assert len(queue.queue) == 1  # Queue unchanged
    
    def test_skip_to_valid_position(self):
        """Test skipping to a valid position in queue."""
        queue = MusicQueue()
        songs = [
            Song(title=f"Song {i}", url=f"http://example.com/{i}")
            for i in range(1, 6)
        ]
        
        for song in songs:
            queue.add(song)
        
        # Skip to position 3 (1-indexed)
        result = queue.skip_to(3)
        
        assert result is True
        assert len(queue.queue) == 3  # Songs 3, 4, 5 remain
        assert queue.queue[0].title == "Song 3"
    
    def test_skip_to_invalid_position(self):
        """Test skipping to invalid positions."""
        queue = MusicQueue()
        songs = [
            Song(title=f"Song {i}", url=f"http://example.com/{i}")
            for i in range(1, 4)
        ]
        
        for song in songs:
            queue.add(song)
        
        # Position too low
        assert queue.skip_to(0) is False
        assert len(queue.queue) == 3  # Unchanged
        
        # Position too high
        assert queue.skip_to(10) is False
        assert len(queue.queue) == 3  # Unchanged
    
    def test_clear(self):
        """Test clearing the queue."""
        queue = MusicQueue()
        song1 = Song(title="Song 1", url="http://example.com/1")
        song2 = Song(title="Song 2", url="http://example.com/2")
        
        queue.add(song1)
        queue.add(song2)
        queue.next()  # Set current
        
        queue.clear()
        
        assert len(queue.queue) == 0
        assert queue.current is None
    
    def test_is_empty_with_no_songs(self):
        """Test is_empty when queue has no songs and no current."""
        queue = MusicQueue()
        assert queue.is_empty() is True
    
    def test_is_empty_with_current_song(self):
        """Test is_empty when queue has current song but empty queue."""
        queue = MusicQueue()
        song = Song(title="Song 1", url="http://example.com/1")
        queue.add(song)
        queue.next()  # This sets current
        
        # Queue is empty but current exists
        assert len(queue.queue) == 0
        assert queue.current is not None
        assert queue.is_empty() is False
    
    def test_is_empty_with_queued_songs(self):
        """Test is_empty when queue has songs."""
        queue = MusicQueue()
        song = Song(title="Song 1", url="http://example.com/1")
        queue.add(song)
        
        assert queue.is_empty() is False
    
    def test_len(self):
        """Test __len__ method."""
        queue = MusicQueue()
        assert len(queue) == 0
        
        queue.add(Song(title="Song 1", url="http://example.com/1"))
        assert len(queue) == 1
        
        queue.add(Song(title="Song 2", url="http://example.com/2"))
        assert len(queue) == 2
        
        queue.next()  # Remove one
        assert len(queue) == 1
