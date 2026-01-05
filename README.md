# Discord Daily Message Bot 🤖

A simple Discord bot that sends a random message from a predefined collection every day at 8 AM.

## Features

- 📅 Sends a random message daily at 8:00 AM (configurable timezone)
- 🎲 Randomly picks from a collection of messages
- 🧪 Test commands to verify functionality

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Copy the bot token (you'll need this later)
5. Enable "Message Content Intent" under Privileged Gateway Intents

### 2. Invite the Bot to Your Server

1. In the Developer Portal, go to "OAuth2" → "URL Generator"
2. Select scopes: `bot`
3. Select permissions: `Send Messages`, `Read Message History`
4. Copy the generated URL and open it to invite the bot

### 3. Get Channel ID

1. Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
2. Right-click the channel where you want messages sent
3. Click "Copy ID"

### 4. Configure Environment

```bash
# Copy the example environment file
cp env.example .env

# Edit .env with your values
# - DISCORD_TOKEN: Your bot token from step 1
# - CHANNEL_ID: The channel ID from step 3
# - TIMEZONE: Your timezone (default: Europe/Vilnius)
```

### 5. Install & Run

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `!ping` | Check if the bot is alive |
| `!test` | Manually trigger a random message |
| `!messages` | List all possible messages |

## Customizing Messages

Edit the `MESSAGES` list in `bot.py` to add or modify the daily messages:

```python
MESSAGES = [
    "ka sian?",
    "kada losiam?",
    "ka losiam siandien?",
    # Add more messages here...
]
```

## Running in Production

For 24/7 operation, consider:
- Using a process manager like `systemd` or `pm2`
- Deploying to a VPS or cloud service
- Using Docker for containerization

## License

MIT

# dcbot
# dcbot
# dcbot
# dcbot
# dcbot
# dcbot
