"""
Unit tests for URL validation functions.
Tests URL detection for YouTube, SoundCloud, Spotify without Discord dependencies.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import (
  is_youtube_url,
  is_soundcloud_url,
  is_spotify_url,
  is_playlist_url
)


class TestYouTubeURLDetection:
  """Test suite for YouTube URL detection."""
  
  def test_youtube_watch_url(self):
    """Test standard YouTube watch URL."""
    assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
  
  def test_youtube_short_url(self):
    """Test YouTube short URL (youtu.be)."""
    assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True
  
  def test_youtube_playlist_url(self):
    """Test YouTube playlist URL."""
    assert is_youtube_url("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf") is True
  
  def test_youtube_with_timestamp(self):
    """Test YouTube URL with timestamp."""
    assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s") is True
  
  def test_youtube_mobile_url(self):
    """Test YouTube mobile URL."""
    assert is_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ") is True
  
  def test_youtube_embed_url(self):
    """Test YouTube embed URL."""
    assert is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ") is True
  
  def test_youtube_case_variations(self):
    """Test that YouTube URLs are detected regardless of case (now case-insensitive)."""
    assert is_youtube_url("HTTPS://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ") is True
    assert is_youtube_url("https://YOUTUBE.com/watch?v=dQw4w9WgXcQ") is True
  
  def test_not_youtube_url(self):
    """Test that non-YouTube URLs are rejected."""
    assert is_youtube_url("https://www.google.com") is False
    assert is_youtube_url("https://soundcloud.com/artist/song") is False
    assert is_youtube_url("not a url at all") is False
    assert is_youtube_url("") is False


class TestSoundCloudURLDetection:
  """Test suite for SoundCloud URL detection."""
  
  def test_soundcloud_track_url(self):
    """Test standard SoundCloud track URL."""
    assert is_soundcloud_url("https://soundcloud.com/artist/track-name") is True
  
  def test_soundcloud_set_url(self):
    """Test SoundCloud set/playlist URL."""
    assert is_soundcloud_url("https://soundcloud.com/artist/sets/playlist-name") is True
  
  def test_soundcloud_with_query_params(self):
    """Test SoundCloud URL with query parameters."""
    assert is_soundcloud_url("https://soundcloud.com/artist/track?in=playlist") is True
  
  def test_soundcloud_case_variations(self):
    """Test that SoundCloud URLs are detected regardless of case (now case-insensitive)."""
    assert is_soundcloud_url("https://SOUNDCLOUD.com/artist/track") is True
  
  def test_not_soundcloud_url(self):
    """Test that non-SoundCloud URLs are rejected."""
    assert is_soundcloud_url("https://www.youtube.com/watch?v=test") is False
    assert is_soundcloud_url("https://spotify.com/track/123") is False
    assert is_soundcloud_url("not a url") is False
    assert is_soundcloud_url("") is False


class TestSpotifyURLDetection:
  """Test suite for Spotify URL detection."""
  
  def test_spotify_track_url(self):
    """Test Spotify track URL."""
    assert is_spotify_url("https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6") is True
  
  def test_spotify_playlist_url(self):
    """Test Spotify playlist URL."""
    assert is_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
  
  def test_spotify_album_url(self):
    """Test Spotify album URL."""
    assert is_spotify_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3") is True
  
  def test_spotify_artist_url(self):
    """Test Spotify artist URL."""
    assert is_spotify_url("https://open.spotify.com/artist/0TnOYISbd1XYRBk9myaseg") is True
  
  def test_spotify_case_variations(self):
    """Test that Spotify URLs are detected regardless of case (now case-insensitive)."""
    assert is_spotify_url("https://open.SPOTIFY.com/track/123") is True
  
  def test_not_spotify_url(self):
    """Test that non-Spotify URLs are rejected."""
    assert is_spotify_url("https://www.youtube.com/watch?v=test") is False
    assert is_spotify_url("https://soundcloud.com/artist/track") is False
    assert is_spotify_url("not a url") is False
    assert is_spotify_url("") is False


class TestPlaylistURLDetection:
  """Test suite for playlist URL detection."""
  
  def test_youtube_playlist_with_list_param(self):
    """Test YouTube playlist URL with list= parameter."""
    assert is_playlist_url("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf") is True
  
  def test_youtube_watch_with_playlist(self):
    """Test YouTube watch URL with playlist parameter."""
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf") is True
  
  def test_single_video_url(self):
    """Test that single video URLs are not detected as playlists."""
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
  
  def test_soundcloud_playlist(self):
    """Test SoundCloud playlist URL."""
    assert is_playlist_url("https://soundcloud.com/artist/sets/playlist-name") is False  # Uses /playlist? check
  
  def test_non_playlist_url(self):
    """Test that regular URLs are not detected as playlists."""
    assert is_playlist_url("https://www.google.com") is False
    assert is_playlist_url("https://youtu.be/dQw4w9WgXcQ") is False
