botversion = "1.6"

print(f"Starting Vipper Timekeeping Discord Bot Version {botversion}")

import json
import sqlite3
import pytz
import difflib
import discord
import re
import datetime
import asyncio
from discord.ext import commands
from typing import Optional
from dotenv import load_dotenv
import os

# Load configuration from file
# Check for a config.json if not load env
try:
    print("Attempting to load config.json")
    with open("config.json", "r") as config_file:
        config_data = json.load(config_file)

    discord_token = config_data.get("discord_token")
except FileNotFoundError:
    print("config.json not found. Attempting to load DISCORD_TOKEN from environment variable.")
    discord_token = os.getenv('DISCORD_TOKEN')

if discord_token is None:
    print("DISCORD_TOKEN not found in environment variable and config.json.")
    exit(1)
else:
    print("DISCORD_TOKEN loaded.")

#Check for database
if not os.path.exists("data/database.db"):
    print("Database not found. Attempting to create database.")
    open("data/database.db", "w").close()
    # Create the database and table if it doesn't exist
    conn = sqlite3.connect("data/database.db")
    cursor = conn.cursor()
    
    # Create the user_timezones table
    cursor.execute('''
        CREATE TABLE user_timezones (
            discord_id INTEGER PRIMARY KEY,
            timezone TEXT NOT NULL
        )
    ''')
    
    # Commit changes and close the connection
    conn.commit()
    conn.close()
    print("Database and table created.")
else:
    print("Database was found.")

# Set up bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Events
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    
    # Sync application commands (slash commands)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return  # Ignore bot messages

    with sqlite3.connect('data/database.db') as db:
        cursor = db.cursor()
        cursor.execute('SELECT timezone FROM user_timezones WHERE discord_id = ?', (message.author.id,))
        result = cursor.fetchone()

    if result:
        timezone = result[0]
        tz = pytz.timezone(timezone)
        
        # Time detection regex (Supports HH:MM, HH:MM AM/PM)
        time_patterns = [
            r'\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b',  # 24-hour format (HH:MM)
            r'\b(1[0-2]|0?[1-9]):([0-5][0-9]) ?(AM|PM|am|pm)\b'  # 12-hour format (HH:MM AM/PM)
        ]

        for pattern in time_patterns:
            match = re.search(pattern, message.content)
            if match:
                time_str = match.group(0)

                # Convert to datetime object
                try:
                    if 'AM' in time_str.upper() or 'PM' in time_str.upper():
                        time_obj = datetime.datetime.strptime(time_str, '%I:%M %p')
                    else:
                        time_obj = datetime.datetime.strptime(time_str, '%H:%M')
                    
                    now = datetime.datetime.now(tz)
                    time_with_date = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)

                    # Convert to Unix timestamp
                    unix_timestamp = int(time_with_date.timestamp())

                    # Send Discord timestamp format
                    await message.channel.send(f"<t:{unix_timestamp}:t>")
                except ValueError:
                    pass  # Ignore invalid formats

    await bot.process_commands(message)

#   Commands

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send('Pong!')

# Slash command for registering a timezone@bot.tree.command(name="registertimezone", description="Register your timezone")
@bot.tree.command(name="registertimezone", description="Register your timezone")
async def registertimezone(interaction: discord.Interaction, timezone: Optional[str] = None, currenttime: Optional[str] = None):
    # Check if user already has a timezone in the database
    with sqlite3.connect('data/database.db') as db:
        cursor = db.cursor()
        cursor.execute('SELECT timezone FROM user_timezones WHERE discord_id = ?', (interaction.user.id,))
        result = cursor.fetchone()

    if timezone is None and currenttime is None:
        await interaction.response.send_message(
            "Please provide either a valid timezone or your current time in 24h format.",
            ephemeral=True
        )
        return

    # Handle timezone provided directly
    if timezone:
        if timezone not in pytz.all_timezones:
            closest_match = difflib.get_close_matches(timezone, pytz.all_timezones, n=1, cutoff=0)
            if closest_match:
                timezone = closest_match[0]
            else:
                await interaction.response.send_message(
                    f"'{timezone}' is not a valid timezone.",
                    ephemeral=True
                )
                return

    # Handle current time provided for timezone determination
    if currenttime:
        try:
            current_time = datetime.datetime.strptime(currenttime, '%H:%M')
        except ValueError:
            await interaction.response.send_message(
                f"Time '{currenttime}' is not valid. Please use the format HH:MM.",
                ephemeral=True
            )
            return

        now = datetime.datetime.now(pytz.UTC)
        closest_timezones = [
            zone for zone in pytz.all_timezones
            if now.astimezone(pytz.timezone(zone)).strftime('%H:%M') == currenttime
        ]

        if not closest_timezones:
            await interaction.response.send_message(
                "No matching timezones found for the given time.",
                ephemeral=True
            )
            return

        if len(closest_timezones) > 1:
            chosen_timezone = closest_timezones[0]
            other_timezones_str = ', '.join(closest_timezones[1:])
            other_timezones_str = f"```{other_timezones_str}```"
            await interaction.response.send_message(
                f"Multiple timezones match your time: {currenttime}. I chose {chosen_timezone}. "
                f"If incorrect, please manually select one from the list using the `/registertimezone [timezone]` command: \n {other_timezones_str}.",
                ephemeral=True
            )
            timezone = closest_timezones[0]
        else:
            timezone = closest_timezones[0]

    # Now insert or update the timezone in the database
    with sqlite3.connect('data/database.db') as db:
        cursor = db.cursor()

        if result is None:
            # User doesn't have a timezone yet, insert it
            cursor.execute('INSERT INTO user_timezones (discord_id, timezone) VALUES (?, ?)', (interaction.user.id, timezone))
            message = f"Timezone set to {timezone} for {interaction.user.name}!"
        else:
            # User has a timezone, update it
            cursor.execute('UPDATE user_timezones SET timezone = ? WHERE discord_id = ?', (timezone, interaction.user.id))
            message = f"Timezone updated to {timezone} for {interaction.user.name}!"

        db.commit()

    # Use follow-up message after the initial response to avoid "InteractionResponded" error
    await interaction.followup.send(message, ephemeral=True)



# Slash command for showing the timezone registered for a user
@bot.tree.command(name="whatismytimezone", description="Show your current registered timezone")
async def whatismytimezone(interaction: discord.Interaction):
    with sqlite3.connect('data/database.db') as db:
        cursor = db.cursor()
        cursor.execute('SELECT timezone FROM user_timezones WHERE discord_id = ?', (interaction.user.id,))
        result = cursor.fetchone()

    if result:
        await interaction.response.send_message(f"Your current registered timezone is {result[0]}.", ephemeral=True)
    else:
        await interaction.response.send_message("You don't have a registered timezone.", ephemeral=True)

# Slash command for showing the current time in a user's registered timezone
@bot.tree.command(name="whatsthetime", description="Show your current time in your registered timezone")
async def whatsthetime(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    if user is None:
        user = interaction.user

    with sqlite3.connect('data/database.db') as db:
        cursor = db.cursor()
        cursor.execute('SELECT timezone FROM user_timezones WHERE discord_id = ?', (user.id,))
        result = cursor.fetchone()

    if result:
        try:
            timezone = pytz.timezone(result[0])
            now = datetime.datetime.now(datetime.UTC).astimezone(timezone)
            await interaction.response.send_message(f"{user.name}'s current time is {now.strftime('%H:%M')}.")
        except pytz.UnknownTimeZoneError:
            await interaction.response.send_message("The user's timezone is invalid in the database.", ephemeral=True)
    else:
        await interaction.response.send_message("The user does not have a registered timezone.", ephemeral=True)

#Version command
@bot.tree.command(name="version", description="Show the bot's version")
async def version(interaction: discord.Interaction):
    await interaction.response.send_message(f"Vipper Timekeeping Discord Bot v{botversion}", ephemeral=True)

# Slash command for showing the help message
@bot.tree.command(name="help", description="Show the help message")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message(
        """
Hiya, This bot was developed by [@Cloud-121](https://github.com/Cloud-121). I designed this bot to help discord servers with users in multiple timezones to know each others time and be able to say there time simply without having to pull up a unix clock. 

This bot is completely free and open source on my github [here](https://github.com/Cloud-121/Vipper-Timekeeping-discord-bot).

A few commands you can use are:

`/registertimezone [timezone or currenttime]` - Register your timezone

`/whatsthetime [user]` - Show your current time in your registered timezone

`/whatismytimezone` - Show your current registered timezone

`/version` - Show the bot's version that's currently running

`/help` - Show this help message (Look you found this one :3)
""",
        ephemeral=True
    )

# Run bot with token from config file
bot.run(discord_token)
