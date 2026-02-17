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


def _log(msg: str) -> None:
    """Print a log message with flush for Docker compatibility."""
    print(f"[BrowserAudio] {msg}", flush=True)


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
        self._warmed_up: Dict[int, bool] = {}

    def _get_sink_name(self, guild_id: int) -> str:
        """Get PulseAudio sink name for a guild."""
        return f"dcbot_guild_{guild_id}"

    # ── PulseAudio sink management ──────────────────────────────

    def _setup_audio_sink(self, guild_id: int) -> bool:
        """Create a PulseAudio null sink for a guild (synchronous)."""
        sink_name = self._get_sink_name(guild_id)
        _log(f"🔊 Creating PulseAudio sink: {sink_name}")
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
                _log(
                    f"✅ PulseAudio sink created: {sink_name} "
                    f"(module {module_index})"
                )
                return True
            _log(
                f"❌ Failed to create PulseAudio sink: {result.stderr}"
            )
            return False
        except Exception as e:
            _log(
                f"❌ Error creating PulseAudio sink: "
                f"{type(e).__name__}: {e}"
            )
            return False

    def _remove_audio_sink(self, guild_id: int) -> None:
        """Remove PulseAudio null sink for a guild (synchronous)."""
        module_index = self._sink_modules.pop(guild_id, None)
        if module_index is not None:
            _log(
                f"🔊 Removing PulseAudio sink for guild {guild_id} "
                f"(module {module_index})"
            )
            try:
                subprocess.run(
                    ["pactl", "unload-module", str(module_index)],
                    capture_output=True,
                    timeout=5,
                )
                _log(
                    f"✅ PulseAudio sink removed for guild {guild_id}"
                )
            except Exception as e:
                _log(
                    f"⚠️ Error removing sink: {type(e).__name__}: {e}"
                )

    # ── Chrome browser management ───────────────────────────────

    def _create_browser_sync(
        self, guild_id: int
    ) -> Optional[webdriver.Chrome]:
        """Create a Chrome browser for a guild (synchronous)."""
        sink_name = self._get_sink_name(guild_id)
        _log(f"🌐 Creating Chrome browser for guild {guild_id}...")
        _log(f"   PULSE_SINK will be set to: {sink_name}")

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

        # Use system Chromium binary — check env var first, then known paths
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin and os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
            _log(f"   Using Chrome binary from CHROME_BIN: {chrome_bin}")
        else:
            for path in [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome",
            ]:
                if os.path.exists(path):
                    options.binary_location = path
                    _log(f"   Using Chrome binary: {path}")
                    break

        # Route Chrome audio to the guild's PulseAudio sink
        env = os.environ.copy()
        env["PULSE_SINK"] = sink_name

        try:
            chromedriver_path = os.environ.get(
                "CHROMEDRIVER_PATH", "/usr/bin/chromedriver"
            )
            if os.path.exists(chromedriver_path):
                _log(f"   Using chromedriver: {chromedriver_path}")
                service = Service(
                    executable_path=chromedriver_path, env=env
                )
            else:
                _log("   Using chromedriver from PATH")
                service = Service(env=env)

            _log("   Launching Chrome process...")
            start_time = time.time()
            driver = webdriver.Chrome(service=service, options=options)
            elapsed = time.time() - start_time
            _log(f"   Chrome launched in {elapsed:.1f}s")

            self._browsers[guild_id] = driver
            self._cookies_accepted[guild_id] = False
            _log(f"✅ Chrome browser created for guild {guild_id}")
            return driver
        except Exception as e:
            _log(f"❌ Error creating browser: {type(e).__name__}: {e}")
            return None

    async def get_or_create_browser(
        self, guild_id: int
    ) -> Optional[webdriver.Chrome]:
        """Get an existing browser or create a new one for the guild."""
        if guild_id in self._browsers:
            try:
                self._browsers[guild_id].title
                _log(
                    f"♻️ Reusing existing browser for guild {guild_id}"
                )
                return self._browsers[guild_id]
            except WebDriverException:
                _log(
                    f"⚠️ Browser died for guild {guild_id}, recreating"
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

    # ── Prewarm ─────────────────────────────────────────────────

    async def prewarm(self, guild_id: int) -> bool:
        """
        Prewarm a browser for a guild: create browser, accept cookies,
        and navigate to YouTube so it's ready for instant playback.
        """
        _log(f"🔥 Prewarming browser for guild {guild_id}...")
        start_time = time.time()

        driver = await self.get_or_create_browser(guild_id)
        if not driver:
            _log(f"❌ Prewarm failed: could not create browser")
            return False

        # Accept cookies and load YouTube homepage
        if not self._cookies_accepted.get(guild_id, False):
            loop = asyncio.get_event_loop()
            _log(f"🍪 Prewarming: navigating to YouTube for cookies...")
            await loop.run_in_executor(
                None, self._ensure_cookies_sync, driver, guild_id
            )

        self._warmed_up[guild_id] = True
        elapsed = time.time() - start_time
        _log(
            f"✅ Browser prewarmed for guild {guild_id} "
            f"in {elapsed:.1f}s"
        )
        return True

    # ── Cookie consent ──────────────────────────────────────────

    def _accept_cookies_sync(self, driver: webdriver.Chrome) -> bool:
        """Accept YouTube cookie consent dialog (synchronous)."""
        _log("🍪 Looking for cookie consent dialog...")
        try:
            time.sleep(2)

            buttons = driver.find_elements(By.TAG_NAME, "button")
            _log(f"   Found {len(buttons)} buttons on page")
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
                    _log(f"   Clicking cookie button: '{text}'")
                    button.click()
                    _log("✅ Cookie consent accepted")
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
                    _log(
                        f"   Clicking cookie button via: {selector}"
                    )
                    els[0].click()
                    _log("✅ Cookie consent accepted (aria)")
                    time.sleep(1)
                    return True

            _log("ℹ️ No cookie dialog found (may not be needed)")
            return True
        except Exception as e:
            _log(f"⚠️ Cookie handling error: {type(e).__name__}: {e}")
            return True

    def _ensure_cookies_sync(
        self, driver: webdriver.Chrome, guild_id: int
    ) -> None:
        """Navigate to YouTube and handle cookies if needed (sync)."""
        if self._cookies_accepted.get(guild_id, False):
            _log("🍪 Cookies already accepted, skipping")
            return
        _log("🍪 Navigating to YouTube to handle cookies...")
        start_time = time.time()
        driver.get("https://www.youtube.com")
        elapsed = time.time() - start_time
        _log(f"   YouTube loaded in {elapsed:.1f}s")
        _log(f"   Page title: {driver.title}")
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
        _log(f"▶️ Starting video playback: {url}")
        total_start = time.time()
        try:
            self._ensure_cookies_sync(driver, guild_id)

            _log(f"   Navigating to video URL...")
            nav_start = time.time()
            driver.get(url)
            nav_elapsed = time.time() - nav_start
            _log(f"   Page navigation took {nav_elapsed:.1f}s")
            _log(f"   Page title: {driver.title}")

            # Wait for <video> element
            _log("   Waiting for <video> element...")
            wait_start = time.time()
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "video"))
            )
            wait_elapsed = time.time() - wait_start
            _log(f"   <video> element found in {wait_elapsed:.1f}s")

            # Get initial video state
            video_state = driver.execute_script("""
                const v = document.querySelector('video');
                if (!v) return null;
                return {
                    paused: v.paused,
                    muted: v.muted,
                    volume: v.volume,
                    readyState: v.readyState,
                    currentTime: v.currentTime,
                    duration: isNaN(v.duration) ? null : v.duration,
                    src: v.src ? v.src.substring(0, 80) : 'none'
                };
            """)
            _log(f"   Video state before play: {video_state}")

            # Unmute and start playback
            _log("   Setting video: muted=false, volume=1.0, play()")
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
            _log("   Checking for ads (2s wait)...")
            time.sleep(2)
            try:
                skip_btns = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".ytp-ad-skip-button, "
                    ".ytp-ad-skip-button-modern, "
                    ".ytp-skip-ad-button",
                )
                if skip_btns:
                    _log(
                        f"   Found {len(skip_btns)} ad skip button(s)"
                    )
                    for btn in skip_btns:
                        if btn.is_displayed():
                            btn.click()
                            _log("   Clicked ad skip button")
                            time.sleep(1)
                            break
                else:
                    _log("   No ad skip buttons found")
            except Exception as e:
                _log(f"   Ad skip check error: {type(e).__name__}: {e}")

            # Ensure playback after potential ad skip
            driver.execute_script("""
                const video = document.querySelector('video');
                if (video && video.paused) {
                    video.play().catch(() => {});
                }
            """)

            # Verify final state
            final_state = driver.execute_script("""
                const v = document.querySelector('video');
                if (!v) return null;
                return {
                    paused: v.paused,
                    muted: v.muted,
                    volume: v.volume,
                    readyState: v.readyState,
                    currentTime: v.currentTime,
                    duration: isNaN(v.duration) ? null : v.duration
                };
            """)
            _log(f"   Video state after play: {final_state}")

            total_elapsed = time.time() - total_start
            _log(
                f"🎵 Video playback started in {total_elapsed:.1f}s: "
                f"{url[:60]}"
            )
            return True
        except TimeoutException:
            elapsed = time.time() - total_start
            _log(
                f"❌ Timeout waiting for video after {elapsed:.1f}s: "
                f"{url[:60]}"
            )
            return False
        except Exception as e:
            elapsed = time.time() - total_start
            _log(
                f"❌ Error playing video after {elapsed:.1f}s: "
                f"{type(e).__name__}: {e}"
            )
            return False

    async def play_video(self, guild_id: int, url: str) -> bool:
        """Navigate to a YouTube video and start playback."""
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(f"❌ play_video: no browser for guild {guild_id}")
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
        _log(f"🔍 Searching YouTube for: '{query}'")
        start_time = time.time()
        try:
            self._ensure_cookies_sync(driver, guild_id)

            encoded = urllib.parse.quote(query)
            search_url = (
                f"https://www.youtube.com/results?search_query={encoded}"
            )
            _log(f"   Navigating to: {search_url[:80]}")
            driver.get(search_url)

            nav_elapsed = time.time() - start_time
            _log(f"   Search page loaded in {nav_elapsed:.1f}s")

            # Wait for video result renderers
            _log("   Waiting for search results...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ytd-video-renderer")
                )
            )

            results = driver.find_elements(
                By.CSS_SELECTOR, "ytd-video-renderer"
            )
            _log(f"   Found {len(results)} video results")

            first = driver.find_element(
                By.CSS_SELECTOR, "ytd-video-renderer a#video-title"
            )
            title = first.get_attribute("title") or first.text
            url = first.get_attribute("href")

            elapsed = time.time() - start_time
            if url and title:
                _log(
                    f"✅ Search result in {elapsed:.1f}s: "
                    f"'{title[:50]}' - {url}"
                )
                return {"title": title.strip(), "url": url}
            _log(f"⚠️ Search result missing title or URL")
            return None
        except TimeoutException:
            elapsed = time.time() - start_time
            _log(
                f"❌ YouTube search timeout after {elapsed:.1f}s "
                f"for: '{query}'"
            )
            return None
        except Exception as e:
            elapsed = time.time() - start_time
            _log(
                f"❌ YouTube search error after {elapsed:.1f}s: "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def search_youtube(
        self, guild_id: int, query: str
    ) -> Optional[Dict[str, str]]:
        """Search YouTube and return first video result."""
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(
                f"❌ search_youtube: no browser for guild {guild_id}"
            )
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
        _log(f"📋 Loading playlist: {url[:80]}")
        start_time = time.time()
        try:
            self._ensure_cookies_sync(driver, guild_id)

            _log("   Navigating to playlist page...")
            driver.get(url)

            nav_elapsed = time.time() - start_time
            _log(f"   Playlist page loaded in {nav_elapsed:.1f}s")

            # Wait for playlist item renderers
            _log("   Waiting for playlist items...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ytd-playlist-video-renderer")
                )
            )

            # Scroll to load more items
            _log("   Scrolling to load playlist entries...")
            last_count = 0
            for scroll_num in range(10):
                entries = driver.find_elements(
                    By.CSS_SELECTOR, "ytd-playlist-video-renderer"
                )
                current_count = len(entries)
                _log(
                    f"   Scroll {scroll_num + 1}: "
                    f"{current_count} entries loaded"
                )
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
            _log(f"   Total entries found: {len(entries)}")

            videos: List[Dict[str, str]] = []
            for i, entry in enumerate(entries[:MAX_PLAYLIST_SONGS]):
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
                    _log(f"   ⚠️ Entry {i} missing title element")
                    continue

            elapsed = time.time() - start_time
            _log(
                f"✅ Scraped {len(videos)} videos from playlist "
                f"in {elapsed:.1f}s"
            )
            return videos
        except TimeoutException:
            elapsed = time.time() - start_time
            _log(
                f"❌ Timeout loading playlist after {elapsed:.1f}s: "
                f"{url[:60]}"
            )
            return []
        except Exception as e:
            elapsed = time.time() - start_time
            _log(
                f"❌ Playlist scraping error after {elapsed:.1f}s: "
                f"{type(e).__name__}: {e}"
            )
            return []

    async def get_playlist_videos(
        self, guild_id: int, url: str
    ) -> List[Dict[str, str]]:
        """Scrape playlist entries from YouTube."""
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(
                f"❌ get_playlist_videos: no browser for "
                f"guild {guild_id}"
            )
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_playlist_videos_sync, driver, guild_id, url
        )

    # ── Video info & state ──────────────────────────────────────

    def get_video_info(self, driver: webdriver.Chrome) -> Dict:
        """Get current video's title, duration, and thumbnail."""
        try:
            info = driver.execute_script("""
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
            _log(
                f"📊 Video info: title='{info.get('title', '?')[:40]}' "
                f"duration={info.get('duration')}s"
            )
            return info
        except Exception as e:
            _log(
                f"⚠️ Error getting video info: "
                f"{type(e).__name__}: {e}"
            )
            return {}

    def is_video_ended(self, driver: webdriver.Chrome) -> bool:
        """Check if the current video has finished playing."""
        try:
            result = driver.execute_script("""
                const v = document.querySelector('video');
                if (!v) return {ended: true, reason: 'no video element'};
                return {
                    ended: v.ended,
                    paused: v.paused,
                    currentTime: Math.round(v.currentTime),
                    duration: isNaN(v.duration) ? null
                        : Math.round(v.duration),
                    readyState: v.readyState
                };
            """)
            if isinstance(result, dict):
                if result.get('ended'):
                    _log(f"🏁 Video ended: {result}")
                return result.get('ended', True)
            return True
        except Exception as e:
            _log(
                f"⚠️ is_video_ended error: {type(e).__name__}: {e}"
            )
            return True

    # ── FFmpeg source for Discord ───────────────────────────────

    def get_ffmpeg_source(self, guild_id: int) -> discord.FFmpegPCMAudio:
        """Create FFmpeg audio source from the guild's PulseAudio monitor."""
        sink_name = self._get_sink_name(guild_id)
        source_name = f"{sink_name}.monitor"
        _log(f"🔈 Creating FFmpeg source from: {source_name}")
        return discord.FFmpegPCMAudio(
            source_name,
            before_options="-f pulse",
            options="-vn",
        )

    # ── Cleanup ─────────────────────────────────────────────────

    def _cleanup_sync(self, guild_id: int) -> None:
        """Clean up browser and PulseAudio sink for a guild (sync)."""
        _log(f"🧹 Cleaning up guild {guild_id}...")
        driver = self._browsers.pop(guild_id, None)
        if driver:
            try:
                driver.quit()
                _log(f"✅ Browser closed for guild {guild_id}")
            except Exception as e:
                _log(
                    f"⚠️ Error closing browser: "
                    f"{type(e).__name__}: {e}"
                )

        self._remove_audio_sink(guild_id)
        self._cookies_accepted.pop(guild_id, None)
        self._warmed_up.pop(guild_id, None)

    async def cleanup(self, guild_id: int) -> None:
        """Clean up browser and PulseAudio sink for a guild."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._cleanup_sync, guild_id)

    async def cleanup_all(self) -> None:
        """Clean up all browsers and PulseAudio sinks."""
        guild_ids = list(self._browsers.keys())
        _log(f"🧹 Cleaning up all {len(guild_ids)} browsers...")
        for guild_id in guild_ids:
            await self.cleanup(guild_id)
