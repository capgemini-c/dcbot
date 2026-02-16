"""
Browser-based audio streaming for Discord bot.

Uses Selenium + Chrome + PulseAudio to play YouTube videos
and capture audio for Discord voice channels. Each guild gets
its own Chrome instance and PulseAudio null sink for audio isolation.
"""

import asyncio
import os
import subprocess
import time
import urllib.parse
from typing import Optional, Dict, List

import discord
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

MAX_PLAYLIST_SONGS = 50


class BrowserAudioStreamer:
    """
    Manages per-guild Chrome browser instances and PulseAudio sinks
    for streaming YouTube audio to Discord voice channels.

    Each guild gets:
    - A dedicated PulseAudio null sink for audio isolation
    - A Chrome browser instance whose audio routes to that sink
    """

    def __init__(self) -> None:
        self._browsers: Dict[int, webdriver.Chrome] = {}
        self._sink_modules: Dict[int, int] = {}
        self._cookies_accepted: Dict[int, bool] = {}

    def _get_sink_name(self, guild_id: int) -> str:
        """Get PulseAudio sink name for a guild."""
        return f"dcbot_guild_{guild_id}"

    # ── PulseAudio sink management ──────────────────────────────

    def _setup_audio_sink(self, guild_id: int) -> bool:
        """Create a PulseAudio null sink for a guild (synchronous)."""
        sink_name = self._get_sink_name(guild_id)
        try:
            result = subprocess.run(
                [
                    "pactl", "load-module", "module-null-sink",
                    f"sink_name={sink_name}",
                    f"sink_properties=device.description={sink_name}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                module_index = int(result.stdout.strip())
                self._sink_modules[guild_id] = module_index
                print(
                    f"✅ PulseAudio sink created: {sink_name} "
                    f"(module {module_index})",
                    flush=True,
                )
                return True
            print(
                f"❌ Failed to create PulseAudio sink: {result.stderr}",
                flush=True,
            )
            return False
        except Exception as e:
            print(
                f"❌ Error creating PulseAudio sink: "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            return False

    def _remove_audio_sink(self, guild_id: int) -> None:
        """Remove PulseAudio null sink for a guild (synchronous)."""
        module_index = self._sink_modules.pop(guild_id, None)
        if module_index is not None:
            try:
                subprocess.run(
                    ["pactl", "unload-module", str(module_index)],
                    capture_output=True,
                    timeout=5,
                )
                print(
                    f"✅ PulseAudio sink removed for guild {guild_id}",
                    flush=True,
                )
            except Exception as e:
                print(
                    f"⚠️ Error removing sink: {type(e).__name__}: {e}",
                    flush=True,
                )

    # ── Chrome browser management ───────────────────────────────

    def _create_browser_sync(
        self, guild_id: int
    ) -> Optional[webdriver.Chrome]:
        """Create a Chrome browser for a guild (synchronous).

        Audio is routed to the guild's PulseAudio sink via the
        PULSE_SINK environment variable set on the chromedriver
        process, which Chrome inherits.
        """
        sink_name = self._get_sink_name(guild_id)

        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-infobars")

        # Use system Chromium binary if available (Docker)
        for path in [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
        ]:
            if os.path.exists(path):
                options.binary_location = path
                break

        # Route Chrome audio to the guild's PulseAudio sink
        env = os.environ.copy()
        env["PULSE_SINK"] = sink_name

        try:
            chromedriver_path = "/usr/bin/chromedriver"
            if os.path.exists(chromedriver_path):
                service = Service(
                    executable_path=chromedriver_path, env=env
                )
            else:
                service = Service(env=env)

            driver = webdriver.Chrome(service=service, options=options)
            self._browsers[guild_id] = driver
            self._cookies_accepted[guild_id] = False
            print(
                f"✅ Chrome browser created for guild {guild_id}",
                flush=True,
            )
            return driver
        except Exception as e:
            print(
                f"❌ Error creating browser: {type(e).__name__}: {e}",
                flush=True,
            )
            return None

    async def get_or_create_browser(
        self, guild_id: int
    ) -> Optional[webdriver.Chrome]:
        """Get an existing browser or create a new one for the guild."""
        if guild_id in self._browsers:
            try:
                # Verify browser is still alive
                self._browsers[guild_id].title
                return self._browsers[guild_id]
            except WebDriverException:
                print(
                    f"⚠️ Browser died for guild {guild_id}, recreating",
                    flush=True,
                )
                self._browsers.pop(guild_id, None)

        loop = asyncio.get_event_loop()

        # Create PulseAudio sink if needed
        if guild_id not in self._sink_modules:
            ok = await loop.run_in_executor(
                None, self._setup_audio_sink, guild_id
            )
            if not ok:
                return None

        # Create browser
        return await loop.run_in_executor(
            None, self._create_browser_sync, guild_id
        )

    # ── Cookie consent ──────────────────────────────────────────

    def _accept_cookies_sync(self, driver: webdriver.Chrome) -> bool:
        """Accept YouTube cookie consent dialog (synchronous)."""
        try:
            time.sleep(2)

            # Look for accept button by visible text
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    text = button.text.lower().strip()
                except Exception:
                    continue
                if any(
                    kw in text
                    for kw in [
                        "accept all", "accept", "agree all", "agree",
                    ]
                ):
                    button.click()
                    print("✅ Cookie consent accepted", flush=True)
                    time.sleep(1)
                    return True

            # Fallback: aria-label based search
            for selector in [
                'button[aria-label*="Accept"]',
                'button[aria-label*="accept"]',
                'button[aria-label*="Agree"]',
            ]:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
                if els:
                    els[0].click()
                    print(
                        "✅ Cookie consent accepted (aria)", flush=True
                    )
                    time.sleep(1)
                    return True

            print("ℹ️ No cookie dialog found", flush=True)
            return True
        except Exception as e:
            print(
                f"⚠️ Cookie handling error: {type(e).__name__}: {e}",
                flush=True,
            )
            return True

    def _ensure_cookies_sync(
        self, driver: webdriver.Chrome, guild_id: int
    ) -> None:
        """Navigate to YouTube and handle cookies if needed (sync)."""
        if self._cookies_accepted.get(guild_id, False):
            return
        driver.get("https://www.youtube.com")
        if self._accept_cookies_sync(driver):
            self._cookies_accepted[guild_id] = True

    # ── Video playback ──────────────────────────────────────────

    def _play_video_sync(
        self,
        driver: webdriver.Chrome,
        guild_id: int,
        url: str,
    ) -> bool:
        """Navigate to a YouTube video and start playback (sync)."""
        try:
            self._ensure_cookies_sync(driver, guild_id)

            driver.get(url)

            # Wait for <video> element
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "video"))
            )

            # Unmute and start playback
            driver.execute_script("""
                const video = document.querySelector('video');
                if (video) {
                    video.muted = false;
                    video.volume = 1.0;
                    if (video.paused) {
                        video.play().catch(() => {});
                    }
                }
            """)

            # Try to skip YouTube ads
            time.sleep(2)
            try:
                skip_btns = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".ytp-ad-skip-button, "
                    ".ytp-ad-skip-button-modern, "
                    ".ytp-skip-ad-button",
                )
                for btn in skip_btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1)
                        break
            except Exception:
                pass

            # Ensure playback after potential ad skip
            driver.execute_script("""
                const video = document.querySelector('video');
                if (video && video.paused) {
                    video.play().catch(() => {});
                }
            """)

            print(f"🎵 Playing video: {url[:60]}", flush=True)
            return True
        except TimeoutException:
            print(f"❌ Timeout waiting for video: {url[:60]}", flush=True)
            return False
        except Exception as e:
            print(
                f"❌ Error playing video: {type(e).__name__}: {e}",
                flush=True,
            )
            return False

    async def play_video(self, guild_id: int, url: str) -> bool:
        """Navigate to a YouTube video and start playback."""
        driver = self._browsers.get(guild_id)
        if not driver:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._play_video_sync, driver, guild_id, url
        )

    # ── YouTube search ──────────────────────────────────────────

    def _search_youtube_sync(
        self,
        driver: webdriver.Chrome,
        guild_id: int,
        query: str,
    ) -> Optional[Dict[str, str]]:
        """Search YouTube and return first video result (sync)."""
        try:
            self._ensure_cookies_sync(driver, guild_id)

            encoded = urllib.parse.quote(query)
            driver.get(
                f"https://www.youtube.com/results?search_query={encoded}"
            )

            # Wait for video result renderers
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ytd-video-renderer")
                )
            )

            first = driver.find_element(
                By.CSS_SELECTOR, "ytd-video-renderer a#video-title"
            )
            title = first.get_attribute("title") or first.text
            url = first.get_attribute("href")

            if url and title:
                print(
                    f"🔍 Search result: {title[:50]} - {url}",
                    flush=True,
                )
                return {"title": title.strip(), "url": url}
            return None
        except Exception as e:
            print(
                f"❌ YouTube search error: {type(e).__name__}: {e}",
                flush=True,
            )
            return None

    async def search_youtube(
        self, guild_id: int, query: str
    ) -> Optional[Dict[str, str]]:
        """Search YouTube and return first video result."""
        driver = self._browsers.get(guild_id)
        if not driver:
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._search_youtube_sync, driver, guild_id, query
        )

    # ── Playlist scraping ───────────────────────────────────────

    def _get_playlist_videos_sync(
        self,
        driver: webdriver.Chrome,
        guild_id: int,
        url: str,
    ) -> List[Dict[str, str]]:
        """Scrape playlist entries from YouTube (synchronous)."""
        try:
            self._ensure_cookies_sync(driver, guild_id)

            driver.get(url)

            # Wait for playlist item renderers
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ytd-playlist-video-renderer")
                )
            )

            # Scroll to load more items (YouTube lazy-loads playlist entries)
            last_count = 0
            for _ in range(10):
                entries = driver.find_elements(
                    By.CSS_SELECTOR, "ytd-playlist-video-renderer"
                )
                current_count = len(entries)
                if (
                    current_count >= MAX_PLAYLIST_SONGS
                    or current_count == last_count
                ):
                    break
                last_count = current_count
                driver.execute_script(
                    "window.scrollTo(0, "
                    "document.documentElement.scrollHeight)"
                )
                time.sleep(1.5)

            entries = driver.find_elements(
                By.CSS_SELECTOR, "ytd-playlist-video-renderer"
            )
            videos: List[Dict[str, str]] = []
            for entry in entries[:MAX_PLAYLIST_SONGS]:
                try:
                    title_el = entry.find_element(
                        By.CSS_SELECTOR, "#video-title"
                    )
                    title = (
                        title_el.get_attribute("title") or title_el.text
                    )
                    href = title_el.get_attribute("href")
                    if title and href:
                        videos.append({
                            "title": title.strip(), "url": href
                        })
                except NoSuchElementException:
                    continue

            print(
                f"📋 Found {len(videos)} videos in playlist", flush=True
            )
            return videos
        except TimeoutException:
            print(
                f"❌ Timeout loading playlist: {url[:60]}", flush=True
            )
            return []
        except Exception as e:
            print(
                f"❌ Playlist scraping error: {type(e).__name__}: {e}",
                flush=True,
            )
            return []

    async def get_playlist_videos(
        self, guild_id: int, url: str
    ) -> List[Dict[str, str]]:
        """Scrape playlist entries from YouTube."""
        driver = self._browsers.get(guild_id)
        if not driver:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_playlist_videos_sync, driver, guild_id, url
        )

    # ── Video info & state ──────────────────────────────────────

    def get_video_info(self, driver: webdriver.Chrome) -> Dict:
        """Get current video's title, duration, and thumbnail."""
        try:
            return driver.execute_script("""
                const video = document.querySelector('video');
                const titleEl = document.querySelector(
                    'h1.ytd-watch-metadata yt-formatted-string, '
                    + '#title h1 yt-formatted-string'
                );
                const thumb = document.querySelector(
                    'meta[property="og:image"]'
                );
                return {
                    title: titleEl
                        ? titleEl.textContent.trim()
                        : document.title,
                    duration: video && !isNaN(video.duration)
                        ? Math.round(video.duration)
                        : null,
                    thumbnail: thumb ? thumb.content : null
                };
            """) or {}
        except Exception as e:
            print(
                f"⚠️ Error getting video info: {type(e).__name__}: {e}",
                flush=True,
            )
            return {}

    def is_video_ended(self, driver: webdriver.Chrome) -> bool:
        """Check if the current video has finished playing."""
        try:
            return driver.execute_script(
                "const v = document.querySelector('video');"
                "return v ? v.ended : true;"
            )
        except Exception:
            return True

    # ── FFmpeg source for Discord ───────────────────────────────

    def get_ffmpeg_source(self, guild_id: int) -> discord.FFmpegPCMAudio:
        """Create FFmpeg audio source from the guild's PulseAudio monitor."""
        sink_name = self._get_sink_name(guild_id)
        return discord.FFmpegPCMAudio(
            f"{sink_name}.monitor",
            before_options="-f pulse",
            options="-vn",
        )

    # ── Cleanup ─────────────────────────────────────────────────

    def _cleanup_sync(self, guild_id: int) -> None:
        """Clean up browser and PulseAudio sink for a guild (sync)."""
        driver = self._browsers.pop(guild_id, None)
        if driver:
            try:
                driver.quit()
                print(
                    f"✅ Browser closed for guild {guild_id}", flush=True
                )
            except Exception as e:
                print(
                    f"⚠️ Error closing browser: "
                    f"{type(e).__name__}: {e}",
                    flush=True,
                )

        self._remove_audio_sink(guild_id)
        self._cookies_accepted.pop(guild_id, None)

    async def cleanup(self, guild_id: int) -> None:
        """Clean up browser and PulseAudio sink for a guild."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._cleanup_sync, guild_id)

    async def cleanup_all(self) -> None:
        """Clean up all browsers and PulseAudio sinks."""
        guild_ids = list(self._browsers.keys())
        for guild_id in guild_ids:
            await self.cleanup(guild_id)
