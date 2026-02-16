"""
Unit tests for helper functions in music module.
Tests URL detection and validation functions.
"""

import pytest
import sys
import os

# Add parent directory to path to import music module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import URLValidator


class TestURLDetection:
    """Test suite for URL detection functions."""

    # is_url tests
    def test_is_url_with_https(self):
        """Test is_url with HTTPS URL."""
        assert URLValidator.is_url("https://example.com") is True

    def test_is_url_with_http(self):
        """Test is_url with HTTP URL."""
        assert URLValidator.is_url("http://example.com") is True

    def test_is_url_with_plain_text(self):
        """Test is_url with plain text."""
        assert URLValidator.is_url("some search query") is False

    def test_is_url_with_empty_string(self):
        """Test is_url with empty string."""
        assert URLValidator.is_url("") is False

    # YouTube URL tests
    def test_is_youtube_url_with_youtube_com(self):
        """Test YouTube URL detection with youtube.com."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert URLValidator.is_youtube(url) is True

    def test_is_youtube_url_with_youtu_be(self):
        """Test YouTube URL detection with youtu.be short URL."""
        url = "https://youtu.be/abc123"
        assert URLValidator.is_youtube(url) is True

    def test_is_youtube_url_with_non_youtube(self):
        """Test YouTube detection returns False for non-YouTube URLs."""
        url = "https://soundcloud.com/artist/track"
        assert URLValidator.is_youtube(url) is False

    # Playlist URL tests
    def test_is_playlist_url_with_list_parameter(self):
        """Test playlist detection with list= parameter."""
        url = "https://www.youtube.com/watch?v=abc123&list=PLxxx"
        assert URLValidator.is_playlist(url) is True

    def test_is_playlist_url_with_playlist_path(self):
        """Test playlist detection with /playlist? path."""
        url = "https://www.youtube.com/playlist?list=PLxxx"
        assert URLValidator.is_playlist(url) is True

    def test_is_playlist_url_with_single_video(self):
        """Test playlist detection returns False for single video."""
        url = "https://www.youtube.com/watch?v=abc123"
        assert URLValidator.is_playlist(url) is False

    def test_is_playlist_url_with_empty_string(self):
        """Test playlist detection with empty string."""
        assert URLValidator.is_playlist("") is False


class TestEdgeCases:
    """Test edge cases and malformed inputs."""

    def test_url_detection_with_empty_string(self):
        """Test URL detection functions with empty string."""
        assert URLValidator.is_youtube("") is False
        assert URLValidator.is_playlist("") is False
        assert URLValidator.is_url("") is False

    def test_url_detection_case_insensitive(self):
        """Test that YouTube URL detection is case-insensitive."""
        assert URLValidator.is_youtube(
            "https://www.youtube.com/watch?v=abc"
        ) is True
        assert URLValidator.is_youtube(
            "https://WWW.YOUTUBE.COM/watch?v=abc"
        ) is True

    def test_url_detection_with_extra_parameters(self):
        """Test URL detection works with query parameters."""
        url = "https://www.youtube.com/watch?v=abc123&t=30s&feature=share"
        assert URLValidator.is_youtube(url) is True
