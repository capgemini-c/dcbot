import os
import random
import asyncio
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
import pytz

from news import fetch_rytas_news

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Vilnius")

# User IDs to tag for games (comma-separated in env)
GAME_USER_IDS = [
    int(uid.strip()) 
    for uid in os.getenv("GAME_USER_IDS", "").split(",") 
    if uid.strip()
]

# Collection of daily messages
MESSAGES = [
    "ką šian?",
    "kada lošiam?",
    "ką lošiam šiandien?"
]

# CS messages
CS_MESSAGES = [
    "einam pašaudyt pew pew",
    "teroristai, einam terorizuoti!"
]

# Load skanduotes from JSON file
SKANDUOTES_FILE = os.path.join(os.path.dirname(__file__), "skanduotes.json")
with open(SKANDUOTES_FILE, "r", encoding="utf-8") as f:
    SKANDUOTES = json.load(f)["skanduotes"]

# Track which items have been used (reset when all are used)
used_skanduotes_indices = set()
used_messages_indices = set()


def get_random_message():
    """Get a random message without repeating until all are used."""
    global used_messages_indices
    
    if len(used_messages_indices) >= len(MESSAGES):
        used_messages_indices = set()
    
    available = [i for i in range(len(MESSAGES)) if i not in used_messages_indices]
    chosen = random.choice(available)
    used_messages_indices.add(chosen)
    
    return MESSAGES[chosen]


def get_random_skanduote():
    """Get a random skanduote without repeating until all are used."""
    global used_skanduotes_indices
    
    if len(used_skanduotes_indices) >= len(SKANDUOTES):
        used_skanduotes_indices = set()
    
    available = [i for i in range(len(SKANDUOTES)) if i not in used_skanduotes_indices]
    chosen = random.choice(available)
    used_skanduotes_indices.add(chosen)
    
    return SKANDUOTES[chosen]


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))


async def send_daily_message():
    """Send a random message to the configured channel."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        message = get_random_message()
        await channel.send(message)
        print(f"Sent daily message: {message}")
    else:
        print(f"Could not find channel with ID: {CHANNEL_ID}")


@bot.event
async def on_ready():
    print(f"🤖 {bot.user} is now online!")
    print(f"📢 Will send messages to channel ID: {CHANNEL_ID}")
    print(f"⏰ Scheduled for 8:00 AM {TIMEZONE}")
    
    # Load music cog
    try:
        await bot.load_extension("music")
        print("🎵 Music cog loaded!")
    except Exception as e:
        print(f"❌ Failed to load music cog: {e}")
    
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
    
    content_lower = message.content.lower()
    
    # Respond to "jasna"
    if "jasna" in content_lower:
        await message.channel.send("toks ir draugelis...")
    
    # Respond to zalgiris mentions with a Rytas chant
    if "zalgiris" in content_lower or "žalgiris" in content_lower or "green white boys" in content_lower:
        chant = get_random_skanduote()
        response = f"Poxuj tie agurkiniai, va biški ryto skanduočių ant prasiblaivymo, matau apsvaiges šūdus pezi:\n\n**🏀 B TRIBŪNA STOJAMES ⛹️‍♂️**\n\n{chant['lyrics']}"
        if len(response) > 2000:
            response = response[:1997] + "..."
        await message.channel.send(response)
    
    # Process commands (so !ping etc still work)
    await bot.process_commands(message)


@bot.tree.command(name="kasian", description="Paklausk Boto ka sian")
async def kasian(interaction: discord.Interaction):
    """Slash command to trigger a random message."""
    message = get_random_message()
    await interaction.response.send_message(message)


@bot.tree.command(name="aoe", description="Sukviesti draugus į AoE")
async def aoe(interaction: discord.Interaction):
    """Slash command to call friends for AoE."""
    mentions = " ".join(f"<@{uid}>" for uid in GAME_USER_IDS)
    await interaction.response.send_message(f"alio, davai varom aoe {mentions}")


@bot.tree.command(name="cs", description="Sukviesti draugus į CS")
async def cs(interaction: discord.Interaction):
    """Slash command to call friends for CS."""
    message = random.choice(CS_MESSAGES)
    mentions = " ".join(f"<@{uid}>" for uid in GAME_USER_IDS)
    await interaction.response.send_message(f"{message} {mentions}")


@bot.tree.command(name="rytas", description="Gauti atsitiktinę Ryto skanduotę")
async def rytas(interaction: discord.Interaction):
    """Slash command to get a random Rytas chant without repeating until all are used."""
    chant = get_random_skanduote()
    # Discord has a 2000 char limit, so we might need to truncate
    message = f"**🏀 B TRIBŪNA STOJAMES ⛹️‍♂️**\n\n{chant['lyrics']}"
    if len(message) > 2000:
        message = message[:1997] + "..."
    
    await interaction.response.send_message(message)


@bot.tree.command(name="rytasnews", description="Gauti naujausias Vilniaus Ryto naujienas")
async def rytasnews(interaction: discord.Interaction):
    """Slash command to get latest Vilniaus Rytas news from basketnews.lt"""
    await interaction.response.defer()  # This might take a moment
    
    articles = await fetch_rytas_news()
    
    if articles:
        message = "**📰 Vilniaus Ryto naujienos (basketnews.lt):**\n\n"
        for i, article in enumerate(articles, 1):
            message += f"{i}. [{article['title']}]({article['url']})\n"
        
        if len(message) > 2000:
            message = message[:1997] + "..."
        
        await interaction.followup.send(message)


@bot.command(name="ping")
async def ping(ctx):
    """Test command to check if the bot is alive."""
    await ctx.send("Pongas! 🏓")


@bot.command(name="test")
async def test_message(ctx):
    """Manually trigger a random message (for testing)."""
    message = get_random_message()
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

