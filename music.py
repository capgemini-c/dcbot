"""
Music module for Discord bot - supports YouTube, SoundCloud, and Spotify links.
"""

import asyncio
import os
import random
import re
from collections import deque
from dataclasses import dataclass
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands

# Load opus for voice support
try:
    discord.opus.load_opus('libopus.so.0')
    print("✅ Opus loaded successfully", flush=True)
except OSError:
    try:
        discord.opus.load_opus('opus')
        print("✅ Opus loaded successfully (fallback)", flush=True)
    except OSError as e:
        print(f"⚠️ Could not load opus: {e}", flush=True)

# Check FFmpeg and Deno
import subprocess
print("=" * 50, flush=True)
print("🎬 SYSTEM DEPENDENCIES", flush=True)
print("=" * 50, flush=True)

# FFmpeg
try:
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        print(f"✅ FFmpeg: {version_line.replace('ffmpeg version ', '')[:40]}", flush=True)
    else:
        print("❌ FFmpeg: not working", flush=True)
except FileNotFoundError:
    print("❌ FFmpeg: NOT INSTALLED", flush=True)
except Exception as e:
    print(f"❌ FFmpeg: {e}", flush=True)

# Deno (for YouTube JS challenges)
try:
    result = subprocess.run(['deno', '--version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        version = result.stdout.split('\n')[0]
        print(f"✅ Deno: {version}", flush=True)
    else:
        print("⚠️ Deno: not working (YouTube may have limited formats)", flush=True)
except FileNotFoundError:
    print("⚠️ Deno: not installed (YouTube may have limited formats)", flush=True)
except Exception as e:
    print(f"⚠️ Deno: {e}", flush=True)

print("=" * 50, flush=True)

# Check PyNaCl/libsodium status
print("=" * 50, flush=True)
print("🔐 ENCRYPTION STATUS", flush=True)
print("=" * 50, flush=True)
try:
    import nacl
    print(f"✅ PyNaCl version: {nacl.__version__}", flush=True)
    from nacl import secret
    print("✅ nacl.secret imported", flush=True)
    # Test if encryption actually works
    from nacl.secret import SecretBox
    key = b'0' * 32
    box = SecretBox(key)
    test = box.encrypt(b'test')
    print("✅ Encryption test passed", flush=True)
except Exception as e:
    print(f"❌ PyNaCl/libsodium error: {type(e).__name__}: {e}", flush=True)
    import traceback
    traceback.print_exc()
print("=" * 50, flush=True)

# yt-dlp for audio extraction
import yt_dlp
import urllib.request

# NordVPN SOCKS5 Proxy Configuration
print("=" * 50, flush=True)
print("🔧 NORDVPN SOCKS5 PROXY", flush=True)
print("=" * 50, flush=True)

NORDVPN_USER = os.getenv('NORDVPN_USER')
NORDVPN_PASS = os.getenv('NORDVPN_PASS')
NORDVPN_SERVER = "se.socks.nordhold.net"  # NordVPN SOCKS5 server (Sweden)

if NORDVPN_USER and NORDVPN_PASS:
    print(f"🔒 PROXY ENABLED", flush=True)
    print(f"   Server: {NORDVPN_SERVER}:1080", flush=True)
else:
    print("🔓 PROXY DISABLED", flush=True)
    print("   Set NORDVPN_USER + NORDVPN_PASS for YouTube support", flush=True)
print("=" * 50, flush=True)

# Test connectivity
print("=" * 50, flush=True)
print("🌐 CONNECTIVITY TEST", flush=True)
print("=" * 50, flush=True)

def test_url_direct(url: str, name: str) -> bool:
    """Test if a URL is reachable (direct connection)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            print(f"   ✅ {name} (direct): HTTP {status}", flush=True)
            return True
    except Exception as e:
        print(f"   ❌ {name} (direct): {type(e).__name__}", flush=True)
        return False

def test_proxy_connection() -> bool:
    """Test if we can connect through the SOCKS5 proxy."""
    if not NORDVPN_USER or not NORDVPN_PASS:
        print("   ⏭️ Proxy test skipped (no credentials)", flush=True)
        return False
    
    import socket
    import socks  # PySocks
    
    try:
        print(f"   🔌 Testing SOCKS5 to {NORDVPN_SERVER}:1080...", flush=True)
        
        # Create a SOCKS5 socket
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, NORDVPN_SERVER, 1080, True, NORDVPN_USER, NORDVPN_PASS)
        s.settimeout(15)
        
        # Try to connect to YouTube through the proxy
        s.connect(("www.youtube.com", 443))
        s.close()
        
        print(f"   ✅ Proxy: Connected to YouTube via {NORDVPN_SERVER}", flush=True)
        return True
    except socks.ProxyConnectionError as e:
        print(f"   ❌ Proxy auth failed: {e}", flush=True)
        return False
    except socks.SOCKS5Error as e:
        print(f"   ❌ SOCKS5 error: {e}", flush=True)
        return False
    except socket.timeout:
        print(f"   ❌ Proxy timeout - server may be unreachable from this network", flush=True)
        return False
    except Exception as e:
        print(f"   ❌ Proxy test failed: {type(e).__name__}: {e}", flush=True)
        return False

print("Direct connections:", flush=True)
test_url_direct("https://www.youtube.com", "YouTube")
test_url_direct("https://soundcloud.com", "SoundCloud")

print("\nProxy connection:", flush=True)
PROXY_WORKS = test_proxy_connection()

print("=" * 50, flush=True)

# Playlist settings
MAX_PLAYLIST_SONGS = 50  # Limit to prevent abuse

YTDL_OPTIONS = {
    'format': 'bestaudio/best',  # Always get best available audio quality
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Enable playlist support
    'playlistend': MAX_PLAYLIST_SONGS,  # Limit playlist size
    'nocheckcertificate': True,
    'ignoreerrors': True,  # Skip unavailable videos in playlist
    'logtostderr': False,
    'quiet': True,  # Suppress yt-dlp output
    'no_warnings': True,  # Suppress warnings
    'noprogress': True,  # Suppress progress bars
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist',  # Get playlist info without downloading each video
    'geo_bypass': True,
    'geo_bypass_country': 'SE',  # Sweden (matches proxy location)
}

# Add proxy if NordVPN credentials are set
if NORDVPN_USER and NORDVPN_PASS and NORDVPN_SERVER:
    proxy_url = f'socks5://{NORDVPN_USER}:{NORDVPN_PASS}@{NORDVPN_SERVER}:1080'
    YTDL_OPTIONS['proxy'] = proxy_url
    print(f"✅ yt-dlp proxy configured: socks5://*****:*****@{NORDVPN_SERVER}:1080", flush=True)
else:
    print("⚠️  yt-dlp running without proxy", flush=True)

# FFmpeg options for local file playback (no proxy needed - file is already downloaded)
FFMPEG_OPTIONS = {
    'options': '-vn',
}

# Audio download directory
AUDIO_CACHE_DIR = '/tmp/dcbot_audio'
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
print(f"📁 Audio cache: {AUDIO_CACHE_DIR}", flush=True)

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


@dataclass
class Song:
    """Represents a song in the queue."""
    title: str
    url: str
    local_file: Optional[str] = None  # Path to downloaded audio file (None if not downloaded yet)
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    requester: Optional[str] = None
    
    @property
    def duration_str(self) -> str:
      """Return formatted duration string."""
      return format_duration(self.duration)
    
    @property
    def is_downloaded(self) -> bool:
        """Check if the song has been downloaded."""
        return self.local_file is not None and os.path.exists(self.local_file)
    
    def cleanup(self):
        """Delete the downloaded audio file."""
        try:
            if self.local_file and os.path.exists(self.local_file):
                os.remove(self.local_file)
                self.local_file = None
        except Exception as e:
            print(f"⚠️ Failed to cleanup {self.local_file}: {e}", flush=True)


class MusicQueue:
    """Manages the song queue for a guild."""


def format_duration(seconds: Optional[int]) -> str:
  """
  Format duration in seconds to human-readable string.
  
  Args:
    seconds: Duration in seconds, or None if unknown
    
  Returns:
    Formatted string like "3:45" or "1:23:45", or "Unknown" if None
  """
  if not seconds:
    return "Unknown"
  
  minutes, secs = divmod(seconds, 60)
  hours, mins = divmod(minutes, 60)
  
  if hours:
    return f"{hours}:{mins:02d}:{secs:02d}"
  return f"{mins}:{secs:02d}"


def validate_user_in_voice(interaction: discord.Interaction) -> tuple[bool, Optional[str]]:
  """
  Validate that user is connected to a voice channel.
  
  Args:
    interaction: Discord interaction from command
    
  Returns:
    Tuple of (is_valid, error_message). If valid, error_message is None.
  """
  if not interaction.user.voice or not interaction.user.voice.channel:
    return False, "❌ Tu turi būti voice kanale, kad galėtum groti muziką!"
  return True, None


def validate_player_exists(
  player: Optional['MusicPlayer'],
  guild_id: int
) -> tuple[bool, Optional[str]]:
  """
  Validate that a music player exists for the guild.
  
  Args:
    player: The MusicPlayer instance (or None)
    guild_id: Guild ID for logging
    
  Returns:
    Tuple of (is_valid, error_message). If valid, error_message is None.
  """
  if not player or not player.voice_client:
    return False, "❌ Botas nėra prijungtas prie voice kanalo!"
  return True, None


def validate_queue_not_empty(player: 'MusicPlayer') -> tuple[bool, Optional[str]]:
  """
  Validate that the player's queue is not empty.
  
  Args:
    player: The MusicPlayer instance
    
  Returns:
    Tuple of (is_valid, error_message). If valid, error_message is None.
  """
  if player.queue.is_empty():
    return False, "❌ Eilė tuščia!"
  return True, None


def validate_skip_position(
  position: int,
  queue_length: int
) -> tuple[bool, Optional[str]]:
  """
  Validate that skip position is within valid range.
  
  Args:
    position: Requested position (1-indexed)
    queue_length: Current length of queue
    
  Returns:
    Tuple of (is_valid, error_message). If valid, error_message is None.
  """
  if position < 1 or position > queue_length:
    return (
      False,
      f"❌ Pozicija turi būti tarp 1 ir {queue_length}!"
    )
  return True, None


def require_player(func):
  """
  Decorator to validate that a music player exists before command execution.
  Automatically validates and passes the player to the decorated function.
  """
  async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
    player = player_manager.get(interaction.guild.id)
    is_valid, error_msg = validate_player_exists(player, interaction.guild.id)
    if not is_valid:
      await interaction.response.send_message(error_msg, ephemeral=True)
      return
    return await func(self, interaction, *args, player=player, **kwargs)
  return wrapper


class EmbedBuilder:
  """
  Builds consistent Discord embeds for music bot messages.
  Centralizes embed creation for maintainability and consistent styling.
  """
  
  @staticmethod
  def now_playing(song: Song) -> discord.Embed:
    """Create embed for now playing message."""
    embed = discord.Embed(
      title="🎵 Dabar groja",
      description=f"**[{song.title}]({song.url})**",
      color=discord.Color.green()
    )
    embed.add_field(name="Trukmė", value=song.duration_str, inline=True)
    embed.add_field(name="Užsakė", value=song.requester or "Unknown", inline=True)
    
    if song.thumbnail:
      embed.set_thumbnail(url=song.thumbnail)
    
    return embed
  
  @staticmethod
  def queue(player: 'MusicPlayer') -> discord.Embed:
    """Create embed for queue display."""
    embed = discord.Embed(
      title="🎶 Dainų eilė",
      color=discord.Color.purple()
    )
    
    # Current song
    if player.queue.current:
      embed.add_field(
        name="🎵 Dabar groja",
        value=f"**[{player.queue.current.title[:50]}]({player.queue.current.url})** [{player.queue.current.duration_str}]",
        inline=False
      )
    else:
      embed.add_field(
        name="🎵 Dabar groja",
        value="Niekas",
        inline=False
      )
    
    # Queue with download status
    queue_length = len(player.queue.queue)
    if queue_length > 0:
      queue_list = []
      for i, song in enumerate(list(player.queue.queue)[:10], 1):
        # Show download status icon
        if song.is_downloaded:
          status_icon = "✅"
        elif player.buffer_manager.is_downloading(song):
          status_icon = "📥"
        else:
          status_icon = "⏳"
        
        duration = song.duration_str if song.duration_str else "?"
        queue_list.append(f"{status_icon} `{i}.` **{song.title[:40]}** [{duration}]")
      
      # Determine correct pluralization
      if queue_length == 1:
        plural_form = "daina"
      elif 2 <= queue_length <= 9:
        plural_form = "dainos"
      else:
        plural_form = "dainų"
      
      embed.add_field(
        name=f"📋 Eilėje ({queue_length} {plural_form})",
        value="\n".join(queue_list),
        inline=False
      )
      
      if queue_length > 10:
        embed.add_field(
          name="➕ Daugiau",
          value=f"Ir dar {queue_length - 10} dainų...",
          inline=False
        )
    else:
      embed.add_field(name="📋 Eilėje", value="Tuščia", inline=False)
    
    return embed
  
  @staticmethod
  def playlist_added(playlist_entries: List[dict], queue_length: int, requester: str) -> discord.Embed:
    """Create embed for playlist added message."""
    embed = discord.Embed(
      title="📋 Playlist pridėtas į eilę",
      description=f"Pridėta **{len(playlist_entries)}** dainų",
      color=discord.Color.green()
    )
    embed.add_field(name="Pirmoji daina", value=playlist_entries[0]['title'][:50], inline=False)
    embed.add_field(name="Eilėje", value=f"{queue_length} dainos", inline=True)
    embed.add_field(name="Užsakė", value=requester, inline=True)
    return embed
  
  @staticmethod
  def song_added(song: Song, queue_position: int) -> discord.Embed:
    """Create embed for song added to queue message."""
    embed = discord.Embed(
      title="✅ Pridėta į eilę",
      description=f"**[{song.title}]({song.url})**",
      color=discord.Color.blue()
    )
    embed.add_field(name="Pozicija eilėje", value=f"#{queue_position}", inline=True)
    embed.add_field(name="Trukmė", value=song.duration_str, inline=True)
    embed.add_field(name="Užsakė", value=song.requester, inline=False)
    
    if song.thumbnail:
      embed.set_thumbnail(url=song.thumbnail)
    
    return embed
  
  @staticmethod
  def stopped() -> discord.Embed:
    """Create embed for stopped playback message."""
    return discord.Embed(
      title="⏹️ Muzika sustabdyta",
      description="Eilė išvalyta ir atsijungta nuo voice kanalo.",
      color=discord.Color.red()
    )
  
  @staticmethod
  def skipped(current_song: Optional[Song], next_song: Optional[Song]) -> discord.Embed:
    """Create embed for skipped song message."""
    embed = discord.Embed(
      title="⏭️ Praleista",
      description=f"Praleista: **{current_song.title if current_song else 'Unknown'}**",
      color=discord.Color.blue()
    )
    
    if next_song:
      embed.add_field(name="Kita daina", value=next_song.title, inline=False)
    else:
      embed.add_field(name="Eilė", value="Tuščia", inline=False)
    
    return embed
  
  @staticmethod
  def skipped_to(target_song: Song, position: int) -> discord.Embed:
    """Create embed for skip to position message."""
    embed = discord.Embed(
      title="⏭️ Peršokta",
      description=f"Peršokta į poziciją #{position}",
      color=discord.Color.blue()
    )
    embed.add_field(
      name="Kita daina",
      value=f"**{target_song.title}**",
      inline=False
    )
    return embed
  
  @staticmethod
  def test_mode(song_title: str) -> discord.Embed:
    """Create embed for test command."""
    return discord.Embed(
      title="🧪 Test Mode",
      description=f"Playing: **{song_title}**",
      color=discord.Color.orange()
    )


class MusicQueue:
    
    def __init__(self):
        self.queue: deque[Song] = deque()
        self.current: Optional[Song] = None
        self.loop: bool = False
    
    def add(self, song: Song):
        self.queue.append(song)
    
    def next(self) -> Optional[Song]:
        if self.loop and self.current:
            return self.current
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        self.current = None
        return None
    
    def skip_to(self, position: int) -> bool:
        """Skip to a specific position in queue (1-indexed). Returns True if successful."""
        if position < 1 or position > len(self.queue):
            return False
        
        # Remove songs before the target position
        for _ in range(position - 1):
            if self.queue:
                song = self.queue.popleft()
                song.cleanup()  # Delete files we're skipping
        
        return True
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
    def __len__(self):
        return len(self.queue)
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0 and self.current is None


class URLValidator:
  """
  Validates and categorizes music URLs from various platforms.
  Provides case-insensitive URL detection for better user experience.
  """
  
  @staticmethod
  def is_spotify(url: str) -> bool:
    """Check if URL is a Spotify link."""
    url_lower = url.lower()
    return 'spotify.com' in url_lower or 'open.spotify.com' in url_lower
  
  @staticmethod
  def is_soundcloud(url: str) -> bool:
    """Check if URL is a SoundCloud link."""
    return 'soundcloud.com' in url.lower()
  
  @staticmethod
  def is_youtube(url: str) -> bool:
    """Check if URL is a YouTube link."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in ['youtube.com', 'youtu.be', 'youtube.be'])
  
  @staticmethod
  def is_playlist(url: str) -> bool:
    """Check if URL contains a playlist."""
    return 'list=' in url or '/playlist?' in url


async def extract_spotify_query(url: str) -> Optional[str]:
    """
    Extract track name and artist from Spotify URL for YouTube search.
    Uses yt-dlp's Spotify extractor when available, otherwise parses the URL.
    """
    # Try to extract with yt-dlp first (it has Spotify support)
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info(url, download=False)
        )
        if data:
            # If yt-dlp extracted it successfully, return the search query
            title = data.get('title', '')
            artist = data.get('artist', '') or data.get('uploader', '')
            if title:
                return f"{artist} - {title}" if artist else title
    except Exception:
        pass
    
    # Fallback: parse the URL to get track ID and search
    match = re.search(r'track/([a-zA-Z0-9]+)', url)
    if match:
        # Return None to indicate we need to search by the URL itself
        return None
    
    return None


def _convert_to_playlist_url(query: str) -> str:
  """
  Convert watch URL with playlist param to proper playlist URL.
  
  Args:
    query: Original URL that may contain list= parameter
    
  Returns:
    Converted playlist URL if applicable, otherwise original query
  """
  if 'list=' in query and 'watch?' in query:
    import re
    list_match = re.search(r'list=([a-zA-Z0-9_-]+)', query)
    if list_match:
      playlist_id = list_match.group(1)
      converted = f"https://www.youtube.com/playlist?list={playlist_id}"
      print(f"📋 Converted to playlist URL: {converted}", flush=True)
      return converted
  return query


async def get_playlist_entries(query: str) -> List[dict]:
  """
  Extract playlist entries without downloading.
  Returns list of video info dicts with 'url' and 'title'.
  """
  # Early return: Only process playlist URLs
  if not URLValidator.is_playlist(query):
    return []
  
  try:
    loop = asyncio.get_event_loop()
    
    # Convert watch?v=X&list=Y to proper playlist URL
    query = _convert_to_playlist_url(query)
    
    # Configure extraction options
    extract_opts = YTDL_OPTIONS.copy()
    extract_opts['extract_flat'] = True
    extract_opts['quiet'] = True
    extract_opts['noplaylist'] = False  # Force playlist mode
    
    def do_extract():
      with yt_dlp.YoutubeDL(extract_opts) as ydl:
        return ydl.extract_info(query, download=False)
    
    print(f"📋 Extracting playlist info...", flush=True)
    data = await asyncio.wait_for(
      loop.run_in_executor(None, do_extract),
      timeout=60
    )
    
    # Early return: No data from extraction
    if not data:
      print(f"❌ No data returned from playlist extraction", flush=True)
      return []
    
    # Early return: Not a playlist (no 'entries' field)
    if 'entries' not in data:
      print(f"❌ No 'entries' in data - not a playlist", flush=True)
      return []
    
    # Process playlist entries
    playlist_title = data.get('title', 'Unknown Playlist')
    print(f"📋 Found playlist: {playlist_title} ({len(data['entries'])} videos)", flush=True)
    
    entries = []
    for entry in data['entries'][:MAX_PLAYLIST_SONGS]:
      if entry:
        entries.append({
          'url': entry.get('url') or entry.get('webpage_url') or f"https://youtube.com/watch?v={entry.get('id')}",
          'title': entry.get('title', 'Unknown'),
          'id': entry.get('id')
        })
    
    return entries
  
  except Exception as e:
    print(f"❌ Error extracting playlist: {e}", flush=True)
    import traceback
    traceback.print_exc()
    return []


async def download_song(url: str, requester: str, timeout_seconds: int = 120) -> Optional[Song]:
    """
    Download a single song from URL.
    """
    try:
        loop = asyncio.get_event_loop()
        
        print(f"🔄 Downloading: {url[:50]}...", flush=True)
        start_time = asyncio.get_event_loop().time()
        
        # Create download options with unique output path
        import uuid
        file_id = str(uuid.uuid4())[:8]
        download_opts = YTDL_OPTIONS.copy()
        download_opts['outtmpl'] = os.path.join(AUDIO_CACHE_DIR, f'{file_id}-%(id)s.%(ext)s')
        download_opts['extract_flat'] = False  # Actually download
        download_opts['noplaylist'] = True  # Single video only
        
        # Download with timeout
        try:
            def do_download():
                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    return ydl.extract_info(url, download=True)
            
            data = await asyncio.wait_for(
                loop.run_in_executor(None, do_download),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"❌ Download timed out after {elapsed:.1f}s", flush=True)
            return None
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        if not data:
            return None
        
        # Handle search results
        if 'entries' in data:
            data = data['entries'][0] if data['entries'] else None
            if not data:
                return None
        
        # Find the downloaded file
        video_id = data.get('id', 'unknown')
        local_file = None
        
        for f in os.listdir(AUDIO_CACHE_DIR):
            if f.startswith(file_id) and video_id in f:
                local_file = os.path.join(AUDIO_CACHE_DIR, f)
                break
        
        if not local_file or not os.path.exists(local_file):
            print(f"❌ Downloaded file not found for {video_id}", flush=True)
            return None
        
        file_size = os.path.getsize(local_file) / (1024 * 1024)
        print(f"📁 Downloaded: {data.get('title', 'Unknown')[:40]} ({file_size:.1f} MB, {elapsed:.1f}s)", flush=True)
        
        return Song(
            title=data.get('title', 'Unknown'),
            url=data.get('webpage_url', url),
            local_file=local_file,
            duration=data.get('duration'),
            thumbnail=data.get('thumbnail'),
            requester=requester
        )
    
    except Exception as e:
        print(f"❌ Error downloading: {type(e).__name__}: {e}", flush=True)
        return None


async def get_song_info(query: str, requester: str, timeout_seconds: int = 120) -> Optional[Song]:
    """
    Download audio from a URL or search query.
    Supports YouTube, SoundCloud, and Spotify.
    For playlists, use get_playlist_entries() first.
    """
    # Handle Spotify URLs - convert to YouTube search
    if URLValidator.is_spotify(query):
        search_query = await extract_spotify_query(query)
        if search_query:
            query = f"ytsearch:{search_query}"
        else:
            query = f"ytsearch:{query}"
    
    return await download_song(query, requester, timeout_seconds)


class DownloadBufferManager:
    """Manages download buffer for songs in the queue."""
    
    def __init__(self, buffer_size: int = 3):
        self.buffer_size = buffer_size
        self.currently_downloading: set[str] = set()
        self._downloading_lock = asyncio.Lock()
    
    def is_downloading(self, song: Song) -> bool:
        """Check if a song is currently being downloaded."""
        return song.title in self.currently_downloading
    
    def get_downloading_count(self) -> int:
        """Get count of songs currently downloading."""
        return len(self.currently_downloading)
    
    def mark_downloading(self, song: Song) -> None:
        """Mark a song as currently downloading."""
        self.currently_downloading.add(song.title)
    
    def unmark_downloading(self, song: Song) -> None:
        """Unmark a song as downloading."""
        self.currently_downloading.discard(song.title)
    
    def get_songs_to_download(self, queue: MusicQueue) -> List[Song]:
        """
        Get list of songs that should be in the download buffer.
        Returns songs that need to be downloaded (not already downloaded).
        """
        songs_to_download = []
        
        # Include current song if not downloaded
        if queue.current and not queue.current.is_downloaded:
            songs_to_download.append(queue.current)
        
        # Calculate how many more songs we need
        songs_needed = self.buffer_size - (1 if queue.current else 0)
        
        # Add next songs from queue that aren't downloaded
        for song in list(queue.queue)[:songs_needed]:
            if not song.is_downloaded:
                songs_to_download.append(song)
        
        return songs_to_download
    
    def get_songs_to_cleanup(self, queue: MusicQueue) -> List[Song]:
        """
        Get list of songs beyond the buffer that should be cleaned up.
        """
        songs_to_cleanup = []
        
        # Songs to keep in buffer
        songs_needed = self.buffer_size - (1 if queue.current else 0)
        
        # Songs beyond the buffer should be cleaned up
        for song in list(queue.queue)[songs_needed:]:
            if song.is_downloaded:
                songs_to_cleanup.append(song)
        
        return songs_to_cleanup
    
    async def maintain_buffer(self, queue: MusicQueue) -> None:
        """
        Maintain a rolling buffer of downloaded songs.
        Downloads songs in buffer, cleans up songs beyond buffer.
        """
        async with self._downloading_lock:
            # Get songs that need to be downloaded
            songs_to_download = self.get_songs_to_download(queue)
            
            # Download each song
            for song in songs_to_download:
                if not song.is_downloaded and not self.is_downloading(song):
                    self.mark_downloading(song)
                    
                    try:
                        downloaded = await download_song(song.url, song.requester, timeout_seconds=90)
                        if downloaded:
                            song.local_file = downloaded.local_file
                            song.duration = downloaded.duration
                            song.thumbnail = downloaded.thumbnail
                        else:
                            print(f"❌ Buffer: Failed to download {song.title[:40]}", flush=True)
                    finally:
                        self.unmark_downloading(song)
            
            # Cleanup songs beyond buffer
            songs_to_cleanup = self.get_songs_to_cleanup(queue)
            for song in songs_to_cleanup:
                song.cleanup()


class MusicPlayer:
    """Handles music playback for a guild."""
    
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()
        self.voice_client: Optional[discord.VoiceClient] = None
        self._play_next_event = asyncio.Event()
        self._player_task: Optional[asyncio.Task] = None
        self.now_playing_message: Optional[discord.Message] = None  # Store message to update
        self.text_channel: Optional[discord.TextChannel] = None  # Store channel for sending messages
        self.playlist_info: dict = {'total': 0, 'downloaded': 0}  # Track playlist progress
        self.buffer_manager = DownloadBufferManager(buffer_size=3)  # Delegate to buffer manager
    
    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Connect to a voice channel."""
        try:
            # Check if already connected to this guild
            existing_vc = discord.utils.get(self.bot.voice_clients, guild=self.guild)
            if existing_vc:
                if existing_vc.channel.id != channel.id:
                    await existing_vc.move_to(channel)
                self.voice_client = existing_vc
            else:
                self.voice_client = await channel.connect()
            
            print(f"✅ Connected to voice channel: {channel.name}", flush=True)
            return True
        except Exception as e:
            print(f"❌ Error connecting to voice channel: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return False
    
    async def disconnect(self):
        """Disconnect from voice channel."""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        self.queue.clear()
        if self._player_task:
            self._player_task.cancel()
    
    async def maintain_download_buffer(self):
        """Maintain a rolling buffer of downloaded songs (delegates to buffer manager)."""
        await self.buffer_manager.maintain_buffer(self.queue)
    
    def _build_now_playing_embed(self, song: Song) -> discord.Embed:
        """Build embed for now playing message with queue info."""
        embed = EmbedBuilder.now_playing(song)
        embed.set_field_at(1, name="Eilėje", value=str(len(self.queue)), inline=True)
        
        # Show downloading status
        if self.buffer_manager.get_downloading_count() > 0:
            downloading_count = self.buffer_manager.get_downloading_count()
            embed.add_field(
                name="📥 Kraunama",
                value=f"{downloading_count} daina{'s' if downloading_count > 1 else ''}",
                inline=True
            )
        
        return embed
    
    async def _update_now_playing_message(self, song: Song) -> None:
        """Update now playing message - edit if it's the last message, otherwise recreate at bottom."""
        if not self.text_channel:
            return
        
        embed = self._build_now_playing_embed(song)
        view = MusicControlView(self.bot, self.guild.id)
        
        # Check if our message is the last one in the channel
        is_last_message = False
        if self.now_playing_message:
            try:
                # Fetch the last message from the channel
                last_message = None
                async for message in self.text_channel.history(limit=1):
                    last_message = message
                    break
                
                # If our message is the last one, just edit it
                if last_message and last_message.id == self.now_playing_message.id:
                    is_last_message = True
                    await self.now_playing_message.edit(embed=embed, view=view)
                    return
            except discord.errors.NotFound:
                # Message was deleted, fall through to create new one
                self.now_playing_message = None
            except Exception as e:
                print(f"⚠️ Failed to check/edit message: {type(e).__name__}: {e}", flush=True)
        
        # If we reach here, either:
        # 1. There's no existing message
        # 2. The message is not the last one in chat
        # 3. Editing failed
        # So we delete the old one (if it exists) and create a new one at the bottom
        
        if self.now_playing_message and not is_last_message:
            try:
                await self.now_playing_message.delete()
            except discord.errors.NotFound:
                pass
            except Exception as e:
                print(f"⚠️ Failed to delete old message: {type(e).__name__}: {e}", flush=True)
            finally:
                self.now_playing_message = None
        
        # Create new message at the bottom
        try:
            self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"⚠️ Failed to create new now playing message: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    def play_next(self, error: Optional[Exception] = None) -> None:
        """Callback when a song finishes playing."""
        if error:
            print(f"Player error: {error}", flush=True)
        self._play_next_event.set()
    
    async def play(self, song: Song) -> bool:
        """Play a song."""
        if not self.voice_client or not self.voice_client.is_connected():
            return False
        
        # Ensure song is downloaded
        if not song.is_downloaded:
            downloaded = await download_song(song.url, song.requester, timeout_seconds=90)
            if downloaded:
                song.local_file = downloaded.local_file
                song.duration = downloaded.duration
                song.thumbnail = downloaded.thumbnail
            else:
                print(f"❌ Failed to download song: {song.title}", flush=True)
                return False
        
        try:
            if not os.path.exists(song.local_file):
                print(f"❌ Audio file not found: {song.local_file}", flush=True)
                return False
            
            source = discord.FFmpegPCMAudio(song.local_file, **FFMPEG_OPTIONS)
            
            # Wrap callback to cleanup after playback
            def after_play(error):
                if error:
                    print(f"❌ Playback error: {error}", flush=True)
                song.cleanup()  # Delete downloaded file
                self.play_next(error)
            
            self.voice_client.play(source, after=after_play)
            self.queue.current = song
            return True
        except Exception as e:
            print(f"❌ Error playing song: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            song.cleanup()  # Clean up on error too
            return False
    
    async def start_player_loop(self):
        """Main player loop - plays songs from queue."""
        while True:
            self._play_next_event.clear()
            
            song = self.queue.next()
            if not song:
                # Queue empty, wait for new songs
                await asyncio.sleep(0.5)
                if self.queue.is_empty():
                    print("🛑 Queue empty, exiting player loop", flush=True)
                    break
                continue
            
            # Maintain download buffer in background (non-blocking)
            asyncio.create_task(self.maintain_download_buffer())
            
            # Start playing the song (this ensures it's downloaded and metadata is populated)
            if not await self.play(song):
                continue
            
            # Update now playing message (delete old, create new at bottom)
            await self._update_now_playing_message(song)
            
            # Wait for song to finish
            await self._play_next_event.wait()
    
    def skip(self) -> bool:
        """Skip the current song."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            return True
        return False
    
    def stop(self):
        """Stop playback and clear queue."""
        self.queue.clear()
        if self.voice_client:
            self.voice_client.stop()


class PlayerManager:
    """Manages MusicPlayer instances per guild."""
    
    def __init__(self):
        self._players: dict[int, MusicPlayer] = {}
    
    def get(self, guild_id: int) -> Optional[MusicPlayer]:
        """Get player for a guild, returns None if doesn't exist."""
        return self._players.get(guild_id)
    
    def create_player(self, bot: commands.Bot, guild: discord.Guild) -> MusicPlayer:
        """Create a new player for a guild."""
        player = MusicPlayer(bot, guild)
        self._players[guild.id] = player
        return player
    
    def get_or_create(self, bot: commands.Bot, guild: discord.Guild) -> MusicPlayer:
        """Get existing player or create new one if doesn't exist."""
        if guild.id not in self._players:
            return self.create_player(bot, guild)
        
        # Sync voice client if bot is already connected
        player = self._players[guild.id]
        existing_vc = discord.utils.get(bot.voice_clients, guild=guild)
        if existing_vc and player.voice_client != existing_vc:
            player.voice_client = existing_vc
        
        return player
    
    def remove(self, guild_id: int) -> None:
        """Remove player for a guild."""
        if guild_id in self._players:
            del self._players[guild_id]
    
    def has_player(self, guild_id: int) -> bool:
        """Check if player exists for a guild."""
        return guild_id in self._players
    
    def count(self) -> int:
        """Get count of active players."""
        return len(self._players)


# Global player manager instance
player_manager = PlayerManager()


class MusicControlView(discord.ui.View):
    """Control buttons for music playback."""
    
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)  # Persistent buttons
        self.bot = bot
        self.guild_id = guild_id
    
    def get_player(self) -> Optional[MusicPlayer]:
        return player_manager.get(self.guild_id)
    
    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary, custom_id="music_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.get_player()
        if player and player.voice_client:
            if player.voice_client.is_playing():
                player.voice_client.pause()
                button.label = "▶️ Resume"
                await interaction.response.edit_message(view=self)
            elif player.voice_client.is_paused():
                player.voice_client.resume()
                button.label = "⏸️ Pause"
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.defer()
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.primary, custom_id="music_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.get_player()
        if player and player.skip():
            await interaction.response.send_message("⏭️ Praleidžiama...", ephemeral=True, delete_after=3)
        else:
            await interaction.response.send_message("❌ Nėra ką praleisti", ephemeral=True, delete_after=3)
    
    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.get_player()
        if player:
            player.stop()
            if player.voice_client:
                await player.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Muzika sustabdyta", ephemeral=True, delete_after=3)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="📋 Queue", style=discord.ButtonStyle.secondary, custom_id="music_queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Defer immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        player = self.get_player()
        
        if not player:
            await interaction.followup.send("📭 Nėra aktyvaus grotuvo", ephemeral=True)
            return
        
        # Use EmbedBuilder for consistent formatting
        embed = EmbedBuilder.queue(player)
        
        # Show playlist download progress if active
        if player.playlist_info['total'] > 0:
            pending = player.playlist_info['total'] - player.playlist_info['downloaded']
            if pending > 0:
                embed.add_field(
                    name="⬇️ Kraunama",
                    value=f"{pending} dainų dar kraunasi iš playlist'o",
                    inline=False
                )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


def get_player(bot: commands.Bot, guild: discord.Guild) -> MusicPlayer:
    """Get or create a music player for a guild."""
    return player_manager.get_or_create(bot, guild)


class Music(commands.Cog):
    """Music commands cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def _add_playlist_to_queue(
        self,
        player: MusicPlayer,
        entries: List[dict],
        requester: str,
        interaction: discord.Interaction
    ) -> None:
        """Add playlist entries to queue without downloading."""
        print(f"📋 Found playlist with {len(entries)} songs", flush=True)
        
        # Create Song objects without downloading (lazy loading)
        for entry in entries:
            song = Song(
                title=entry['title'],
                url=entry['url'],
                local_file=None,
                requester=requester
            )
            player.queue.add(song)
        
        # Show playlist added message
        embed = EmbedBuilder.playlist_added(entries, len(player.queue), requester)
        view = MusicControlView(self.bot, interaction.guild.id)
        player.now_playing_message = await interaction.followup.send(embed=embed, view=view)
    
    async def _add_single_song_to_queue(
        self,
        player: MusicPlayer,
        query: str,
        requester: str,
        interaction: discord.Interaction
    ) -> Optional[Song]:
        """Download and add single song to queue."""
        song = await get_song_info(query, requester)
        if not song:
            return None
        
        # Add to queue
        player.queue.add(song)
        
        # Create embed with control buttons
        embed = EmbedBuilder.song_added(song, len(player.queue))
        view = MusicControlView(self.bot, interaction.guild.id)
        player.now_playing_message = await interaction.followup.send(embed=embed, view=view)
        
        return song
    
    def _start_player_if_needed(self, player: MusicPlayer) -> None:
        """Start player loop if not already playing."""
        if not player.voice_client.is_playing() and (player._player_task is None or player._player_task.done()):
            player._player_task = asyncio.create_task(player.start_player_loop())
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Handle voice state updates - auto disconnect when alone."""
        # Only process if the bot is in a voice channel in this guild
        voice_client = discord.utils.get(self.bot.voice_clients, guild=member.guild)
        if not voice_client:
            return
        
        # Check if the bot is alone in the voice channel
        channel = voice_client.channel
        # Filter out bots from the member count
        human_members = [m for m in channel.members if not m.bot]
        
        if len(human_members) == 0:
            print(f"🚪 All users left voice channel '{channel.name}', disconnecting in 30 seconds...")
            # Wait 30 seconds before disconnecting (in case someone rejoins quickly)
            await asyncio.sleep(30)
            
            # Re-check if still alone
            voice_client = discord.utils.get(self.bot.voice_clients, guild=member.guild)
            if voice_client:
                channel = voice_client.channel
                human_members = [m for m in channel.members if not m.bot]
                
                if len(human_members) == 0:
                    print(f"🔌 Auto-disconnecting from '{channel.name}' - channel empty", flush=True)
                    player = player_manager.get(member.guild.id)
                    if player:
                        await player.disconnect()
                        # Clean up player
                        player_manager.remove(member.guild.id)
    
    @app_commands.command(name="play", description="Paleisti dainą arba playlist'ą iš YouTube, SoundCloud arba Spotify")
    @app_commands.describe(query="YouTube/SoundCloud nuoroda arba paieškos užklausa (Spotify nuorodų nepalaiko)")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song or playlist from YouTube, SoundCloud, or Spotify."""
        # Validate user is in voice channel
        is_valid, error_msg = validate_user_in_voice(interaction)
        if not is_valid:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        
        # Store text channel for sending messages
        player.text_channel = interaction.channel
        
        # Connect to voice channel
        if not await player.connect(voice_channel):
            await interaction.followup.send("❌ Nepavyko prisijungti prie voice kanalo!")
            return
        
        # Check if it's a playlist
        playlist_entries = await get_playlist_entries(query)
        
        if playlist_entries:
            await self._add_playlist_to_queue(player, playlist_entries, interaction.user.display_name, interaction)
        else:
            song = await self._add_single_song_to_queue(player, query, interaction.user.display_name, interaction)
            if not song:
                await interaction.followup.send("❌ Nepavyko rasti dainos. Patikrink nuorodą arba pabandyk kitą paiešką.")
                return
        
        # Start playing if not already
        self._start_player_if_needed(player)
    
    @app_commands.command(name="testplay", description="Test command - plays Rick Astley")
    async def testplay(self, interaction: discord.Interaction):
        """Test command that plays a known YouTube video."""
        TEST_URL = "https://www.youtube.com/watch?v=4kHl4FoK1Ys"
        
        # Validate user is in voice channel
        is_valid, error_msg = validate_user_in_voice(interaction)
        if not is_valid:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        
        # Store text channel for sending messages
        player.text_channel = interaction.channel
        
        # Connect to voice channel
        if not await player.connect(voice_channel):
            await interaction.followup.send("❌ Nepavyko prisijungti prie voice kanalo!")
            return
        
        # Get song info
        song = await get_song_info(TEST_URL, interaction.user.display_name)
        if not song:
            await interaction.followup.send("❌ Test failed - nepavyko gauti dainos info.")
            return
        
        # Add to queue
        player.queue.add(song)
        
        await interaction.followup.send(embed=EmbedBuilder.test_mode(song.title))
        
        # Start playing
        if not player.voice_client.is_playing() and (player._player_task is None or player._player_task.done()):
            player._player_task = asyncio.create_task(player.start_player_loop())
    
    @app_commands.command(name="stop", description="Sustabdyti muziką ir išvalyti eilę")
    @require_player
    async def stop(self, interaction: discord.Interaction, player: 'MusicPlayer'):
        """Stop playback and clear the queue."""
        await player.disconnect()
        
        await interaction.response.send_message(embed=EmbedBuilder.stopped())
        
        # Clean up player
        player_manager.remove(interaction.guild.id)
    
    @app_commands.command(name="skip", description="Praleisti dabartinę dainą")
    @require_player
    async def skip(self, interaction: discord.Interaction, player: 'MusicPlayer'):
        """Skip the current song."""
        if not player.voice_client.is_playing():
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True
            )
            return
        
        current_song = player.queue.current
        player.skip()
        
        # Determine next song for embed
        next_song = player.queue.queue[0] if player.queue.queue else None
        await interaction.response.send_message(embed=EmbedBuilder.skipped(current_song, next_song))
    
    @app_commands.command(name="skipto", description="Peršokti į konkrečią dainą eilėje")
    @app_commands.describe(position="Dainos numeris eilėje (1, 2, 3...)")
    @require_player
    async def skipto(self, interaction: discord.Interaction, position: int, player: 'MusicPlayer'):
        """Skip to a specific position in the queue."""
        is_valid, error_msg = validate_skip_position(position, len(player.queue))
        if not is_valid:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # Defer the response to avoid timeout
        await interaction.response.defer()
        
        # Skip to position
        if player.queue.skip_to(position):
            # Stop current song to trigger next
            if player.voice_client.is_playing():
                player.voice_client.stop()
            
            target_song = player.queue.queue[0] if player.queue.queue else None
            
            if target_song:
                # Send temporary message that deletes after 10 seconds
                message = await interaction.followup.send(
                  embed=EmbedBuilder.skipped_to(target_song, position)
                )
                
                # Delete message after 10 seconds
                await asyncio.sleep(10)
                try:
                    await message.delete()
                except discord.errors.NotFound:
                    pass
                except Exception as e:
                    print(f"⚠️ Failed to delete skipto message: {e}", flush=True)
            else:
                await interaction.followup.send("⚠️ Peršokta, bet eilė tuščia", ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Nepavyko peršokti į šią poziciją!",
                ephemeral=True
            )
    
    @app_commands.command(name="queue", description="Rodyti dainų eilę")
    async def queue_cmd(self, interaction: discord.Interaction):
        """Show the current queue."""
        player = player_manager.get(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="🎶 Dainų eilė",
                description="📭 Nėra aktyvaus grotuvo!",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Use EmbedBuilder for consistent queue display
        await interaction.response.send_message(embed=EmbedBuilder.queue(player))
    
    @app_commands.command(name="nowplaying", description="Rodyti dabartinę dainą")
    @require_player
    async def nowplaying(self, interaction: discord.Interaction, player: 'MusicPlayer'):
        """Show the currently playing song."""
        if not player.queue.current:
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(embed=EmbedBuilder.now_playing(player.queue.current))


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Music(bot))
