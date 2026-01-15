"""
Unit tests for DownloadBufferManager class.
Tests download buffer logic without Discord dependencies.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import DownloadBufferManager, Song, MusicQueue


class TestDownloadBufferManager:
    """Test suite for DownloadBufferManager class."""
    
    def setup_method(self):
        """Create fresh instances for each test."""
        self.manager = DownloadBufferManager(buffer_size=3)
        self.queue = MusicQueue()
    
    def test_initialization(self):
        """Test that DownloadBufferManager initializes correctly."""
        assert self.manager.buffer_size == 3
        assert len(self.manager.currently_downloading) == 0
    
    def test_is_downloading_false(self):
        """Test is_downloading when nothing is downloading."""
        song = Song(title="Test Song", url="http://example.com/1")
        assert self.manager.is_downloading(song) is False
    
    def test_is_downloading_true(self):
        """Test is_downloading when song is being downloaded."""
        song = Song(title="Test Song", url="http://example.com/1")
        self.manager.currently_downloading.add(song.title)
        assert self.manager.is_downloading(song) is True
    
    def test_get_downloading_count(self):
        """Test getting count of currently downloading songs."""
        assert self.manager.get_downloading_count() == 0
        
        self.manager.currently_downloading.add("Song 1")
        assert self.manager.get_downloading_count() == 1
        
        self.manager.currently_downloading.add("Song 2")
        assert self.manager.get_downloading_count() == 2
    
    def test_mark_downloading(self):
        """Test marking a song as downloading."""
        song = Song(title="Test Song", url="http://example.com/1")
        self.manager.mark_downloading(song)
        
        assert song.title in self.manager.currently_downloading
        assert self.manager.is_downloading(song) is True
    
    def test_unmark_downloading(self):
        """Test unmarking a song as downloading."""
        song = Song(title="Test Song", url="http://example.com/1")
        self.manager.mark_downloading(song)
        self.manager.unmark_downloading(song)
        
        assert song.title not in self.manager.currently_downloading
        assert self.manager.is_downloading(song) is False
    
    def test_get_songs_to_download_empty_queue(self):
        """Test getting songs to download when queue is empty."""
        songs = self.manager.get_songs_to_download(self.queue)
        assert songs == []
    
    def test_get_songs_to_download_with_current(self):
        """Test getting songs including current song."""
        current = Song(title="Current", url="http://example.com/1")
        song1 = Song(title="Song 1", url="http://example.com/2")
        song2 = Song(title="Song 2", url="http://example.com/3")
        
        self.queue.add(song1)
        self.queue.add(song2)
        self.queue.current = current
        
        songs = self.manager.get_songs_to_download(self.queue)
        
        # Should get current + next 2 (buffer_size = 3)
        assert len(songs) == 3
        assert current in songs
        assert song1 in songs
        assert song2 in songs
    
    def test_get_songs_to_download_no_current(self):
        """Test getting songs when no current song."""
        song1 = Song(title="Song 1", url="http://example.com/1")
        song2 = Song(title="Song 2", url="http://example.com/2")
        song3 = Song(title="Song 3", url="http://example.com/3")
        song4 = Song(title="Song 4", url="http://example.com/4")
        
        self.queue.add(song1)
        self.queue.add(song2)
        self.queue.add(song3)
        self.queue.add(song4)
        
        songs = self.manager.get_songs_to_download(self.queue)
        
        # Should get next 3 (buffer_size = 3)
        assert len(songs) == 3
        assert song1 in songs
        assert song2 in songs
        assert song3 in songs
        assert song4 not in songs
    
    def test_get_songs_to_download_only_undownloaded(self):
        """Test that only undownloaded songs are returned."""
        import tempfile
        
        # Create temporary file for song1 to make it "downloaded"
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(b"fake audio")
        
        try:
            song1 = Song(title="Downloaded", url="http://example.com/1", local_file=tmp_path)
            song2 = Song(title="Not Downloaded", url="http://example.com/2")
            song3 = Song(title="Also Not Downloaded", url="http://example.com/3")
            
            self.queue.add(song1)
            self.queue.add(song2)
            self.queue.add(song3)
            
            songs = self.manager.get_songs_to_download(self.queue)
            
            # Should only get undownloaded songs
            assert song1 not in songs
            assert song2 in songs
            assert song3 in songs
        finally:
            # Cleanup
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_get_songs_to_cleanup(self):
        """Test getting songs that should be cleaned up."""
        import tempfile
        import os
        
        # Create songs beyond buffer with actual downloaded files
        temp_files = []
        songs_in_queue = []
        
        try:
            for i in range(10):
                # Create temporary file for each song
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name
                    tmp.write(b"fake audio")
                    temp_files.append(tmp_path)
                
                song = Song(title=f"Song {i}", url=f"http://example.com/{i}", local_file=tmp_path)
                songs_in_queue.append(song)
                self.queue.add(song)
            
            # Set current
            self.queue.current = Song(title="Current", url="http://example.com/current")
            
            songs_to_cleanup = self.manager.get_songs_to_cleanup(self.queue)
            
            # With buffer_size=3 and current song, should cleanup songs beyond position 2
            # (current + next 2 songs = buffer, rest should be cleaned)
            expected_cleanup_count = len(songs_in_queue) - (self.manager.buffer_size - 1)
            assert len(songs_to_cleanup) == expected_cleanup_count
        finally:
            # Cleanup temp files
            for path in temp_files:
                if os.path.exists(path):
                    os.unlink(path)
    
    def test_custom_buffer_size(self):
        """Test creating manager with custom buffer size."""
        manager = DownloadBufferManager(buffer_size=5)
        assert manager.buffer_size == 5
        
        # Add 10 songs
        for i in range(10):
            self.queue.add(Song(title=f"Song {i}", url=f"http://example.com/{i}"))
        
        songs = manager.get_songs_to_download(self.queue)
        assert len(songs) == 5  # Should respect custom buffer size
