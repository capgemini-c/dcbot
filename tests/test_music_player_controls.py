"""
Unit tests for MusicPlayer control methods.
Tests skip, stop, and playback control methods.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import MusicPlayer, Song


class TestMusicPlayerControls:
  """Test suite for MusicPlayer control methods."""
  
  def setup_method(self):
    """Create fresh MusicPlayer for each test."""
    self.mock_bot = MagicMock()
    self.mock_guild = MagicMock()
    self.mock_guild.id = 12345
    self.mock_guild.name = "Test Guild"
    
    self.player = MusicPlayer(self.mock_bot, self.mock_guild)
  
  def test_skip_when_playing(self):
    """Test skip() when a song is playing."""
    # Mock voice client that is playing
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = True
    self.player.voice_client = mock_vc
    
    result = self.player.skip()
    
    assert result is True
    mock_vc.stop.assert_called_once()
  
  def test_skip_when_not_playing(self):
    """Test skip() when nothing is playing."""
    # Mock voice client that is not playing
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = False
    self.player.voice_client = mock_vc
    
    result = self.player.skip()
    
    assert result is False
    mock_vc.stop.assert_not_called()
  
  def test_skip_when_no_voice_client(self):
    """Test skip() when not connected to voice channel."""
    self.player.voice_client = None
    
    result = self.player.skip()
    
    assert result is False
  
  def test_stop_with_voice_client(self):
    """Test stop() clears queue and stops playback."""
    # Add some songs to queue
    self.player.queue.add(Song(title="Song 1", url="http://example.com/1"))
    self.player.queue.add(Song(title="Song 2", url="http://example.com/2"))
    
    # Mock voice client
    mock_vc = MagicMock()
    self.player.voice_client = mock_vc
    
    self.player.stop()
    
    # Verify queue is cleared
    assert len(self.player.queue) == 0
    assert self.player.queue.current is None
    
    # Verify voice client stop was called
    mock_vc.stop.assert_called_once()
  
  def test_stop_without_voice_client(self):
    """Test stop() without voice client (should not error)."""
    # Add some songs to queue
    self.player.queue.add(Song(title="Song 1", url="http://example.com/1"))
    self.player.queue.add(Song(title="Song 2", url="http://example.com/2"))
    
    self.player.voice_client = None
    
    # Should not raise exception
    self.player.stop()
    
    # Verify queue is still cleared
    assert len(self.player.queue) == 0
  
  def test_stop_clears_current_song(self):
    """Test stop() clears the current song."""
    # Set current song
    current_song = Song(title="Current", url="http://example.com/1")
    self.player.queue.current = current_song
    
    # Add songs to queue
    self.player.queue.add(Song(title="Next", url="http://example.com/2"))
    
    self.player.stop()
    
    # Verify everything is cleared
    assert self.player.queue.current is None
    assert len(self.player.queue) == 0
    assert self.player.queue.is_empty() is True


class TestMusicQueueSkipTo:
  """Test suite for MusicQueue.skip_to() edge cases."""
  
  def test_skip_to_first_position(self):
    """Test skipping to position 1 (next song)."""
    from music import MusicQueue
    queue = MusicQueue()
    
    song1 = Song(title="Song 1", url="http://example.com/1")
    song2 = Song(title="Song 2", url="http://example.com/2")
    song3 = Song(title="Song 3", url="http://example.com/3")
    
    queue.add(song1)
    queue.add(song2)
    queue.add(song3)
    
    result = queue.skip_to(1)
    
    assert result is True
    assert len(queue) == 3  # No songs removed (position 1 is next)
  
  def test_skip_to_middle_position(self):
    """Test skipping to middle of queue."""
    from music import MusicQueue
    queue = MusicQueue()
    
    for i in range(5):
      queue.add(Song(title=f"Song {i+1}", url=f"http://example.com/{i+1}"))
    
    result = queue.skip_to(3)
    
    assert result is True
    assert len(queue) == 3  # Removed first 2 songs
  
  def test_skip_to_last_position(self):
    """Test skipping to last song in queue."""
    from music import MusicQueue
    queue = MusicQueue()
    
    for i in range(5):
      queue.add(Song(title=f"Song {i+1}", url=f"http://example.com/{i+1}"))
    
    result = queue.skip_to(5)
    
    assert result is True
    assert len(queue) == 1  # Only last song remains
  
  def test_skip_to_invalid_position_zero(self):
    """Test skipping to position 0 (invalid)."""
    from music import MusicQueue
    queue = MusicQueue()
    
    queue.add(Song(title="Song 1", url="http://example.com/1"))
    
    result = queue.skip_to(0)
    
    assert result is False
    assert len(queue) == 1  # Queue unchanged
  
  def test_skip_to_invalid_position_negative(self):
    """Test skipping to negative position (invalid)."""
    from music import MusicQueue
    queue = MusicQueue()
    
    queue.add(Song(title="Song 1", url="http://example.com/1"))
    
    result = queue.skip_to(-1)
    
    assert result is False
    assert len(queue) == 1  # Queue unchanged
  
  def test_skip_to_position_beyond_queue(self):
    """Test skipping to position beyond queue length."""
    from music import MusicQueue
    queue = MusicQueue()
    
    queue.add(Song(title="Song 1", url="http://example.com/1"))
    queue.add(Song(title="Song 2", url="http://example.com/2"))
    
    result = queue.skip_to(10)
    
    assert result is False
    assert len(queue) == 2  # Queue unchanged
  
  def test_skip_to_empty_queue(self):
    """Test skipping when queue is empty."""
    from music import MusicQueue
    queue = MusicQueue()
    
    result = queue.skip_to(1)
    
    assert result is False
