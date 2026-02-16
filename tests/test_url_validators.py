"""
Unit tests for URL validation functions.
Tests URL detection for YouTube without Discord dependencies.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import URLValidator


class TestURLDetection:
    """Test suite for URLValidator.is_url()."""

    def test_https_url(self):
        """Test HTTPS URL detection."""
        assert URLValidator.is_url("https://example.com") is True

    def test_http_url(self):
        """Test HTTP URL detection."""
        assert URLValidator.is_url("http://example.com") is True

    def test_not_a_url(self):
        """Test non-URL text."""
        assert URLValidator.is_url("not a url") is False
        assert URLValidator.is_url("") is False
        assert URLValidator.is_url("ftp://example.com") is False


class TestYouTubeURLDetection:
    """Test suite for YouTube URL detection."""

    def test_youtube_watch_url(self):
        """Test standard YouTube watch URL."""
        assert URLValidator.is_youtube(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ) is True

    def test_youtube_short_url(self):
        """Test YouTube short URL (youtu.be)."""
        assert URLValidator.is_youtube(
            "https://youtu.be/dQw4w9WgXcQ"
        ) is True

    def test_youtube_playlist_url(self):
        """Test YouTube playlist URL."""
        assert URLValidator.is_youtube(
            "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        ) is True

    def test_youtube_with_timestamp(self):
        """Test YouTube URL with timestamp."""
        assert URLValidator.is_youtube(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"
        ) is True

    def test_youtube_mobile_url(self):
        """Test YouTube mobile URL."""
        assert URLValidator.is_youtube(
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        ) is True

    def test_youtube_embed_url(self):
        """Test YouTube embed URL."""
        assert URLValidator.is_youtube(
            "https://www.youtube.com/embed/dQw4w9WgXcQ"
        ) is True

    def test_youtube_case_variations(self):
        """Test that YouTube URLs are detected regardless of case."""
        assert URLValidator.is_youtube(
            "HTTPS://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ"
        ) is True
        assert URLValidator.is_youtube(
            "https://YOUTUBE.com/watch?v=dQw4w9WgXcQ"
        ) is True

    def test_not_youtube_url(self):
        """Test that non-YouTube URLs are rejected."""
        assert URLValidator.is_youtube("https://www.google.com") is False
        assert URLValidator.is_youtube(
            "https://soundcloud.com/artist/song"
        ) is False
        assert URLValidator.is_youtube("not a url at all") is False
        assert URLValidator.is_youtube("") is False


class TestPlaylistURLDetection:
    """Test suite for playlist URL detection."""

    def test_youtube_playlist_with_list_param(self):
        """Test YouTube playlist URL with list= parameter."""
        assert URLValidator.is_playlist(
            "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        ) is True

    def test_youtube_watch_with_playlist(self):
        """Test YouTube watch URL with playlist parameter."""
        assert URLValidator.is_playlist(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        ) is True

    def test_single_video_url(self):
        """Test that single video URLs are not detected as playlists."""
        assert URLValidator.is_playlist(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ) is False

    def test_non_playlist_url(self):
        """Test that regular URLs are not detected as playlists."""
        assert URLValidator.is_playlist("https://www.google.com") is False
        assert URLValidator.is_playlist(
            "https://youtu.be/dQw4w9WgXcQ"
        ) is False
