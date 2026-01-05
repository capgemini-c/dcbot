import os
import random
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
import pytz

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Vilnius")

# Collection of daily messages
MESSAGES = [
    "ka sian?",
    "kada losiam?",
    "ka losiam siandien?"
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))


async def send_daily_message():
    """Send a random message to the configured channel."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        message = random.choice(MESSAGES)
        await channel.send(message)
        print(f"Sent daily message: {message}")
    else:
        print(f"Could not find channel with ID: {CHANNEL_ID}")


@bot.event
async def on_ready():
    print(f"🤖 {bot.user} is now online!")
    print(f"📢 Will send messages to channel ID: {CHANNEL_ID}")
    print(f"⏰ Scheduled for 8:00 AM {TIMEZONE}")
    
    # Sync slash commands
    await bot.tree.sync()
    print("✅ Slash commands synced!")
    
    # Schedule the daily message at 8 AM
    scheduler.add_job(
        send_daily_message,
        CronTrigger(hour=8, minute=0, timezone=pytz.timezone(TIMEZONE)),
        id="daily_message",
        replace_existing=True,
    )
    scheduler.start()


@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Respond to "jasna"
    if "jasna" in message.content.lower():
        await message.channel.send("toks ir draugelis...")
    
    # Process commands (so !ping etc still work)
    await bot.process_commands(message)


@bot.tree.command(name="kasian", description="Paklausk Boto ka sian")
async def kasian(interaction: discord.Interaction):
    """Slash command to trigger a random message."""
    message = random.choice(MESSAGES)
    await interaction.response.send_message(message)


@bot.command(name="ping")
async def ping(ctx):
    """Test command to check if the bot is alive."""
    await ctx.send("Pongas! 🏓")


@bot.command(name="test")
async def test_message(ctx):
    """Manually trigger a random message (for testing)."""
    message = random.choice(MESSAGES)
    await ctx.send(message)


@bot.command(name="messages")
async def list_messages(ctx):
    """List all possible messages."""
    msg_list = "\n".join(f"• {m}" for m in MESSAGES)
    await ctx.send(f"**Available messages:**\n{msg_list}")


# Simple web server to keep the bot alive on free hosting
async def health_check(request):
    return web.Response(text="Bot is alive!")


async def run_webserver():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server running on port {port}")


async def main():
    # Start web server
    await run_webserver()
    # Start Discord bot
    await bot.start(TOKEN)


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with your Discord bot token.")
        exit(1)
    
    if CHANNEL_ID == 0:
        print("❌ Error: CHANNEL_ID not found in environment variables!")
        print("Please add the channel ID where messages should be sent.")
        exit(1)
    
    asyncio.run(main())

