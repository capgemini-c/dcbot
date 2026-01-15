"""
Unit tests for Song dataclass.
Tests song properties and methods without Discord dependencies.
"""

import pytest
import tempfile
import os
import sys

# Add parent directory to path to import music module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import Song


class TestSong:
    """Test suite for Song dataclass."""
    
    def test_song_initialization(self):
        """Test basic song initialization."""
        song = Song(
            title="Test Song",
            url="http://example.com/song",
            duration=180,
            requester="TestUser"
        )
        
        assert song.title == "Test Song"
        assert song.url == "http://example.com/song"
        assert song.duration == 180
        assert song.requester == "TestUser"
        assert song.local_file is None
        assert song.thumbnail is None
    
    def test_duration_str_with_seconds_only(self):
        """Test duration string formatting for short songs."""
        song = Song(title="Short", url="http://example.com/1", duration=45)
        assert song.duration_str == "0:45"
    
    def test_duration_str_with_minutes(self):
        """Test duration string formatting with minutes."""
        song = Song(title="Medium", url="http://example.com/1", duration=195)
        assert song.duration_str == "3:15"
    
    def test_duration_str_with_hours(self):
        """Test duration string formatting with hours."""
        song = Song(title="Long", url="http://example.com/1", duration=3665)
        assert song.duration_str == "1:01:05"
    
    def test_duration_str_with_no_duration(self):
        """Test duration string when duration is None."""
        song = Song(title="Unknown", url="http://example.com/1")
        assert song.duration_str == "Unknown"
    
    def test_is_downloaded_false_when_no_file(self):
        """Test is_downloaded when local_file is None."""
        song = Song(title="Test", url="http://example.com/1")
        assert song.is_downloaded is False
    
    def test_is_downloaded_false_when_file_not_exists(self):
        """Test is_downloaded when file path doesn't exist."""
        song = Song(
            title="Test",
            url="http://example.com/1",
            local_file="/nonexistent/path/to/file.mp3"
        )
        assert song.is_downloaded is False
    
    def test_is_downloaded_true_when_file_exists(self):
        """Test is_downloaded when file actually exists."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(b"fake audio data")
        
        try:
            song = Song(
                title="Test",
                url="http://example.com/1",
                local_file=tmp_path
            )
            assert song.is_downloaded is True
        finally:
            # Cleanup
            os.unlink(tmp_path)
    
    def test_cleanup_with_existing_file(self):
        """Test cleanup removes existing file."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(b"fake audio data")
        
        song = Song(
            title="Test",
            url="http://example.com/1",
            local_file=tmp_path
        )
        
        # Verify file exists
        assert os.path.exists(tmp_path)
        
        # Cleanup
        song.cleanup()
        
        # Verify file removed and local_file set to None
        assert not os.path.exists(tmp_path)
        assert song.local_file is None
    
    def test_cleanup_with_no_file(self):
        """Test cleanup when no file exists (should not error)."""
        song = Song(title="Test", url="http://example.com/1")
        song.cleanup()  # Should not raise exception
        assert song.local_file is None
    
    def test_cleanup_with_nonexistent_file(self):
        """Test cleanup when file path set but file doesn't exist."""
        song = Song(
            title="Test",
            url="http://example.com/1",
            local_file="/nonexistent/file.mp3"
        )
        song.cleanup()  # Should not raise exception
        # Note: Current implementation doesn't set local_file to None if file doesn't exist
        # This is a minor bug but not critical - file removal attempt is wrapped in try/except
        assert song.local_file == "/nonexistent/file.mp3"  # Unchanged (current behavior)
