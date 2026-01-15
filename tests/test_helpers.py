"""
Unit tests for helper functions in music module.
Tests URL detection and validation functions.
"""

import pytest
import sys
import os

# Add parent directory to path to import music module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import (
    is_spotify_url,
    is_soundcloud_url,
    is_youtube_url,
    is_playlist_url
)


class TestURLDetection:
    """Test suite for URL detection functions."""
    
    # Spotify URL tests
    def test_is_spotify_url_with_open_spotify(self):
        """Test Spotify URL detection with open.spotify.com."""
        url = "https://open.spotify.com/track/abc123"
        assert is_spotify_url(url) is True
    
    def test_is_spotify_url_with_spotify_com(self):
        """Test Spotify URL detection with spotify.com."""
        url = "https://spotify.com/track/abc123"
        assert is_spotify_url(url) is True
    
    def test_is_spotify_url_with_youtube(self):
        """Test Spotify detection returns False for YouTube URLs."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert is_spotify_url(url) is False
    
    # SoundCloud URL tests
    def test_is_soundcloud_url_valid(self):
        """Test SoundCloud URL detection."""
        url = "https://soundcloud.com/artist/track"
        assert is_soundcloud_url(url) is True
    
    def test_is_soundcloud_url_with_youtube(self):
        """Test SoundCloud detection returns False for YouTube URLs."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert is_soundcloud_url(url) is False
    
    # YouTube URL tests
    def test_is_youtube_url_with_youtube_com(self):
        """Test YouTube URL detection with youtube.com."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert is_youtube_url(url) is True
    
    def test_is_youtube_url_with_youtu_be(self):
        """Test YouTube URL detection with youtu.be short URL."""
        url = "https://youtu.be/abc123"
        assert is_youtube_url(url) is True
    
    def test_is_youtube_url_with_youtube_be(self):
        """Test YouTube URL detection with youtube.be."""
        url = "https://youtube.be/abc123"
        assert is_youtube_url(url) is True
    
    def test_is_youtube_url_with_soundcloud(self):
        """Test YouTube detection returns False for SoundCloud URLs."""
        url = "https://soundcloud.com/artist/track"
        assert is_youtube_url(url) is False
    
    # Playlist URL tests
    def test_is_playlist_url_with_list_parameter(self):
        """Test playlist detection with list= parameter."""
        url = "https://www.youtube.com/watch?v=abc123&list=PLxxx"
        assert is_playlist_url(url) is True
    
    def test_is_playlist_url_with_playlist_path(self):
        """Test playlist detection with /playlist? path."""
        url = "https://www.youtube.com/playlist?list=PLxxx"
        assert is_playlist_url(url) is True
    
    def test_is_playlist_url_with_single_video(self):
        """Test playlist detection returns False for single video."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert is_playlist_url(url) is False
    
    def test_is_playlist_url_with_empty_string(self):
        """Test playlist detection with empty string."""
        assert is_playlist_url("") is False


class TestEdgeCases:
    """Test edge cases and malformed inputs."""
    
    def test_url_detection_with_empty_string(self):
        """Test URL detection functions with empty string."""
        assert is_spotify_url("") is False
        assert is_soundcloud_url("") is False
        assert is_youtube_url("") is False
        assert is_playlist_url("") is False
    
    def test_url_detection_case_sensitive(self):
        """Test that URL detection is case sensitive (current behavior)."""
        # Note: Current implementation uses 'in' operator which is case-sensitive
        assert is_youtube_url("https://www.youtube.com/watch?v=abc") is True
        assert is_youtube_url("https://WWW.YOUTUBE.COM/watch?v=abc") is False  # Case-sensitive
        assert is_spotify_url("https://spotify.com/track/abc") is True
        assert is_soundcloud_url("https://soundcloud.com/track") is True
    
    def test_url_detection_with_extra_parameters(self):
        """Test URL detection works with query parameters."""
        url = "https://www.youtube.com/watch?v=abc123&t=30s&feature=share"
        assert is_youtube_url(url) is True
