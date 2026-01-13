"""
Music module for Discord bot - supports YouTube, SoundCloud, and Spotify links.
"""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

# yt-dlp for audio extraction
import yt_dlp

# Suppress yt-dlp noise
yt_dlp.utils.bug_reports_message = lambda: ''

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


@dataclass
class Song:
    """Represents a song in the queue."""
    title: str
    url: str
    stream_url: str
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
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
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


async def get_song_info(query: str, requester: str) -> Optional[Song]:
    """
    Extract song information from a URL or search query.
    Supports YouTube, SoundCloud, and Spotify.
    """
    try:
        loop = asyncio.get_event_loop()
        
        # Handle Spotify URLs - convert to YouTube search
        if is_spotify_url(query):
            search_query = await extract_spotify_query(query)
            if search_query:
                query = f"ytsearch:{search_query}"
            else:
                # If we couldn't extract, try searching by the original URL text
                query = f"ytsearch:{query}"
        
        # Extract info
        data = await loop.run_in_executor(
            None,
            lambda: ytdl.extract_info(query, download=False)
        )
        
        if not data:
            return None
        
        # Handle search results
        if 'entries' in data:
            data = data['entries'][0] if data['entries'] else None
            if not data:
                return None
        
        # Get the best audio URL
        stream_url = data.get('url')
        if not stream_url:
            # Try to get from formats
            formats = data.get('formats', [])
            for f in formats:
                if f.get('acodec') != 'none':
                    stream_url = f.get('url')
                    break
        
        if not stream_url:
            return None
        
        return Song(
            title=data.get('title', 'Unknown'),
            url=data.get('webpage_url', query),
            stream_url=stream_url,
            duration=data.get('duration'),
            thumbnail=data.get('thumbnail'),
            requester=requester
        )
    
    except Exception as e:
        print(f"Error extracting song info: {e}")
        return None


class MusicPlayer:
    """Handles music playback for a guild."""
    
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()
        self.voice_client: Optional[discord.VoiceClient] = None
        self._play_next_event = asyncio.Event()
        self._player_task: Optional[asyncio.Task] = None
    
    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Connect to a voice channel."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect()
            return True
        except Exception as e:
            print(f"Error connecting to voice channel: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from voice channel."""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        self.queue.clear()
        if self._player_task:
            self._player_task.cancel()
    
    def play_next(self, error=None):
        """Callback when a song finishes playing."""
        if error:
            print(f"Player error: {error}")
        self._play_next_event.set()
    
    async def play(self, song: Song) -> bool:
        """Play a song."""
        if not self.voice_client or not self.voice_client.is_connected():
            return False
        
        try:
            source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
            self.voice_client.play(source, after=self.play_next)
            self.queue.current = song
            return True
        except Exception as e:
            print(f"Error playing song: {e}")
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
                    break
                continue
            
            if not await self.play(song):
                continue
            
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


# Store players per guild
players: dict[int, MusicPlayer] = {}


def get_player(bot: commands.Bot, guild: discord.Guild) -> MusicPlayer:
    """Get or create a music player for a guild."""
    if guild.id not in players:
        players[guild.id] = MusicPlayer(bot, guild)
    return players[guild.id]


class Music(commands.Cog):
    """Music commands cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="play", description="Paleisti dainą iš YouTube, SoundCloud arba Spotify")
    @app_commands.describe(query="YouTube/SoundCloud/Spotify nuoroda arba paieškos užklausa")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song from YouTube, SoundCloud, or Spotify."""
        # Check if user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ Tu turi būti voice kanale, kad galėtum groti muziką!",
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
        
        # Get song info
        song = await get_song_info(query, interaction.user.display_name)
        if not song:
            await interaction.followup.send("❌ Nepavyko rasti dainos. Patikrink nuorodą arba pabandyk kitą paiešką.")
            return
        
        # Add to queue
        player.queue.add(song)
        
        # Create embed
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
        
        await interaction.followup.send(embed=embed)
        
        # Start playing if not already
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
        
        # Queue
        if player.queue.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue.queue)[:10], 1):
                queue_list.append(f"`{i}.` **{song.title}** [{song.duration_str}]")
            
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
