"""
Unit tests for Song dataclass.
Tests song properties and methods without Discord dependencies.
"""

import pytest
import sys
import os

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
            requester="TestUser",
        )

        assert song.title == "Test Song"
        assert song.url == "http://example.com/song"
        assert song.duration == 180
        assert song.requester == "TestUser"
        assert song.thumbnail is None

    def test_song_default_values(self):
        """Test song initialization with defaults."""
        song = Song(title="Test", url="http://example.com/1")

        assert song.duration is None
        assert song.thumbnail is None
        assert song.requester is None

    def test_duration_str_with_seconds_only(self):
        """Test duration string formatting for short songs."""
        song = Song(
            title="Short", url="http://example.com/1", duration=45
        )
        assert song.duration_str == "0:45"

    def test_duration_str_with_minutes(self):
        """Test duration string formatting with minutes."""
        song = Song(
            title="Medium", url="http://example.com/1", duration=195
        )
        assert song.duration_str == "3:15"

    def test_duration_str_with_hours(self):
        """Test duration string formatting with hours."""
        song = Song(
            title="Long", url="http://example.com/1", duration=3665
        )
        assert song.duration_str == "1:01:05"

    def test_duration_str_with_no_duration(self):
        """Test duration string when duration is None."""
        song = Song(title="Unknown", url="http://example.com/1")
        assert song.duration_str == "Unknown"

    def test_song_with_thumbnail(self):
        """Test song with thumbnail URL."""
        song = Song(
            title="Test",
            url="http://example.com/1",
            thumbnail="http://example.com/thumb.jpg",
        )
        assert song.thumbnail == "http://example.com/thumb.jpg"
