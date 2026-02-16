"""
Music module for Discord bot - YouTube playback via Selenium + PulseAudio.
"""

import asyncio
import os
import subprocess
from collections import deque
from dataclasses import dataclass
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from browser_audio import BrowserAudioStreamer

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

# ── System dependency checks ────────────────────────────────────

print("=" * 50, flush=True)
print("🎬 SYSTEM DEPENDENCIES", flush=True)
print("=" * 50, flush=True)

# FFmpeg
try:
    result = subprocess.run(
        ['ffmpeg', '-version'], capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        print(
            f"✅ FFmpeg: "
            f"{version_line.replace('ffmpeg version ', '')[:40]}",
            flush=True,
        )
    else:
        print("❌ FFmpeg: not working", flush=True)
except FileNotFoundError:
    print("❌ FFmpeg: NOT INSTALLED", flush=True)
except Exception as e:
    print(f"❌ FFmpeg: {e}", flush=True)

# PulseAudio
try:
    result = subprocess.run(
        ['pactl', 'info'], capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        print("✅ PulseAudio: running", flush=True)
    else:
        print(
            "⚠️ PulseAudio: not running (audio capture won't work)",
            flush=True,
        )
except FileNotFoundError:
    print(
        "⚠️ PulseAudio: not installed (audio capture won't work)",
        flush=True,
    )
except Exception as e:
    print(f"⚠️ PulseAudio: {e}", flush=True)

# Chromium
try:
    _chromium_found = False
    for _chromium_path in [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
    ]:
        if os.path.exists(_chromium_path):
            result = subprocess.run(
                [_chromium_path, '--version'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(
                    f"✅ Chromium: {result.stdout.strip()}", flush=True
                )
                _chromium_found = True
                break
    if not _chromium_found:
        print("⚠️ Chromium: not found", flush=True)
except Exception as e:
    print(f"⚠️ Chromium: {e}", flush=True)

print("=" * 50, flush=True)

# Check PyNaCl / libsodium
print("=" * 50, flush=True)
print("🔐 ENCRYPTION STATUS", flush=True)
print("=" * 50, flush=True)
try:
    import nacl
    print(f"✅ PyNaCl version: {nacl.__version__}", flush=True)
    from nacl.secret import SecretBox
    key = b'0' * 32
    box = SecretBox(key)
    box.encrypt(b'test')
    print("✅ Encryption test passed", flush=True)
except Exception as e:
    print(
        f"❌ PyNaCl/libsodium error: {type(e).__name__}: {e}",
        flush=True,
    )
    import traceback
    traceback.print_exc()
print("=" * 50, flush=True)


# ── Global instances ────────────────────────────────────────────

browser_streamer = BrowserAudioStreamer()

MAX_PLAYLIST_SONGS = 50


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Song:
    """Represents a song in the queue."""
    title: str
    url: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    requester: Optional[str] = None

    @property
    def duration_str(self) -> str:
        """Return formatted duration string."""
        return format_duration(self.duration)


# ── Helper functions ────────────────────────────────────────────

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


def validate_user_in_voice(
    interaction: discord.Interaction,
) -> tuple[bool, Optional[str]]:
    """
    Validate that user is connected to a voice channel.

    Args:
      interaction: Discord interaction from command

    Returns:
      Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not interaction.user.voice or not interaction.user.voice.channel:
        return (
            False,
            "❌ Tu turi būti voice kanale, kad galėtum groti muziką!",
        )
    return True, None


def validate_player_exists(
    player: Optional['MusicPlayer'],
    guild_id: int,
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


def validate_queue_not_empty(
    player: 'MusicPlayer',
) -> tuple[bool, Optional[str]]:
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
    queue_length: int,
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
            f"❌ Pozicija turi būti tarp 1 ir {queue_length}!",
        )
    return True, None


# ── Embed builder ───────────────────────────────────────────────

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
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Trukmė", value=song.duration_str, inline=True
        )
        embed.add_field(
            name="Užsakė",
            value=song.requester or "Unknown",
            inline=True,
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        return embed

    @staticmethod
    def queue(player: 'MusicPlayer') -> discord.Embed:
        """Create embed for queue display."""
        embed = discord.Embed(
            title="🎶 Dainų eilė",
            color=discord.Color.purple(),
        )

        # Current song
        if player.queue.current:
            current = player.queue.current
            embed.add_field(
                name="🎵 Dabar groja",
                value=(
                    f"**[{current.title[:50]}]({current.url})** "
                    f"[{current.duration_str}]"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="🎵 Dabar groja", value="Niekas", inline=False
            )

        # Queue list
        queue_length = len(player.queue.queue)
        if queue_length > 0:
            queue_list = []
            for i, song in enumerate(
                list(player.queue.queue)[:10], 1
            ):
                duration = song.duration_str if song.duration_str else "?"
                queue_list.append(
                    f"`{i}.` **{song.title[:40]}** [{duration}]"
                )

            # Lithuanian pluralization
            if queue_length == 1:
                plural_form = "daina"
            elif 2 <= queue_length <= 9:
                plural_form = "dainos"
            else:
                plural_form = "dainų"

            embed.add_field(
                name=f"📋 Eilėje ({queue_length} {plural_form})",
                value="\n".join(queue_list),
                inline=False,
            )

            if queue_length > 10:
                embed.add_field(
                    name="➕ Daugiau",
                    value=f"Ir dar {queue_length - 10} dainų...",
                    inline=False,
                )
        else:
            embed.add_field(
                name="📋 Eilėje", value="Tuščia", inline=False
            )

        return embed

    @staticmethod
    def playlist_added(
        playlist_entries: List[dict],
        queue_length: int,
        requester: str,
    ) -> discord.Embed:
        """Create embed for playlist added message."""
        embed = discord.Embed(
            title="📋 Playlist pridėtas į eilę",
            description=f"Pridėta **{len(playlist_entries)}** dainų",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Pirmoji daina",
            value=playlist_entries[0]['title'][:50],
            inline=False,
        )
        embed.add_field(
            name="Eilėje",
            value=f"{queue_length} dainos",
            inline=True,
        )
        embed.add_field(
            name="Užsakė", value=requester, inline=True
        )
        return embed

    @staticmethod
    def song_added(song: Song, queue_position: int) -> discord.Embed:
        """Create embed for song added to queue message."""
        embed = discord.Embed(
            title="✅ Pridėta į eilę",
            description=f"**[{song.title}]({song.url})**",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Pozicija eilėje",
            value=f"#{queue_position}",
            inline=True,
        )
        embed.add_field(
            name="Trukmė", value=song.duration_str, inline=True
        )
        embed.add_field(
            name="Užsakė", value=song.requester, inline=False
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        return embed

    @staticmethod
    def stopped() -> discord.Embed:
        """Create embed for stopped playback message."""
        return discord.Embed(
            title="⏹️ Muzika sustabdyta",
            description="Eilė išvalyta ir atsijungta nuo voice kanalo.",
            color=discord.Color.red(),
        )

    @staticmethod
    def skipped(
        current_song: Optional[Song],
        next_song: Optional[Song],
    ) -> discord.Embed:
        """Create embed for skipped song message."""
        current_title = (
            current_song.title if current_song else "Unknown"
        )
        embed = discord.Embed(
            title="⏭️ Praleista",
            description=f"Praleista: **{current_title}**",
            color=discord.Color.blue(),
        )
        if next_song:
            embed.add_field(
                name="Kita daina",
                value=next_song.title,
                inline=False,
            )
        else:
            embed.add_field(
                name="Eilė", value="Tuščia", inline=False
            )
        return embed

    @staticmethod
    def skipped_to(target_song: Song, position: int) -> discord.Embed:
        """Create embed for skip to position message."""
        embed = discord.Embed(
            title="⏭️ Peršokta",
            description=f"Peršokta į poziciją #{position}",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Kita daina",
            value=f"**{target_song.title}**",
            inline=False,
        )
        return embed

    @staticmethod
    def test_mode(song_title: str) -> discord.Embed:
        """Create embed for test command."""
        return discord.Embed(
            title="🧪 Test Mode",
            description=f"Playing: **{song_title}**",
            color=discord.Color.orange(),
        )


# ── Music queue ─────────────────────────────────────────────────

class MusicQueue:
    """Manages the song queue for a guild."""

    def __init__(self) -> None:
        self.queue: deque[Song] = deque()
        self.current: Optional[Song] = None
        self.loop: bool = False

    def add(self, song: Song) -> None:
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
        """Skip to a specific position in queue (1-indexed).

        Returns True if successful.
        """
        if position < 1 or position > len(self.queue):
            return False
        for _ in range(position - 1):
            if self.queue:
                self.queue.popleft()
        return True

    def clear(self) -> None:
        self.queue.clear()
        self.current = None

    def __len__(self) -> int:
        return len(self.queue)

    def is_empty(self) -> bool:
        return len(self.queue) == 0 and self.current is None


# ── URL validation ──────────────────────────────────────────────

class URLValidator:
    """Validates and categorizes YouTube URLs."""

    @staticmethod
    def is_url(text: str) -> bool:
        """Check if text is a URL."""
        return text.startswith('http://') or text.startswith('https://')

    @staticmethod
    def is_youtube(url: str) -> bool:
        """Check if URL is a YouTube link."""
        url_lower = url.lower()
        return any(
            domain in url_lower
            for domain in ['youtube.com', 'youtu.be']
        )

    @staticmethod
    def is_playlist(url: str) -> bool:
        """Check if URL contains a playlist."""
        return 'list=' in url or '/playlist?' in url


# ── Music player ────────────────────────────────────────────────

class MusicPlayer:
    """Handles music playback for a guild via Selenium + PulseAudio."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()
        self.voice_client: Optional[discord.VoiceClient] = None
        self._play_next_event = asyncio.Event()
        self._player_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self.now_playing_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None

    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Connect to a voice channel."""
        try:
            existing_vc = discord.utils.get(
                self.bot.voice_clients, guild=self.guild
            )
            if existing_vc:
                if existing_vc.channel.id != channel.id:
                    await existing_vc.move_to(channel)
                self.voice_client = existing_vc
            else:
                self.voice_client = await channel.connect()

            print(
                f"✅ Connected to voice channel: {channel.name}",
                flush=True,
            )
            return True
        except Exception as e:
            print(
                f"❌ Error connecting to voice: "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            import traceback
            traceback.print_exc()
            return False

    async def disconnect(self) -> None:
        """Disconnect from voice channel and clean up browser."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None

        self.queue.clear()

        if self._player_task:
            self._player_task.cancel()
            self._player_task = None

        # Clean up the guild's browser and PulseAudio sink
        await browser_streamer.cleanup(self.guild.id)

    def _build_now_playing_embed(self, song: Song) -> discord.Embed:
        """Build embed for now playing message with queue info."""
        embed = EmbedBuilder.now_playing(song)
        embed.set_field_at(
            1, name="Eilėje",
            value=str(len(self.queue)), inline=True,
        )
        return embed

    async def _update_now_playing_message(self, song: Song) -> None:
        """Update now playing message - edit or recreate at bottom."""
        if not self.text_channel:
            return

        embed = self._build_now_playing_embed(song)
        view = MusicControlView(self.bot, self.guild.id)

        is_last_message = False
        if self.now_playing_message:
            try:
                last_message = None
                async for message in self.text_channel.history(limit=1):
                    last_message = message
                    break

                if (
                    last_message
                    and last_message.id == self.now_playing_message.id
                ):
                    is_last_message = True
                    await self.now_playing_message.edit(
                        embed=embed, view=view
                    )
                    return
            except discord.errors.NotFound:
                self.now_playing_message = None
            except Exception as e:
                print(
                    f"⚠️ Failed to check/edit message: "
                    f"{type(e).__name__}: {e}",
                    flush=True,
                )

        if self.now_playing_message and not is_last_message:
            try:
                await self.now_playing_message.delete()
            except discord.errors.NotFound:
                pass
            except Exception as e:
                print(
                    f"⚠️ Failed to delete old message: "
                    f"{type(e).__name__}: {e}",
                    flush=True,
                )
            finally:
                self.now_playing_message = None

        try:
            self.now_playing_message = await self.text_channel.send(
                embed=embed, view=view
            )
        except Exception as e:
            print(
                f"⚠️ Failed to send now playing: "
                f"{type(e).__name__}: {e}",
                flush=True,
            )

    def play_next(self, error: Optional[Exception] = None) -> None:
        """Callback when a song finishes playing."""
        if error:
            print(f"Player error: {error}", flush=True)
        self._play_next_event.set()

    async def play(self, song: Song) -> bool:
        """Play a song via browser + PulseAudio streaming."""
        if not self.voice_client or not self.voice_client.is_connected():
            return False

        try:
            # Ensure browser exists for this guild
            driver = await browser_streamer.get_or_create_browser(
                self.guild.id
            )
            if not driver:
                print("❌ Failed to create browser", flush=True)
                return False

            # Navigate to the YouTube video and start playback
            success = await browser_streamer.play_video(
                self.guild.id, song.url
            )
            if not success:
                print(
                    f"❌ Failed to play video: {song.title}", flush=True
                )
                return False

            # Update song metadata from the video page
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None, browser_streamer.get_video_info, driver
            )
            if info.get('duration') and not song.duration:
                song.duration = info['duration']
            if info.get('thumbnail') and not song.thumbnail:
                song.thumbnail = info['thumbnail']
            if info.get('title') and song.title in (
                'Unknown', 'Kraunama...',
            ):
                song.title = info['title']

            # Create FFmpeg source from PulseAudio monitor
            source = browser_streamer.get_ffmpeg_source(self.guild.id)

            def after_play(error: Optional[Exception]) -> None:
                if error:
                    print(f"❌ Playback error: {error}", flush=True)
                self.play_next(error)

            self.voice_client.play(source, after=after_play)
            self.queue.current = song

            # Start monitoring video end state
            if self._monitor_task:
                self._monitor_task.cancel()
            self._monitor_task = asyncio.create_task(
                self._monitor_video()
            )

            return True
        except Exception as e:
            print(
                f"❌ Error playing song: {type(e).__name__}: {e}",
                flush=True,
            )
            import traceback
            traceback.print_exc()
            return False

    async def _monitor_video(self) -> None:
        """Monitor video playback and stop when video ends."""
        try:
            driver = browser_streamer._browsers.get(self.guild.id)
            if not driver:
                return

            loop = asyncio.get_event_loop()

            # Wait for video to start playing before monitoring
            await asyncio.sleep(3)

            while True:
                await asyncio.sleep(2)
                ended = await loop.run_in_executor(
                    None, browser_streamer.is_video_ended, driver
                )
                if ended:
                    print(
                        "🎵 Video ended, advancing queue", flush=True
                    )
                    if (
                        self.voice_client
                        and self.voice_client.is_playing()
                    ):
                        self.voice_client.stop()
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(
                f"⚠️ Video monitor error: {type(e).__name__}: {e}",
                flush=True,
            )

    async def start_player_loop(self) -> None:
        """Main player loop - plays songs from queue sequentially."""
        while True:
            self._play_next_event.clear()

            song = self.queue.next()
            if not song:
                await asyncio.sleep(0.5)
                if self.queue.is_empty():
                    print(
                        "🛑 Queue empty, exiting player loop",
                        flush=True,
                    )
                    break
                continue

            if not await self.play(song):
                continue

            await self._update_now_playing_message(song)
            await self._play_next_event.wait()

    def skip(self) -> bool:
        """Skip the current song."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            return True
        return False

    def stop(self) -> None:
        """Stop playback and clear queue."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        self.queue.clear()
        if self.voice_client:
            self.voice_client.stop()


# ── Player manager ──────────────────────────────────────────────

class PlayerManager:
    """Manages MusicPlayer instances per guild."""

    def __init__(self) -> None:
        self._players: dict[int, MusicPlayer] = {}

    def get(self, guild_id: int) -> Optional[MusicPlayer]:
        """Get player for a guild, returns None if doesn't exist."""
        return self._players.get(guild_id)

    def create_player(
        self, bot: commands.Bot, guild: discord.Guild
    ) -> MusicPlayer:
        """Create a new player for a guild."""
        player = MusicPlayer(bot, guild)
        self._players[guild.id] = player
        return player

    def get_or_create(
        self, bot: commands.Bot, guild: discord.Guild
    ) -> MusicPlayer:
        """Get existing player or create new one if doesn't exist."""
        if guild.id not in self._players:
            return self.create_player(bot, guild)

        player = self._players[guild.id]
        existing_vc = discord.utils.get(
            bot.voice_clients, guild=guild
        )
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


# ── Music control view ──────────────────────────────────────────

class MusicControlView(discord.ui.View):
    """Control buttons for music playback."""

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    def get_player(self) -> Optional[MusicPlayer]:
        return player_manager.get(self.guild_id)

    @discord.ui.button(
        label="⏸️ Pause",
        style=discord.ButtonStyle.secondary,
        custom_id="music_pause",
    )
    async def pause_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
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

    @discord.ui.button(
        label="⏭️ Skip",
        style=discord.ButtonStyle.primary,
        custom_id="music_skip",
    )
    async def skip_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        player = self.get_player()
        if player and player.skip():
            await interaction.response.send_message(
                "⏭️ Praleidžiama...",
                ephemeral=True, delete_after=3,
            )
        else:
            await interaction.response.send_message(
                "❌ Nėra ką praleisti",
                ephemeral=True, delete_after=3,
            )

    @discord.ui.button(
        label="⏹️ Stop",
        style=discord.ButtonStyle.danger,
        custom_id="music_stop",
    )
    async def stop_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        player = self.get_player()
        if player:
            player.stop()
            if player.voice_client:
                await player.voice_client.disconnect()
            await interaction.response.send_message(
                "⏹️ Muzika sustabdyta",
                ephemeral=True, delete_after=3,
            )
        else:
            await interaction.response.defer()

    @discord.ui.button(
        label="📋 Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="music_queue",
    )
    async def queue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        player = self.get_player()
        if not player:
            await interaction.followup.send(
                "📭 Nėra aktyvaus grotuvo", ephemeral=True
            )
            return
        embed = EmbedBuilder.queue(player)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Helpers ─────────────────────────────────────────────────────

def get_player(
    bot: commands.Bot, guild: discord.Guild
) -> MusicPlayer:
    """Get or create a music player for a guild."""
    return player_manager.get_or_create(bot, guild)


# ── Music cog ───────────────────────────────────────────────────

class Music(commands.Cog):
    """Music commands cog."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _add_playlist_to_queue(
        self,
        player: MusicPlayer,
        entries: List[dict],
        requester: str,
        interaction: discord.Interaction,
    ) -> None:
        """Add playlist entries to queue."""
        print(
            f"📋 Adding {len(entries)} songs from playlist", flush=True
        )
        for entry in entries:
            song = Song(
                title=entry['title'],
                url=entry['url'],
                requester=requester,
            )
            player.queue.add(song)

        embed = EmbedBuilder.playlist_added(
            entries, len(player.queue), requester
        )
        view = MusicControlView(self.bot, interaction.guild.id)
        player.now_playing_message = await interaction.followup.send(
            embed=embed, view=view
        )

    async def _add_single_song_to_queue(
        self,
        player: MusicPlayer,
        song: Song,
        interaction: discord.Interaction,
    ) -> None:
        """Add a single song to queue and send confirmation."""
        player.queue.add(song)
        embed = EmbedBuilder.song_added(song, len(player.queue))
        view = MusicControlView(self.bot, interaction.guild.id)
        player.now_playing_message = await interaction.followup.send(
            embed=embed, view=view
        )

    def _start_player_if_needed(self, player: MusicPlayer) -> None:
        """Start player loop if not already playing."""
        if not player.voice_client.is_playing() and (
            player._player_task is None
            or player._player_task.done()
        ):
            player._player_task = asyncio.create_task(
                player.start_player_loop()
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state updates - auto disconnect when alone."""
        voice_client = discord.utils.get(
            self.bot.voice_clients, guild=member.guild
        )
        if not voice_client:
            return

        channel = voice_client.channel
        human_members = [m for m in channel.members if not m.bot]

        if len(human_members) == 0:
            print(
                f"🚪 All users left '{channel.name}', "
                f"disconnecting in 30 seconds...",
            )
            await asyncio.sleep(30)

            voice_client = discord.utils.get(
                self.bot.voice_clients, guild=member.guild
            )
            if voice_client:
                channel = voice_client.channel
                human_members = [
                    m for m in channel.members if not m.bot
                ]
                if len(human_members) == 0:
                    print(
                        f"🔌 Auto-disconnecting from "
                        f"'{channel.name}'",
                        flush=True,
                    )
                    player = player_manager.get(member.guild.id)
                    if player:
                        await player.disconnect()
                        player_manager.remove(member.guild.id)

    @app_commands.command(
        name="play",
        description="Paleisti dainą arba playlist'ą iš YouTube",
    )
    @app_commands.describe(
        query="YouTube nuoroda arba paieškos užklausa"
    )
    async def play(
        self, interaction: discord.Interaction, query: str
    ) -> None:
        """Play a song or playlist from YouTube."""
        is_valid, error_msg = validate_user_in_voice(interaction)
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        await interaction.response.defer()

        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        player.text_channel = interaction.channel

        # Connect to voice channel
        if not await player.connect(voice_channel):
            await interaction.followup.send(
                "❌ Nepavyko prisijungti prie voice kanalo!"
            )
            return

        # Ensure browser is ready for this guild
        browser = await browser_streamer.get_or_create_browser(
            interaction.guild.id
        )
        if not browser:
            await interaction.followup.send(
                "❌ Nepavyko paleisti naršyklės! "
                "Patikrink ar Chromium ir PulseAudio veikia.",
                ephemeral=True,
            )
            return

        requester = interaction.user.display_name

        # Route based on query type
        if (
            URLValidator.is_url(query)
            and URLValidator.is_playlist(query)
        ):
            # Playlist URL
            entries = await browser_streamer.get_playlist_videos(
                interaction.guild.id, query
            )
            if entries:
                await self._add_playlist_to_queue(
                    player, entries, requester, interaction
                )
            else:
                await interaction.followup.send(
                    "❌ Nepavyko gauti playlist'o dainų. "
                    "Patikrink nuorodą."
                )
                return

        elif URLValidator.is_url(query):
            # Direct URL (YouTube or other)
            song = Song(
                title="Kraunama...",
                url=query,
                requester=requester,
            )
            await self._add_single_song_to_queue(
                player, song, interaction
            )

        else:
            # Search query - use Selenium to find video
            result = await browser_streamer.search_youtube(
                interaction.guild.id, query
            )
            if not result:
                await interaction.followup.send(
                    "❌ Nepavyko rasti dainos. Pabandyk kitą paiešką."
                )
                return
            song = Song(
                title=result['title'],
                url=result['url'],
                requester=requester,
            )
            await self._add_single_song_to_queue(
                player, song, interaction
            )

        # Start playing if not already
        self._start_player_if_needed(player)

    @app_commands.command(
        name="testplay",
        description="Test command - plays a known YouTube video",
    )
    async def testplay(
        self, interaction: discord.Interaction
    ) -> None:
        """Test command that plays a known YouTube video."""
        TEST_URL = "https://www.youtube.com/watch?v=4kHl4FoK1Ys"

        is_valid, error_msg = validate_user_in_voice(interaction)
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        await interaction.response.defer()

        voice_channel = interaction.user.voice.channel
        player = get_player(self.bot, interaction.guild)
        player.text_channel = interaction.channel

        if not await player.connect(voice_channel):
            await interaction.followup.send(
                "❌ Nepavyko prisijungti prie voice kanalo!"
            )
            return

        browser = await browser_streamer.get_or_create_browser(
            interaction.guild.id
        )
        if not browser:
            await interaction.followup.send(
                "❌ Nepavyko paleisti naršyklės!"
            )
            return

        song = Song(
            title="Test Video",
            url=TEST_URL,
            requester=interaction.user.display_name,
        )
        player.queue.add(song)

        await interaction.followup.send(
            embed=EmbedBuilder.test_mode(song.title)
        )

        if not player.voice_client.is_playing() and (
            player._player_task is None
            or player._player_task.done()
        ):
            player._player_task = asyncio.create_task(
                player.start_player_loop()
            )

    @app_commands.command(
        name="stop",
        description="Sustabdyti muziką ir išvalyti eilę",
    )
    async def stop(
        self, interaction: discord.Interaction
    ) -> None:
        """Stop playback and clear the queue."""
        player = player_manager.get(interaction.guild.id)
        is_valid, error_msg = validate_player_exists(
            player, interaction.guild.id
        )
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        await player.disconnect()
        await interaction.response.send_message(
            embed=EmbedBuilder.stopped()
        )
        player_manager.remove(interaction.guild.id)

    @app_commands.command(
        name="skip",
        description="Praleisti dabartinę dainą",
    )
    async def skip(
        self, interaction: discord.Interaction
    ) -> None:
        """Skip the current song."""
        player = player_manager.get(interaction.guild.id)
        is_valid, error_msg = validate_player_exists(
            player, interaction.guild.id
        )
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        if not player.voice_client.is_playing():
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True,
            )
            return

        current_song = player.queue.current
        player.skip()

        next_song = (
            player.queue.queue[0] if player.queue.queue else None
        )
        await interaction.response.send_message(
            embed=EmbedBuilder.skipped(current_song, next_song)
        )

    @app_commands.command(
        name="skipto",
        description="Peršokti į konkrečią dainą eilėje",
    )
    @app_commands.describe(
        position="Dainos numeris eilėje (1, 2, 3...)"
    )
    async def skipto(
        self, interaction: discord.Interaction, position: int
    ) -> None:
        """Skip to a specific position in the queue."""
        player = player_manager.get(interaction.guild.id)
        is_valid, error_msg = validate_player_exists(
            player, interaction.guild.id
        )
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        is_valid, error_msg = validate_skip_position(
            position, len(player.queue)
        )
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        await interaction.response.defer()

        if player.queue.skip_to(position):
            if player.voice_client.is_playing():
                player.voice_client.stop()

            target_song = (
                player.queue.queue[0]
                if player.queue.queue
                else None
            )
            if target_song:
                message = await interaction.followup.send(
                    embed=EmbedBuilder.skipped_to(
                        target_song, position
                    )
                )
                await asyncio.sleep(10)
                try:
                    await message.delete()
                except discord.errors.NotFound:
                    pass
                except Exception as e:
                    print(
                        f"⚠️ Failed to delete skipto message: {e}",
                        flush=True,
                    )
            else:
                await interaction.followup.send(
                    "⚠️ Peršokta, bet eilė tuščia",
                    ephemeral=True,
                )
        else:
            await interaction.followup.send(
                "❌ Nepavyko peršokti į šią poziciją!",
                ephemeral=True,
            )

    @app_commands.command(
        name="queue", description="Rodyti dainų eilę"
    )
    async def queue_cmd(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the current queue."""
        player = player_manager.get(interaction.guild.id)

        if not player:
            embed = discord.Embed(
                title="🎶 Dainų eilė",
                description="📭 Nėra aktyvaus grotuvo!",
                color=discord.Color.purple(),
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=EmbedBuilder.queue(player)
        )

    @app_commands.command(
        name="nowplaying", description="Rodyti dabartinę dainą"
    )
    async def nowplaying(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the currently playing song."""
        player = player_manager.get(interaction.guild.id)
        is_valid, error_msg = validate_player_exists(
            player, interaction.guild.id
        )
        if not is_valid:
            await interaction.response.send_message(
                error_msg, ephemeral=True
            )
            return

        if not player.queue.current:
            await interaction.response.send_message(
                "❌ Šiuo metu niekas negroja!",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=EmbedBuilder.now_playing(player.queue.current)
        )


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Music(bot))
