import json
import sqlite3
import pytz
import difflib
import discord
import datetime
import asyncio
from discord.ext import commands
from typing import Optional

# Load configuration from file
with open("config.json", "r") as config_file:
    config_data = json.load(config_file)

discord_token = config_data.get("discord_token")
replace_message = config_data.get("replace_message")

# Set up bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    
    # Sync application commands (slash commands)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send('Pong!')

# Slash command for registering a timezone
@bot.tree.command(name="registertimezone", description="Register your timezone")
async def registertimezone(interaction: discord.Interaction, timezone: Optional[str] = None, currenttime: Optional[str] = None):
    with sqlite3.connect('database.db') as db:
        cursor = db.cursor()
        cursor.execute('SELECT timezone FROM user_timezones WHERE discord_id = ?', (interaction.user.id,))
        result = cursor.fetchone()

    if timezone is None and currenttime is None:
        await interaction.response.send_message(
            "Please provide either a valid timezone or your current time in 24h format.",
            ephemeral=True
        )
        return

    # If timezone is provided
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

    # If current time is provided
    if currenttime:
        try:
            current_time = datetime.datetime.strptime(currenttime, '%H:%M')
        except ValueError:
            await interaction.response.send_message(
                f"Time '{currenttime}' is not valid. Please use the format HH:MM.",
                ephemeral=True
            )
            return

        now = datetime.datetime.now(datetime.UTC)
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
            await interaction.response.send_message(
                f"Multiple timezones match your time: {currenttime}. I chose {chosen_timezone}. "
                f"If incorrect, please type one from the list: {other_timezones_str}.",
                ephemeral=True
            )

            def check(message: discord.Message):
                return message.author == interaction.user and message.channel == interaction.channel and message.content in closest_timezones

            try:
                response_message = await bot.wait_for('message', check=check, timeout=30)
                timezone = response_message.content
            except asyncio.TimeoutError:
                await interaction.followup.send("Timed out. Please try again.", ephemeral=True)
                return
        else:
            timezone = closest_timezones[0]

    # Insert or update timezone
    with sqlite3.connect('database.db') as db:
        cursor = db.cursor()
        if result is None:
            cursor.execute('INSERT INTO user_timezones (discord_id, timezone) VALUES (?, ?)', (interaction.user.id, timezone))
            message = f"Timezone set to {timezone} for {interaction.user.name}!"
        else:
            cursor.execute('UPDATE user_timezones SET timezone = ? WHERE discord_id = ?', (timezone, interaction.user.id))
            message = f"Timezone updated to {timezone} for {interaction.user.name}!"

        db.commit()

    await interaction.response.send_message(message, ephemeral=True)

# Slash command for showing the timezone registered for a user
@bot.tree.command(name="whatismytimezone", description="Show your current registered timezone")
async def whatismytimezone(interaction: discord.Interaction):
    with sqlite3.connect('database.db') as db:
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

    with sqlite3.connect('database.db') as db:
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

# Slash command for showing the help message
@bot.tree.command(name="help", description="Show the help message")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message(
        """
Hiya, This bot was developed by @Cloud-121. I designed this bot to help discord servers with users in multiple timezones to know each others time and be able to say there time simply without having to pull up a unix clock. 
This bot is completely free and open source on my github [here](https://github.com/Cloud-121/Vipper-Timekeeping-discord-bot).
A few commands you can use are:

`/registertimezone [timezone or currenttime]` - Register your timezone

`/whatsthetime [user]` - Show your current time in your registered timezone

`/whatismytimezone` - Show your current registered timezone

`/help` - Show this help message (Look you found this one :3)
""",
        ephemeral=True
    )

# Run bot with token from config file
bot.run(discord_token)
