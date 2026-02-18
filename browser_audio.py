"""
Browser-based audio streaming for Discord bot.

Uses Selenium + Chrome + PulseAudio to play YouTube videos
and capture audio for Discord voice channels. Each guild gets
its own Chrome instance and PulseAudio null sink for audio isolation.
"""

import asyncio
import os
import subprocess
import threading
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
VIDEO_READY_TIMEOUT = 30
VIDEO_READY_POLL_INTERVAL = 0.5

CONSENT_COOKIE = {
    "name": "SOCS",
    "value": "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2Vy"
             "dmVyXzIwMjMwODI5LjA3X3AxGgJlbiACGgYIgJa5pwY",
    "domain": ".youtube.com",
    "path": "/",
}


def _log(msg: str) -> None:
    print(f"[BrowserAudio] {msg}", flush=True)


class BrowserAudioStreamer:
    """
    Manages per-guild Chrome browser instances and PulseAudio sinks
    for streaming YouTube audio to Discord voice channels.
    """

    def __init__(self) -> None:
        self._browsers: Dict[int, webdriver.Chrome] = {}
        self._sink_modules: Dict[int, int] = {}
        self._cookies_accepted: Dict[int, bool] = {}
        self._create_locks: Dict[int, asyncio.Lock] = {}
        self._browser_locks: Dict[int, threading.Lock] = {}

    def _get_create_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._create_locks:
            self._create_locks[guild_id] = asyncio.Lock()
        return self._create_locks[guild_id]

    def _get_browser_lock(self, guild_id: int) -> threading.Lock:
        if guild_id not in self._browser_locks:
            self._browser_locks[guild_id] = threading.Lock()
        return self._browser_locks[guild_id]

    def _get_sink_name(self, guild_id: int) -> str:
        return f"dcbot_guild_{guild_id}"

    # ── PulseAudio sink management ──────────────────────────────

    def _setup_audio_sink(self, guild_id: int) -> bool:
        sink_name = self._get_sink_name(guild_id)
        _log(f"🔊 Creating PulseAudio sink: {sink_name}")
        try:
            result = subprocess.run(
                [
                    "pactl", "load-module", "module-null-sink",
                    f"sink_name={sink_name}",
                    f"sink_properties=device.description={sink_name}",
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                module_index = int(result.stdout.strip())
                self._sink_modules[guild_id] = module_index
                _log(f"✅ PulseAudio sink created: {sink_name} (module {module_index})")

                subprocess.run(
                    ["pactl", "set-default-sink", sink_name],
                    capture_output=True, timeout=5,
                )
                _log(f"   Set as default sink")
                return True
            _log(f"❌ Failed to create PulseAudio sink: {result.stderr}")
            return False
        except Exception as e:
            _log(f"❌ Error creating PulseAudio sink: {type(e).__name__}: {e}")
            return False

    def _remove_audio_sink(self, guild_id: int) -> None:
        module_index = self._sink_modules.pop(guild_id, None)
        if module_index is not None:
            _log(f"🔊 Removing PulseAudio sink for guild {guild_id} (module {module_index})")
            try:
                subprocess.run(
                    ["pactl", "unload-module", str(module_index)],
                    capture_output=True, timeout=5,
                )
                _log(f"✅ PulseAudio sink removed for guild {guild_id}")
            except Exception as e:
                _log(f"⚠️ Error removing sink: {type(e).__name__}: {e}")

    def _ensure_sink_routing(self, guild_id: int) -> None:
        """Move all PulseAudio sink-inputs to the guild's sink."""
        sink_name = self._get_sink_name(guild_id)
        try:
            result = subprocess.run(
                ["pactl", "list", "sink-inputs", "short"],
                capture_output=True, text=True, timeout=5,
            )
            inputs = result.stdout.strip()
            _log(f"🔈 Sink-inputs: {inputs or '(none)'}")

            if not inputs:
                _log("⚠️ No sink-inputs — Chrome is not producing audio yet")
                return

            for line in inputs.split("\n"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    input_id = parts[0].strip()
                    move_result = subprocess.run(
                        ["pactl", "move-sink-input", input_id, sink_name],
                        capture_output=True, text=True, timeout=5,
                    )
                    if move_result.returncode == 0:
                        _log(f"   ✅ Moved sink-input {input_id} → {sink_name}")
                    else:
                        _log(f"   ⚠️ Failed to move sink-input {input_id}: {move_result.stderr.strip()}")

            sinks_result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=5,
            )
            _log(f"🔈 Sinks:\n{sinks_result.stdout.strip()}")
        except Exception as e:
            _log(f"⚠️ Sink routing error: {type(e).__name__}: {e}")

    # ── Chrome browser management ───────────────────────────────

    def _create_browser_sync(self, guild_id: int) -> Optional[webdriver.Chrome]:
        sink_name = self._get_sink_name(guild_id)
        _log(f"🌐 Creating Chrome browser for guild {guild_id}...")
        _log(f"   PULSE_SINK={sink_name}")

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
        options.add_argument("--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies")

        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin and os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
            _log(f"   Chrome binary: {chrome_bin}")
        else:
            for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
                if os.path.exists(path):
                    options.binary_location = path
                    _log(f"   Chrome binary: {path}")
                    break

        env = os.environ.copy()
        env["PULSE_SINK"] = sink_name

        try:
            chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
            if os.path.exists(chromedriver_path):
                _log(f"   Chromedriver: {chromedriver_path}")
                service = Service(executable_path=chromedriver_path, env=env)
            else:
                _log("   Chromedriver: from PATH")
                service = Service(env=env)

            _log("   Launching Chrome...")
            start_time = time.time()
            driver = webdriver.Chrome(service=service, options=options)
            _log(f"   Chrome launched in {time.time() - start_time:.1f}s")

            self._browsers[guild_id] = driver
            _log(f"✅ Chrome browser created for guild {guild_id}")

            self._set_consent_cookie(driver, guild_id)
            return driver
        except Exception as e:
            _log(f"❌ Error creating browser: {type(e).__name__}: {e}")
            return None

    def _set_consent_cookie(self, driver: webdriver.Chrome, guild_id: int) -> None:
        """Navigate to YouTube and set SOCS consent cookie to bypass GDPR dialog."""
        _log("🍪 Setting YouTube consent cookie...")
        try:
            driver.get("https://www.youtube.com")
            time.sleep(2)

            # First try clicking Accept All if dialog is visible
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    text = btn.text.lower().strip()
                except Exception:
                    continue
                if "accept all" in text:
                    _log(f"   Clicking consent button: '{text}'")
                    btn.click()
                    time.sleep(2)
                    self._cookies_accepted[guild_id] = True
                    _log("✅ Consent accepted via button click")
                    return

            # Fallback: set cookie directly
            driver.add_cookie(CONSENT_COOKIE)
            driver.refresh()
            time.sleep(1)
            self._cookies_accepted[guild_id] = True
            _log("✅ Consent cookie set programmatically")
        except Exception as e:
            _log(f"⚠️ Failed to set consent cookie: {type(e).__name__}: {e}")
            self._cookies_accepted[guild_id] = False

    async def get_or_create_browser(self, guild_id: int) -> Optional[webdriver.Chrome]:
        lock = self._get_create_lock(guild_id)
        async with lock:
            if guild_id in self._browsers:
                try:
                    self._browsers[guild_id].title
                    _log(f"♻️ Reusing existing browser for guild {guild_id}")
                    return self._browsers[guild_id]
                except WebDriverException:
                    _log(f"⚠️ Browser died for guild {guild_id}, recreating")
                    self._browsers.pop(guild_id, None)

            loop = asyncio.get_event_loop()

            if guild_id not in self._sink_modules:
                ok = await loop.run_in_executor(None, self._setup_audio_sink, guild_id)
                if not ok:
                    return None

            return await loop.run_in_executor(None, self._create_browser_sync, guild_id)

    # ── Consent dialog handling ─────────────────────────────────

    def _dismiss_consent_if_present(self, driver: webdriver.Chrome, guild_id: int) -> None:
        """Dismiss YouTube GDPR consent dialog if visible on current page."""
        try:
            consent_els = driver.find_elements(
                By.CSS_SELECTOR,
                "ytd-consent-bump-v2-lightbox, tp-yt-paper-dialog.ytd-consent-bump-v2-lightbox"
            )
            if not consent_els:
                _log("🍪 No consent dialog on page")
                return

            _log("🍪 Consent dialog detected on video page! Dismissing...")

            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    text = btn.text.lower().strip()
                except Exception:
                    continue
                if any(kw in text for kw in ["accept all", "agree all", "accept"]):
                    _log(f"   Clicking: '{text}'")
                    btn.click()
                    self._cookies_accepted[guild_id] = True
                    _log("✅ Consent dismissed")
                    time.sleep(3)
                    return

            for selector in ['button[aria-label*="Accept"]', 'button[aria-label*="Agree"]']:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
                if els:
                    els[0].click()
                    self._cookies_accepted[guild_id] = True
                    _log("✅ Consent dismissed (aria fallback)")
                    time.sleep(3)
                    return

            _log("⚠️ Consent dialog found but no accept button found!")
            try:
                driver.add_cookie(CONSENT_COOKIE)
                driver.refresh()
                time.sleep(3)
                _log("   Retried with programmatic cookie + refresh")
            except Exception:
                pass
        except Exception as e:
            _log(f"⚠️ Consent handling error: {type(e).__name__}: {e}")

    # ── Video playback ──────────────────────────────────────────

    def _trigger_playback(self, driver: webdriver.Chrome) -> None:
        """Trigger video playback via YouTube player API and HTML5 video element."""
        driver.execute_script("""
            // YouTube player API
            const player = document.querySelector('#movie_player');
            if (player) {
                if (player.playVideo) player.playVideo();
                if (player.unMute) player.unMute();
                if (player.setVolume) player.setVolume(100);
            }
            // HTML5 video element
            const video = document.querySelector('video');
            if (video) {
                video.muted = false;
                video.volume = 1.0;
                if (video.paused) video.play().catch(() => {});
            }
        """)

    def _skip_ads(self, driver: webdriver.Chrome) -> None:
        """Check for and skip YouTube ads."""
        try:
            skip_btns = driver.find_elements(
                By.CSS_SELECTOR,
                ".ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button"
            )
            for btn in skip_btns:
                if btn.is_displayed():
                    btn.click()
                    _log("   ⏭️ Ad skipped")
                    time.sleep(1)
                    return
            _log("   No ads detected")
        except Exception:
            pass

    def _get_video_state(self, driver: webdriver.Chrome) -> Optional[dict]:
        """Get comprehensive video and player state for debugging."""
        return driver.execute_script("""
            const v = document.querySelector('video');
            if (!v) return null;
            const p = document.querySelector('#movie_player');
            const state = {
                readyState: v.readyState,
                networkState: v.networkState,
                currentTime: v.currentTime,
                duration: isNaN(v.duration) ? null : v.duration,
                paused: v.paused,
                muted: v.muted,
                volume: v.volume,
                hasSrc: !!(v.src && v.src.length > 5),
                error: v.error ? v.error.code : null
            };
            if (p && p.getPlayerState) {
                try { state.playerState = p.getPlayerState(); } catch(e) {}
            }
            return state;
        """)

    def _wait_for_video_ready(self, driver: webdriver.Chrome) -> bool:
        """Wait until the video is actually playing (currentTime advancing)."""
        _log("   Waiting for video to buffer and play...")
        start = time.time()
        last_log_time = 0
        retry_play_count = 0

        while time.time() - start < VIDEO_READY_TIMEOUT:
            state = self._get_video_state(driver)
            if not state:
                time.sleep(VIDEO_READY_POLL_INTERVAL)
                continue

            # Video is playing when it has data and time is advancing
            if state.get('readyState', 0) >= 3 and state.get('currentTime', 0) > 0:
                elapsed = time.time() - start
                _log(
                    f"   ✅ Video playing! readyState={state['readyState']} "
                    f"currentTime={state['currentTime']:.1f}s "
                    f"duration={state.get('duration')} "
                    f"(waited {elapsed:.1f}s)"
                )
                return True

            # Retry playback if stuck
            elapsed = time.time() - start
            if elapsed > 3 and retry_play_count < 5 and int(elapsed) % 4 == 0:
                if state.get('paused') or state.get('readyState', 0) == 0:
                    retry_play_count += 1
                    _log(f"   🔄 Retry playback attempt {retry_play_count}...")
                    self._trigger_playback(driver)

            # Log every ~3 seconds
            if int(elapsed) >= last_log_time + 3:
                last_log_time = int(elapsed)
                _log(f"   ⏳ Waiting ({elapsed:.0f}s): {state}")

            time.sleep(VIDEO_READY_POLL_INTERVAL)

        # Timeout — get final state for debugging
        final = self._get_video_state(driver)
        elapsed = time.time() - start
        _log(f"   ❌ Video NOT ready after {elapsed:.1f}s: {final}")
        return False

    def _play_video_sync(self, driver: webdriver.Chrome, guild_id: int, url: str) -> bool:
        lock = self._get_browser_lock(guild_id)
        with lock:
            return self._play_video_locked(driver, guild_id, url)

    def _play_video_locked(self, driver: webdriver.Chrome, guild_id: int, url: str) -> bool:
        """Navigate to a YouTube video and start playback."""
        _log(f"▶️ Playing: {url}")
        total_start = time.time()
        try:
            # 1. Navigate directly to video URL
            _log("   Step 1: Navigating to video URL...")
            nav_start = time.time()
            driver.get(url)
            _log(f"   Page loaded in {time.time() - nav_start:.1f}s — title: {driver.title}")

            # 2. Dismiss consent dialog if it appears
            self._dismiss_consent_if_present(driver, guild_id)

            # 3. Wait for <video> element
            _log("   Step 2: Waiting for <video> element...")
            wait_start = time.time()
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "video"))
            )
            _log(f"   <video> found in {time.time() - wait_start:.1f}s")

            # 4. Wait for YouTube player to initialize
            _log("   Step 3: Waiting for YouTube player init...")
            time.sleep(3)

            # Log initial state before triggering play
            initial_state = self._get_video_state(driver)
            _log(f"   Initial video state: {initial_state}")

            # 5. Trigger playback
            _log("   Step 4: Triggering playback...")
            self._trigger_playback(driver)

            # Also try clicking the large play button
            try:
                play_btns = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".ytp-large-play-button, .ytp-play-button[aria-label*='Play']"
                )
                for btn in play_btns:
                    if btn.is_displayed():
                        btn.click()
                        _log("   Clicked YouTube play button")
                        break
            except Exception:
                pass

            # 6. Handle ads
            _log("   Step 5: Checking for ads...")
            self._skip_ads(driver)

            # 7. Re-trigger playback (in case ad interrupted)
            self._trigger_playback(driver)

            # 8. Wait for video to actually start playing
            _log("   Step 6: Verifying playback...")
            ready = self._wait_for_video_ready(driver)

            if not ready:
                _log("⚠️ Video did not start playing!")
                try:
                    driver.save_screenshot("/tmp/yt_playback_failed.png")
                    _log("📸 Debug screenshot saved to /tmp/yt_playback_failed.png")
                except Exception:
                    pass

                page_state = driver.execute_script("""
                    const r = {};
                    const c = document.querySelector('ytd-consent-bump-v2-lightbox');
                    r.consentVisible = !!c;
                    const e = document.querySelector('.ytp-error');
                    r.errorOverlay = e ? e.innerText.substring(0, 200) : null;
                    r.url = window.location.href;
                    r.title = document.title;
                    return r;
                """)
                _log(f"   Page debug info: {page_state}")

            # 9. Verify and fix audio routing
            self._ensure_sink_routing(guild_id)

            total_elapsed = time.time() - total_start
            _log(f"🎵 Video playback setup done in {total_elapsed:.1f}s: {url[:60]}")
            return True

        except TimeoutException:
            elapsed = time.time() - total_start
            _log(f"❌ Timeout waiting for video after {elapsed:.1f}s: {url[:60]}")
            return False
        except Exception as e:
            elapsed = time.time() - total_start
            _log(f"❌ Error playing video after {elapsed:.1f}s: {type(e).__name__}: {e}")
            return False

    async def play_video(self, guild_id: int, url: str) -> bool:
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(f"❌ play_video: no browser for guild {guild_id}")
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._play_video_sync, driver, guild_id, url)

    # ── YouTube search ──────────────────────────────────────────

    def _search_youtube_sync(self, driver: webdriver.Chrome, guild_id: int, query: str) -> Optional[Dict[str, str]]:
        lock = self._get_browser_lock(guild_id)
        with lock:
            return self._search_youtube_locked(driver, guild_id, query)

    def _search_youtube_locked(self, driver: webdriver.Chrome, guild_id: int, query: str) -> Optional[Dict[str, str]]:
        _log(f"🔍 Searching YouTube for: '{query}'")
        start_time = time.time()
        try:
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.youtube.com/results?search_query={encoded}"
            _log(f"   Navigating to: {search_url[:80]}")
            driver.get(search_url)

            self._dismiss_consent_if_present(driver, guild_id)

            _log(f"   Search page loaded in {time.time() - start_time:.1f}s")
            _log("   Waiting for search results...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ytd-video-renderer"))
            )

            results = driver.find_elements(By.CSS_SELECTOR, "ytd-video-renderer")
            _log(f"   Found {len(results)} video results")

            first = driver.find_element(By.CSS_SELECTOR, "ytd-video-renderer a#video-title")
            title = first.get_attribute("title") or first.text
            url = first.get_attribute("href")

            elapsed = time.time() - start_time
            if url and title:
                _log(f"✅ Search result in {elapsed:.1f}s: '{title[:50]}' - {url}")
                return {"title": title.strip(), "url": url}
            _log("⚠️ Search result missing title or URL")
            return None
        except TimeoutException:
            _log(f"❌ YouTube search timeout after {time.time() - start_time:.1f}s for: '{query}'")
            return None
        except Exception as e:
            _log(f"❌ YouTube search error after {time.time() - start_time:.1f}s: {type(e).__name__}: {e}")
            return None

    async def search_youtube(self, guild_id: int, query: str) -> Optional[Dict[str, str]]:
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(f"❌ search_youtube: no browser for guild {guild_id}")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_youtube_sync, driver, guild_id, query)

    # ── Playlist scraping ───────────────────────────────────────

    def _get_playlist_videos_sync(self, driver: webdriver.Chrome, guild_id: int, url: str) -> List[Dict[str, str]]:
        lock = self._get_browser_lock(guild_id)
        with lock:
            return self._get_playlist_locked(driver, guild_id, url)

    def _get_playlist_locked(self, driver: webdriver.Chrome, guild_id: int, url: str) -> List[Dict[str, str]]:
        _log(f"📋 Loading playlist: {url[:80]}")
        start_time = time.time()
        try:
            _log("   Navigating to playlist page...")
            driver.get(url)

            self._dismiss_consent_if_present(driver, guild_id)

            _log(f"   Playlist page loaded in {time.time() - start_time:.1f}s")
            _log("   Waiting for playlist items...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ytd-playlist-video-renderer"))
            )

            _log("   Scrolling to load playlist entries...")
            last_count = 0
            for scroll_num in range(10):
                entries = driver.find_elements(By.CSS_SELECTOR, "ytd-playlist-video-renderer")
                current_count = len(entries)
                _log(f"   Scroll {scroll_num + 1}: {current_count} entries loaded")
                if current_count >= MAX_PLAYLIST_SONGS or current_count == last_count:
                    break
                last_count = current_count
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
                time.sleep(1.5)

            entries = driver.find_elements(By.CSS_SELECTOR, "ytd-playlist-video-renderer")
            _log(f"   Total entries found: {len(entries)}")

            videos: List[Dict[str, str]] = []
            for i, entry in enumerate(entries[:MAX_PLAYLIST_SONGS]):
                try:
                    title_el = entry.find_element(By.CSS_SELECTOR, "#video-title")
                    title = title_el.get_attribute("title") or title_el.text
                    href = title_el.get_attribute("href")
                    if title and href:
                        videos.append({"title": title.strip(), "url": href})
                except NoSuchElementException:
                    _log(f"   ⚠️ Entry {i} missing title element")
                    continue

            elapsed = time.time() - start_time
            _log(f"✅ Scraped {len(videos)} videos from playlist in {elapsed:.1f}s")
            return videos
        except TimeoutException:
            _log(f"❌ Timeout loading playlist after {time.time() - start_time:.1f}s: {url[:60]}")
            return []
        except Exception as e:
            _log(f"❌ Playlist scraping error after {time.time() - start_time:.1f}s: {type(e).__name__}: {e}")
            return []

    async def get_playlist_videos(self, guild_id: int, url: str) -> List[Dict[str, str]]:
        driver = self._browsers.get(guild_id)
        if not driver:
            _log(f"❌ get_playlist_videos: no browser for guild {guild_id}")
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_playlist_videos_sync, driver, guild_id, url)

    # ── Video info & state ──────────────────────────────────────

    def get_video_info(self, driver: webdriver.Chrome) -> Dict:
        try:
            info = driver.execute_script("""
                const video = document.querySelector('video');
                const titleEl = document.querySelector(
                    'h1.ytd-watch-metadata yt-formatted-string, '
                    + '#title h1 yt-formatted-string'
                );
                const thumb = document.querySelector('meta[property="og:image"]');
                return {
                    title: titleEl ? titleEl.textContent.trim() : document.title,
                    duration: video && !isNaN(video.duration) ? Math.round(video.duration) : null,
                    thumbnail: thumb ? thumb.content : null
                };
            """) or {}
            _log(f"📊 Video info: title='{info.get('title', '?')[:40]}' duration={info.get('duration')}s")
            return info
        except Exception as e:
            _log(f"⚠️ Error getting video info: {type(e).__name__}: {e}")
            return {}

    def is_video_ended(self, driver: webdriver.Chrome) -> bool:
        try:
            result = driver.execute_script("""
                const v = document.querySelector('video');
                if (!v) return {ended: true, reason: 'no video element'};
                return {
                    ended: v.ended,
                    paused: v.paused,
                    currentTime: Math.round(v.currentTime),
                    duration: isNaN(v.duration) ? null : Math.round(v.duration),
                    readyState: v.readyState
                };
            """)
            if isinstance(result, dict):
                if result.get('ended'):
                    _log(f"🏁 Video ended: {result}")
                return result.get('ended', True)
            return True
        except Exception as e:
            _log(f"⚠️ is_video_ended error: {type(e).__name__}: {e}")
            return True

    # ── FFmpeg source for Discord ───────────────────────────────

    def get_ffmpeg_source(self, guild_id: int) -> discord.FFmpegPCMAudio:
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
        _log(f"🧹 Cleaning up guild {guild_id}...")
        driver = self._browsers.pop(guild_id, None)
        if driver:
            try:
                driver.quit()
                _log(f"✅ Browser closed for guild {guild_id}")
            except Exception as e:
                _log(f"⚠️ Error closing browser: {type(e).__name__}: {e}")

        self._remove_audio_sink(guild_id)
        self._cookies_accepted.pop(guild_id, None)

    async def cleanup(self, guild_id: int) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._cleanup_sync, guild_id)

    async def cleanup_all(self) -> None:
        guild_ids = list(self._browsers.keys())
        _log(f"🧹 Cleaning up all {len(guild_ids)} browsers...")
        for guild_id in guild_ids:
            await self.cleanup(guild_id)
