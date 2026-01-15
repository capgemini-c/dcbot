"""
Unit tests for formatting helper functions.
Tests duration formatting and other utility formatters.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from music import Song


class TestDurationFormatting:
  """Test suite for duration formatting (currently in Song.duration_str)."""
  
  def test_format_zero_seconds(self):
    """Test formatting 0 seconds (treated as unknown)."""
    song = Song(title="Test", url="http://example.com/1", duration=0)
    # Note: 0 is treated as falsy, so it returns "Unknown"
    # This is acceptable as 0-second songs don't exist
    assert song.duration_str == "Unknown"
  
  def test_format_single_digit_seconds(self):
    """Test formatting single digit seconds (should be zero-padded)."""
    song = Song(title="Test", url="http://example.com/1", duration=5)
    assert song.duration_str == "0:05"
  
  def test_format_double_digit_seconds(self):
    """Test formatting double digit seconds."""
    song = Song(title="Test", url="http://example.com/1", duration=45)
    assert song.duration_str == "0:45"
  
  def test_format_exactly_one_minute(self):
    """Test formatting exactly 1 minute."""
    song = Song(title="Test", url="http://example.com/1", duration=60)
    assert song.duration_str == "1:00"
  
  def test_format_minutes_and_seconds(self):
    """Test formatting minutes and seconds."""
    song = Song(title="Test", url="http://example.com/1", duration=195)
    assert song.duration_str == "3:15"
  
  def test_format_exactly_one_hour(self):
    """Test formatting exactly 1 hour."""
    song = Song(title="Test", url="http://example.com/1", duration=3600)
    assert song.duration_str == "1:00:00"
  
  def test_format_hours_minutes_seconds(self):
    """Test formatting hours, minutes, and seconds."""
    song = Song(title="Test", url="http://example.com/1", duration=3665)
    assert song.duration_str == "1:01:05"
  
  def test_format_long_duration(self):
    """Test formatting very long duration (10+ hours)."""
    song = Song(title="Test", url="http://example.com/1", duration=36000)
    assert song.duration_str == "10:00:00"
  
  def test_format_none_duration(self):
    """Test formatting None duration."""
    song = Song(title="Test", url="http://example.com/1", duration=None)
    assert song.duration_str == "Unknown"
  
  def test_format_edge_case_59_seconds(self):
    """Test formatting 59 seconds (just before 1 minute)."""
    song = Song(title="Test", url="http://example.com/1", duration=59)
    assert song.duration_str == "0:59"
  
  def test_format_edge_case_59_minutes(self):
    """Test formatting 59:59 (just before 1 hour)."""
    song = Song(title="Test", url="http://example.com/1", duration=3599)
    assert song.duration_str == "59:59"
  
  def test_format_realistic_song_durations(self):
    """Test formatting realistic song durations."""
    # Typical pop song (3:30)
    song1 = Song(title="Test", url="http://example.com/1", duration=210)
    assert song1.duration_str == "3:30"
    
    # Typical rock song (4:45)
    song2 = Song(title="Test", url="http://example.com/2", duration=285)
    assert song2.duration_str == "4:45"
    
    # Long progressive rock song (12:34)
    song3 = Song(title="Test", url="http://example.com/3", duration=754)
    assert song3.duration_str == "12:34"
