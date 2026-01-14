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
import json as json_lib

# ============================================
# NordVPN SOCKS5 Proxy Configuration
# ============================================
# NordVPN SOCKS5 Proxy Configuration
# ============================================
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
    'quiet': False,
    'no_warnings': False,
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
        if not self.duration:
            return "Unknown"
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @property
    def is_downloaded(self) -> bool:
        """Check if the song has been downloaded."""
        return self.local_file is not None and os.path.exists(self.local_file)
    
    def cleanup(self):
        """Delete the downloaded audio file."""
        try:
            if self.local_file and os.path.exists(self.local_file):
                os.remove(self.local_file)
                print(f"🗑️ Cleaned up: {os.path.basename(self.local_file)}", flush=True)
                self.local_file = None
        except Exception as e:
            print(f"⚠️ Failed to cleanup {self.local_file}: {e}", flush=True)


class MusicQueue:
    """Manages the song queue for a guild."""
    
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
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0
    
    def __len__(self):
        return len(self.queue)
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0 and self.current is None


def is_spotify_url(url: str) -> bool:
    """Check if URL is a Spotify link."""
    return 'spotify.com' in url or 'open.spotify.com' in url


def is_soundcloud_url(url: str) -> bool:
    """Check if URL is a SoundCloud link."""
    return 'soundcloud.com' in url


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube link."""
    return any(domain in url for domain in ['youtube.com', 'youtu.be', 'youtube.be'])


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


def is_playlist_url(url: str) -> bool:
    """Check if URL contains a playlist."""
    return 'list=' in url or '/playlist?' in url


async def get_playlist_entries(query: str) -> List[dict]:
    """
    Extract playlist entries without downloading.
    Returns list of video info dicts with 'url' and 'title'.
    """
    # Only process if it looks like a playlist URL
    if not is_playlist_url(query):
        return []
    
    try:
        loop = asyncio.get_event_loop()
        
        # Convert watch?v=X&list=Y to playlist URL for proper extraction
        if 'list=' in query and 'watch?' in query:
            import re
            list_match = re.search(r'list=([a-zA-Z0-9_-]+)', query)
            if list_match:
                playlist_id = list_match.group(1)
                query = f"https://www.youtube.com/playlist?list={playlist_id}"
                print(f"📋 Converted to playlist URL: {query}", flush=True)
        
        # Use extract_flat to get playlist info quickly
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
        
        if not data:
            print(f"❌ No data returned from playlist extraction", flush=True)
            return []
        
        # Check if it's a playlist
        if 'entries' in data:
            entries = []
            playlist_title = data.get('title', 'Unknown Playlist')
            print(f"📋 Found playlist: {playlist_title} ({len(data['entries'])} videos)", flush=True)
            
            for entry in data['entries'][:MAX_PLAYLIST_SONGS]:
                if entry:
                    entries.append({
                        'url': entry.get('url') or entry.get('webpage_url') or f"https://youtube.com/watch?v={entry.get('id')}",
                        'title': entry.get('title', 'Unknown'),
                        'id': entry.get('id')
                    })
            return entries
        else:
            print(f"❌ No 'entries' in data - not a playlist", flush=True)
            return []
    
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
    if is_spotify_url(query):
        search_query = await extract_spotify_query(query)
        if search_query:
            query = f"ytsearch:{search_query}"
        else:
            query = f"ytsearch:{query}"
    
    return await download_song(query, requester, timeout_seconds)


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
        self.playlist_info: dict = {'total': 0, 'downloaded': 0}  # Track playlist progress
        self._download_buffer_size = 3  # Keep current + next 2 songs downloaded
        self._downloading_lock = asyncio.Lock()  # Prevent concurrent buffer updates
        self._currently_downloading: set = set()  # Track songs currently being downloaded
    
    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Connect to a voice channel."""
        try:
            print(f"🔊 Attempting to connect to voice channel: {channel.name} ({channel.id})")
            
            # Check if already connected to this guild
            existing_vc = discord.utils.get(self.bot.voice_clients, guild=self.guild)
            if existing_vc:
                print(f"📍 Already connected to: {existing_vc.channel.name}")
                if existing_vc.channel.id != channel.id:
                    print(f"🔄 Moving to: {channel.name}")
                    await existing_vc.move_to(channel)
                self.voice_client = existing_vc
            else:
                print(f"🔌 Connecting fresh to: {channel.name}")
                self.voice_client = await channel.connect()
            
            print(f"✅ Connected to voice channel: {channel.name}")
            return True
        except Exception as e:
            print(f"❌ Error connecting to voice channel: {type(e).__name__}: {e}")
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
        """
        Maintain a rolling buffer of downloaded songs.
        Downloads current + next N songs, cleans up old ones.
        """
        async with self._downloading_lock:
            # Get songs that should be downloaded (current + next N in queue)
            songs_to_keep = []
            
            if self.queue.current and not self.queue.current.is_downloaded:
                songs_to_keep.append(self.queue.current)
            
            # Determine how many songs to download from queue
            # If current exists, download N-1 more. If no current, download N.
            songs_needed = self._download_buffer_size - (1 if self.queue.current else 0)
            
            # Add next songs from queue
            for i, song in enumerate(list(self.queue.queue)[:songs_needed]):
                if not song.is_downloaded:
                    songs_to_keep.append(song)
            
            # Download any songs that aren't downloaded yet
            for song in songs_to_keep:
                if not song.is_downloaded:
                    self._currently_downloading.add(song.title)
                    print(f"📥 Buffer: Downloading {song.title[:40]}...", flush=True)
                    downloaded = await download_song(song.url, song.requester, timeout_seconds=90)
                    self._currently_downloading.discard(song.title)
                    if downloaded:
                        song.local_file = downloaded.local_file
                        song.duration = downloaded.duration
                        song.thumbnail = downloaded.thumbnail
                        print(f"✅ Buffer: Downloaded {song.title[:40]}", flush=True)
                    else:
                        print(f"❌ Buffer: Failed to download {song.title[:40]}", flush=True)
            
            # Cleanup songs beyond the buffer (keeping current + next N)
            songs_in_buffer_count = (1 if self.queue.current else 0) + songs_needed
            
            # Clean up songs beyond the buffer
            for i, song in enumerate(list(self.queue.queue)[songs_needed:], start=songs_needed):
                if song.is_downloaded:
                    print(f"🗑️ Buffer: Cleaning song #{i+1} (beyond buffer): {song.title[:40]}", flush=True)
                    song.cleanup()
    
    def play_next(self, error=None):
        """Callback when a song finishes playing."""
        if error:
            print(f"Player error: {error}")
        self._play_next_event.set()
    
    async def play(self, song: Song) -> bool:
        """Play a song."""
        print(f"🎵 play() called for: {song.title}")
        if not self.voice_client or not self.voice_client.is_connected():
            print("❌ No voice client or not connected")
            return False
        
        # Ensure song is downloaded
        if not song.is_downloaded:
            print(f"⚠️ Song not downloaded yet, downloading now: {song.title}")
            downloaded = await download_song(song.url, song.requester, timeout_seconds=90)
            if downloaded:
                song.local_file = downloaded.local_file
                song.duration = downloaded.duration
                song.thumbnail = downloaded.thumbnail
            else:
                print(f"❌ Failed to download song: {song.title}")
                return False
        
        try:
            print(f"🔊 Creating FFmpeg audio source...")
            print(f"   Local file: {song.local_file}")
            
            if not os.path.exists(song.local_file):
                print(f"❌ Audio file not found: {song.local_file}")
                return False
            
            source = discord.FFmpegPCMAudio(song.local_file, **FFMPEG_OPTIONS)
            print(f"✅ FFmpeg source created, starting playback...")
            
            # Wrap callback to cleanup after playback
            def after_play(error):
                if error:
                    print(f"❌ Playback error: {error}", flush=True)
                song.cleanup()  # Delete downloaded file
                self.play_next(error)
            
            self.voice_client.play(source, after=after_play)
            self.queue.current = song
            print(f"✅ Playback started for: {song.title}")
            return True
        except Exception as e:
            print(f"❌ Error playing song: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            song.cleanup()  # Clean up on error too
            return False
    
    async def start_player_loop(self):
        """Main player loop - plays songs from queue."""
        print("🔄 Player loop started")
        while True:
            self._play_next_event.clear()
            
            print("📋 Getting next song from queue...")
            song = self.queue.next()
            if not song:
                print("📭 No song in queue, checking if empty...")
                # Queue empty, wait for new songs
                await asyncio.sleep(0.5)
                if self.queue.is_empty():
                    print("🛑 Queue empty, exiting player loop")
                    break
                continue
            
            print(f"▶️ Playing next: {song.title}")
            
            # Maintain download buffer in background (non-blocking)
            asyncio.create_task(self.maintain_download_buffer())
            
            # Start playing the song (this ensures it's downloaded and metadata is populated)
            if not await self.play(song):
                print("❌ play() returned False, skipping to next")
                continue
            
            # Update now playing message AFTER song is downloaded and playing
            if self.now_playing_message:
                try:
                    embed = discord.Embed(
                        title="🎵 Dabar groja",
                        description=f"**[{song.title}]({song.url})**",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Trukmė", value=song.duration_str, inline=True)
                    embed.add_field(name="Eilėje", value=str(len(self.queue)), inline=True)
                    embed.add_field(name="Užsakė", value=song.requester, inline=True)
                    
                    # Show downloading status
                    if self._currently_downloading:
                        downloading_count = len(self._currently_downloading)
                        embed.add_field(
                            name="📥 Kraunama", 
                            value=f"{downloading_count} daina{'s' if downloading_count > 1 else ''}", 
                            inline=True
                        )
                    
                    if song.thumbnail:
                        embed.set_thumbnail(url=song.thumbnail)
                    
                    # Keep the same view
                    view = MusicControlView(self.bot, self.guild.id)
                    await self.now_playing_message.edit(embed=embed, view=view)
                except Exception as e:
                    print(f"⚠️ Failed to update now playing message: {e}", flush=True)
            
            # Wait for song to finish
            print("⏳ Waiting for song to finish...")
            await self._play_next_event.wait()
            print("✅ Song finished")
    
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


# Store players per guild
players: dict[int, MusicPlayer] = {}


class MusicControlView(discord.ui.View):
    """Control buttons for music playback."""
    
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)  # Persistent buttons
        self.bot = bot
        self.guild_id = guild_id
    
    def get_player(self) -> Optional[MusicPlayer]:
        return players.get(self.guild_id)
    
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
        player = self.get_player()
        
        embed = discord.Embed(title="📋 Muzikos eilė", color=discord.Color.blue())
        
        if not player:
            await interaction.response.send_message("📭 Nėra aktyvaus grotuvo", ephemeral=True, delete_after=5)
            return
        
        # Current song
        if player.queue.current:
            embed.add_field(
                name="▶️ Dabar groja",
                value=f"**{player.queue.current.title}** ({player.queue.current.duration_str})",
                inline=False
            )
        else:
            embed.add_field(
                name="▶️ Dabar groja",
                value="Niekas",
                inline=False
            )
        
        # Queue - show up to 20 songs with download status
        if player.queue.queue:
            queue_text = ""
            for i, song in enumerate(list(player.queue.queue)[:20], 1):
                # Show download status icon
                if song.is_downloaded:
                    status_icon = "✅"
                elif song.title in player._currently_downloading:
                    status_icon = "📥"
                else:
                    status_icon = "⏳"
                queue_text += f"{status_icon} {i}. {song.title[:45]} ({song.duration_str})\n"
            if len(player.queue.queue) > 20:
                queue_text += f"\n... ir dar {len(player.queue.queue) - 20} dainos"
            embed.add_field(name=f"📋 Eilėje ({len(player.queue.queue)} dainos)", value=queue_text, inline=False)
        else:
            embed.add_field(name="📋 Eilėje", value="Tuščia", inline=False)
        
        # Show playlist download progress if active
        if player.playlist_info['total'] > 0:
            pending = player.playlist_info['total'] - player.playlist_info['downloaded']
            if pending > 0:
                embed.add_field(
                    name="⬇️ Kraunama",
                    value=f"{pending} dainų dar kraunasi iš playlist'o",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=30)


def get_player(bot: commands.Bot, guild: discord.Guild) -> MusicPlayer:
    """Get or create a music player for a guild."""
    if guild.id not in players:
        players[guild.id] = MusicPlayer(bot, guild)
    
    # Sync voice client if bot is already connected
    player = players[guild.id]
    existing_vc = discord.utils.get(bot.voice_clients, guild=guild)
    if existing_vc and player.voice_client != existing_vc:
        player.voice_client = existing_vc
    
    return player


class Music(commands.Cog):
    """Music commands cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="play", description="Paleisti dainą arba playlist'ą iš YouTube, SoundCloud arba Spotify")
    @app_commands.describe(query="YouTube/SoundCloud/Spotify nuoroda arba paieškos užklausa")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song or playlist from YouTube, SoundCloud, or Spotify."""
        print(f"▶️ /play command received from {interaction.user.display_name}: {query}")
        
        # Check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            print("❌ User not in voice channel")
            await interaction.response.send_message(
                "❌ Tu turi būti voice kanale, kad galėtum groti muziką!",
                ephemeral=True
            )
            return
        
        print(f"📍 User is in voice channel: {interaction.user.voice.channel.name}")
        await interaction.response.defer()
        print("⏳ Response deferred")
        
        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        print(f"🎮 Got player for guild: {interaction.guild.name}")
        
        # Connect to voice channel
        print(f"🔌 Attempting to connect to: {voice_channel.name}")
        if not await player.connect(voice_channel):
            print("❌ Failed to connect to voice channel")
            await interaction.followup.send("❌ Nepavyko prisijungti prie voice kanalo!")
            return
        
        print("✅ Connected to voice channel, checking for playlist...")
        
        # Check if it's a playlist
        playlist_entries = await get_playlist_entries(query)
        
        if playlist_entries:
            # It's a playlist - add all songs to queue WITHOUT downloading
            print(f"📋 Found playlist with {len(playlist_entries)} songs", flush=True)
            
            # Create Song objects without downloading (lazy loading)
            for i, entry in enumerate(playlist_entries):
                song = Song(
                    title=entry['title'],
                    url=entry['url'],
                    local_file=None,  # Not downloaded yet
                    requester=interaction.user.display_name
                )
                player.queue.add(song)
                print(f"📋 Added to queue [{i+1}/{len(playlist_entries)}]: {song.title}", flush=True)
            
            # Show playlist added message
            embed = discord.Embed(
                title="📋 Playlist pridėtas į eilę",
                description=f"Pridėta **{len(playlist_entries)}** dainų",
                color=discord.Color.green()
            )
            embed.add_field(name="Pirmoji daina", value=playlist_entries[0]['title'][:50], inline=False)
            embed.add_field(name="Eilėje", value=f"{len(player.queue)} dainos", inline=True)
            embed.add_field(name="Užsakė", value=interaction.user.display_name, inline=True)
            
            view = MusicControlView(self.bot, interaction.guild.id)
            player.now_playing_message = await interaction.followup.send(embed=embed, view=view)
            
            # Start playing if not already
            if not player.voice_client.is_playing() and (player._player_task is None or player._player_task.done()):
                print("🎬 Starting player loop...")
                player._player_task = asyncio.create_task(player.start_player_loop())
            else:
                print("⏸️ Player already running, songs queued")
        else:
            # Single song
            print("🎵 Single song, downloading...")
            song = await get_song_info(query, interaction.user.display_name)
            if not song:
                print("❌ Failed to get song info")
                await interaction.followup.send("❌ Nepavyko rasti dainos. Patikrink nuorodą arba pabandyk kitą paiešką.")
                return
            
            print(f"🎵 Got song: {song.title} ({song.duration_str})")
            
            # Add to queue
            player.queue.add(song)
            print(f"📋 Added to queue. Queue length: {len(player.queue)}")
            
            # Create embed with control buttons
            embed = discord.Embed(
                title="🎵 Pridėta į eilę",
                description=f"**[{song.title}]({song.url})**",
                color=discord.Color.green()
            )
            embed.add_field(name="Trukmė", value=song.duration_str, inline=True)
            embed.add_field(name="Eilėje", value=str(len(player.queue)), inline=True)
            embed.add_field(name="Užsakė", value=song.requester, inline=True)
            
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            view = MusicControlView(self.bot, interaction.guild.id)
            player.now_playing_message = await interaction.followup.send(embed=embed, view=view)
            print("📤 Sent embed response with controls")
            
            # Start playing if not already
            print(f"🔍 Checking if should start playing: is_playing={player.voice_client.is_playing() if player.voice_client else 'no client'}, task={player._player_task}")
            if not player.voice_client.is_playing() and (player._player_task is None or player._player_task.done()):
                print("🎬 Starting player loop...")
                player._player_task = asyncio.create_task(player.start_player_loop())
            else:
                print("⏸️ Player already running, song queued")
    
    @app_commands.command(name="testplay", description="Test command - plays Rick Astley")
    async def testplay(self, interaction: discord.Interaction):
        """Test command that plays a known YouTube video."""
        TEST_URL = "https://www.youtube.com/watch?v=4kHl4FoK1Ys"
        print(f"🧪 /testplay command received from {interaction.user.display_name}", flush=True)
        
        # Check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Tu turi būti voice kanale!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        
        # Connect to voice channel
        if not await player.connect(voice_channel):
            await interaction.followup.send("❌ Nepavyko prisijungti prie voice kanalo!")
            return
        
        print(f"🧪 Testing with URL: {TEST_URL}", flush=True)
        
        # Get song info
        song = await get_song_info(TEST_URL, interaction.user.display_name)
        if not song:
            await interaction.followup.send("❌ Test failed - nepavyko gauti dainos info.")
            return
        
        print(f"🧪 Got song: {song.title}", flush=True)
        
        # Add to queue
        player.queue.add(song)
        
        embed = discord.Embed(
            title="🧪 Test Mode",
            description=f"Playing: **{song.title}**",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed)
        
        # Start playing
        if not player.voice_client.is_playing() and (player._player_task is None or player._player_task.done()):
            player._player_task = asyncio.create_task(player.start_player_loop())
    
    @app_commands.command(name="stop", description="Sustabdyti muziką ir išvalyti eilę")
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear the queue."""
        player = players.get(interaction.guild.id)
        
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ Botas nėra prijungtas prie voice kanalo!",
                ephemeral=True
            )
            return
        
        await player.disconnect()
        
        embed = discord.Embed(
            title="⏹️ Muzika sustabdyta",
            description="Eilė išvalyta ir atsijungta nuo voice kanalo.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        
        # Clean up player
        if interaction.guild.id in players:
            del players[interaction.guild.id]
    
    @app_commands.command(name="skip", description="Praleisti dabartinę dainą")
    async def skip(self, interaction: discord.Interaction):
        """Skip the current song."""
        player = players.get(interaction.guild.id)
        
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ Botas nėra prijungtas prie voice kanalo!",
                ephemeral=True
            )
            return
        
        if not player.voice_client.is_playing():
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True
            )
            return
        
        current_song = player.queue.current
        player.skip()
        
        embed = discord.Embed(
            title="⏭️ Praleista",
            description=f"Praleista: **{current_song.title if current_song else 'Unknown'}**",
            color=discord.Color.blue()
        )
        
        # Show what's next
        if player.queue.queue:
            next_song = player.queue.queue[0]
            embed.add_field(name="Kita daina", value=next_song.title, inline=False)
        else:
            embed.add_field(name="Eilė", value="Tuščia", inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="skipto", description="Peršokti į konkrečią dainą eilėje")
    @app_commands.describe(position="Dainos numeris eilėje (1, 2, 3...)")
    async def skipto(self, interaction: discord.Interaction, position: int):
        """Skip to a specific position in the queue."""
        player = players.get(interaction.guild.id)
        
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ Botas nėra prijungtas prie voice kanalo!",
                ephemeral=True
            )
            return
        
        if position < 1:
            await interaction.response.send_message(
                "❌ Pozicija turi būti 1 arba daugiau!",
                ephemeral=True
            )
            return
        
        if position > len(player.queue):
            await interaction.response.send_message(
                f"❌ Eilėje yra tik {len(player.queue)} dainų!",
                ephemeral=True
            )
            return
        
        # Defer the response to avoid timeout
        await interaction.response.defer()
        
        # Skip to position
        if player.queue.skip_to(position):
            # Stop current song to trigger next
            if player.voice_client.is_playing():
                player.voice_client.stop()
            
            target_song = player.queue.queue[0] if player.queue.queue else None
            
            embed = discord.Embed(
                title="⏩ Peršokta",
                description=f"Peršokta į poziciją **#{position}**",
                color=discord.Color.blue()
            )
            
            if target_song:
                embed.add_field(name="Kita daina", value=target_song.title, inline=False)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                "❌ Nepavyko peršokti į šią poziciją!",
                ephemeral=True
            )
    
    @app_commands.command(name="queue", description="Rodyti dainų eilę")
    async def queue_cmd(self, interaction: discord.Interaction):
        """Show the current queue."""
        player = players.get(interaction.guild.id)
        
        if not player or player.queue.is_empty():
            await interaction.response.send_message(
                "📭 Eilė tuščia!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🎶 Dainų eilė",
            color=discord.Color.purple()
        )
        
        # Current song
        if player.queue.current:
            embed.add_field(
                name="🎵 Dabar groja",
                value=f"**{player.queue.current.title}** [{player.queue.current.duration_str}]",
                inline=False
            )
        
        # Queue with download status
        if player.queue.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue.queue)[:10], 1):
                # Show download status icon
                if song.is_downloaded:
                    status_icon = "✅"
                elif song.title in player._currently_downloading:
                    status_icon = "📥"
                else:
                    status_icon = "⏳"
                queue_list.append(f"{status_icon} `{i}.` **{song.title}** [{song.duration_str}]")
            
            embed.add_field(
                name=f"📋 Eilėje ({len(player.queue)} dainų)",
                value="\n".join(queue_list),
                inline=False
            )
            
            if len(player.queue) > 10:
                embed.set_footer(text=f"...ir dar {len(player.queue) - 10} dainų")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="nowplaying", description="Rodyti dabartinę dainą")
    async def nowplaying(self, interaction: discord.Interaction):
        """Show the currently playing song."""
        player = players.get(interaction.guild.id)
        
        if not player or not player.queue.current:
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True
            )
            return
        
        song = player.queue.current
        embed = discord.Embed(
            title="🎵 Dabar groja",
            description=f"**[{song.title}]({song.url})**",
            color=discord.Color.green()
        )
        embed.add_field(name="Trukmė", value=song.duration_str, inline=True)
        embed.add_field(name="Užsakė", value=song.requester or "Unknown", inline=True)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Music(bot))
