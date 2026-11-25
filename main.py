import asyncio
import os
import traceback
import discord
from discord.ext import commands
import sqlite3
import aiosqlite
from dotenv import load_dotenv

# from keep_alive import keep_alive
from initialize_database import initialize_database
from handle_database import (
    get_permitted_sync,
    add_permitted_sync,
    get_locale,
    get_invite,
    set_invite,
    delete_invite,
    add_money,
    add_xp,
    add_temp_xp,
    get_xp,
    get_temp_xp,
    set_temp_xp,
    get_alert_channel,
    get_xp_channel_multiplier,
    get_xp_category_multiplier,
    is_xp_blacklisted,
)
from cogs.xp_system import update_user_lvl_roles
import my_utils
from my_utils import update_translations

# import tracemalloc
# tracemalloc.start()

# ========== START =========== #

load_dotenv()

# Create all missing databases
conn = sqlite3.connect('mechbot.db')
initialize_database(conn)


# ========== STATIC VARIABLES =========== #


intents = discord.Intents.all()
DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
TEST_GUILDS = [901904937930346567]
OWNER_ID = 336475402535174154


# ========== BOT SETUP =========== #


print(discord.__version__)
bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

previous_invitations = dict()
invitations_lock = asyncio.Lock()

# Give default owner permission, if he doesn't have it already
cursor = conn.cursor()
if OWNER_ID not in get_permitted_sync(cursor):
    add_permitted_sync(cursor, OWNER_ID)
    conn.commit()
    print("\nADDED MALPKAKEFIREK AS THE OWNER\n")
cursor.close()
conn.close()


# ========== LOADING COGS =========== #


if __name__ == '__main__':
    print("loading plugins...")
    """
    Loads the cogs from the `./cogs` folder.
    Note:
        The cogs are named in this format `{cog_dir}.{cog_filename_without_extension}`.
    """
    for cog in os.listdir('cogs'):
        if cog.endswith('.py') is True:
            print(f"loading cogs.{cog[:-3]}...")
            bot.load_extension(f'cogs.{cog[:-3]}')
        elif os.path.isdir(f'cogs/{cog}'):
            for file in os.listdir(f'cogs/{cog}'):
                if file.endswith('.py') is True:
                    print(f"loading cogs.{cog}.{file[:-3]}...")
                    bot.load_extension(f'cogs.{cog}.{file[:-3]}')
    print("plugins loaded :D")


# ========== ON READY =========== #


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}\n\n====== INVITES ======")

    # print all invites from all guilds
    for guild in bot.guilds:
        try:
            invites = list(await guild.invites())
        except discord.Forbidden:
            print(f"Couldn't fetch invites for guild \"{guild.name}\" (missing permissions)")
            async with invitations_lock:
                previous_invitations.pop(str(guild.id), None)
            continue

        # Keep the snapshot consistent with what join handlers can read.
        async with invitations_lock:
            previous_invitations[str(guild.id)] = list(invites)

        print(f"{guild.name}:")
        for inv in invites:
            print(f"{inv.code} – {inv.uses}")
        print()

    custom_activity = discord.Activity(type=2, name="/help")
    await bot.change_presence(activity=custom_activity)


# ========== ERROR HANDLING =========== #


@bot.event
async def on_application_command_error(ctx, error):
    """Single handler for slash-command errors (cogs must not duplicate it)."""
    if getattr(error, '_bot_error_handled', False):
        return
    error._bot_error_handled = True

    author = getattr(ctx, 'author', None)
    locale = 'pl'
    if author is not None:
        try:
            async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
                async with conn.cursor() as cursor:
                    locale = await get_locale(cursor, author.id)
        except Exception:
            pass

    errors = getattr(my_utils, 'TRANSLATIONS', {}).get('errors', {})
    if isinstance(error, commands.MissingPermissions):
        template = errors.get('missing_permissions', {})
        if isinstance(template, dict):
            template = template.get(locale, template.get('en', template.get('pl')))
        missing = getattr(error, 'missing_permissions', ())
        permission = str(missing[0]).replace('_', ' ').upper() if missing else 'required'
        try:
            response = template % permission
        except (TypeError, AttributeError):
            response = template or f"You need {permission} permission to use this command."
    elif isinstance(error, commands.CommandOnCooldown):
        response = "This command is on cooldown. Please try again later."
    elif isinstance(error, (commands.CheckFailure, discord.Forbidden)):
        response = "You do not have permission to use this command."
    elif isinstance(error, discord.HTTPException):
        response = "Discord refused the request. Please try again later."
    else:
        response = "An unexpected error occurred. Please try again later."

    formatted = ''.join(traceback.format_exception(
        type(error), error, getattr(error, '__traceback__', None)
    ))
    print(formatted)
    try:
        with open('errors.txt', 'a', encoding='utf-8') as f:
            f.write(formatted)
            f.write("<<<================================>>>\n")
    except OSError as file_error:
        print(f"Could not write errors.txt: {file_error}")

    if not isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
        try:
            owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
            await owner.send(formatted[:1900])
        except Exception:
            pass

    try:
        await ctx.respond(response, ephemeral=True)
    except Exception:
        pass


# ========== FUNCTIONS =========== #


# fetch invite by invite's code
def find_invite_by_code(invite_list, code):
    for invite in invite_list:
        if invite.code == code:
            return invite
    else:
        return None


async def send_alert(guild, channel_id, message):
    """Send an alert only when a usable alert channel is configured."""
    if channel_id is None:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    await channel.send(message)


# ========== ON JOIN =========== #

@bot.event
async def on_member_join(member):
    guild = member.guild
    guild_key = str(guild.id)

    # Take a consistent snapshot and refresh it before any other join can diff
    # against the same baseline. The fetch stays inside the lock so concurrent
    # joins cannot both credit the same invite increment.
    async with invitations_lock:
        invites_before_join = (
            list(previous_invitations[guild_key]) if guild_key in previous_invitations else None
        )
        try:
            invites_after_join = list(await guild.invites())
        except discord.Forbidden:
            invites_after_join = None

        if invites_after_join is None:
            previous_invitations.pop(guild_key, None)
        else:
            previous_invitations[guild_key] = list(invites_after_join)

        inv = find_used_invite(invites_before_join, invites_after_join)

    # (disabled)
    # /-----------------------\
    # create dm channel with person who joined, if not already created
    # if not member.dm_channel:
    #   await member.create_dm()
    #   print(f"Created a DM channel with \"{member.name}\"")

    # send welcoming message if dm is possible
    # try:
    #   await member.dm_channel.send(f"Witamy!")
    # except discord.Forbidden:
    #   print(discord.Forbidden)
    # \-----------------------/

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            alert_channel_id = await get_alert_channel(cursor)

    if member == bot.user:
        print(f"I joined the server {guild.name}!")
        return

    # if user is a bot
    if member.bot:
        print(f"Invited user `{member.name}` is a bot")
        await send_alert(
            guild, alert_channel_id,
            f"Pominięto przypisanie mech coinów za zaproszenie użytkownika {member.mention}, ponieważ to jest bot."
        )
        return

    # Without a baseline there is nothing to compare against; don't guess an inviter.
    if invites_before_join is None:
        print(
            f"Couldn't add money for inviting `{member.name}`, "
            f"because there is no invite baseline for guild \"{guild.name}\""
        )
        return

    if inv is None:
        print(f"Couldn't add money for inviting `{member.name}`, because invite was single use")
        await send_alert(
            guild, alert_channel_id,
            f"Nie można było przypisać mech coinów za zaproszenie użytkownika {member.mention}, ponieważ zaproszenie było jednorazowe!"
        )
        return

    if inv.inviter is None:
        print(f"Couldn't add money for inviting `{member.name}`, because invite `{inv.code}` has no inviter")
        await send_alert(
            guild, alert_channel_id,
            f"Nie można było przypisać mech coinów za zaproszenie użytkownika {member.mention}, ponieważ zaproszenie `{inv.code}` nie ma zapraszającego!"
        )
        return

    # if member invited himself, don't give money (and don't store the invite)
    if member.id == inv.inviter.id:
        return

    # Only store an invite when money is actually credited.
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN IMMEDIATE") as cursor:
            new_balance = await add_money(cursor, inv.inviter.id, 50)
            await set_invite(cursor, member.id, inv.code, inv.inviter.name, inv.inviter.id)
        await conn.commit()

    # send all alerts
    print(f"Added 50 money to user {inv.inviter.name} for inviting {member.name} (now at {new_balance})")
    await send_alert(
        guild, alert_channel_id,
        f"Użytkownik `{inv.inviter.name}` otrzymał 50 mech coinów za zaproszenie {member.mention} (teraz {new_balance}) [`{inv.code}`]"
    )


def find_used_invite(invites_before_join, invites_after_join):
    if invites_before_join is None or invites_after_join is None:
        return None

    before_by_code = {inv.code: inv for inv in invites_before_join}
    for inv in invites_after_join:
        before = before_by_code.get(inv.code)
        if before is not None:
            if inv.uses <= before.uses:
                continue
            print("old invite used")
            return inv
        if inv.uses <= 0:
            continue
        print("new invite used")
        return inv

    # if no invite was found
    return None

# ========== ON LEAVE =========== #


@bot.event
async def on_member_remove(member):
    if member == bot.user:
        print(f"I left the server {member.guild.name}!")
        return

    invite = None
    alert_channel_id = None
    new_balance = None

    # Read, debit and delete together so a concurrent leave can't double-credit.
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN IMMEDIATE") as cursor:
            invite = await get_invite(cursor, member.id)
            alert_channel_id = await get_alert_channel(cursor)

            # remove money from inviter if invitee leaves
            if not member.bot and invite:
                inviter_id = invite[2]
                new_balance = await add_money(cursor, inviter_id, -50)
                await delete_invite(cursor, member.id)
        await conn.commit()

    if member.bot:
        print(f"{member.name} left the server, but was a bot")
        await send_alert(
            member.guild, alert_channel_id,
            f"Nie usunięto mech coinów, ponieważ użytkownik `{member.name}` jest botem."
        )
        return

    if invite:
        inviter_id = invite[2]
        inviter = bot.get_user(inviter_id) or await bot.fetch_user(inviter_id)
        inviter_name = inviter.name if inviter else inviter_id

        print(f"REMOVED 50 MONEY FROM {inviter_name} (now {new_balance})")
        await send_alert(
            member.guild, alert_channel_id,
            f"Usunięto 50 mech coinów użytkownikowi `{inviter_name}` (teraz {new_balance}), ponieważ użytkownik `{member.name}` wyszedł z serwera :pensive:"
        )
        return

    # no invite in db
    print(f"{member.name} left the server")
    await send_alert(
        member.guild, alert_channel_id,
        f"Nie usunięto mech coinów, ponieważ brak zaproszenia dla użytkownika `{member.name}`!"
    )


@bot.event
async def on_presence_update(before, after):
    if after.id == 789090415932080138 and after.status == discord.Status.offline and before.status != discord.Status.offline:
        await bot.get_user(336475402535174154).send("Małpka bot is offline!")


# ========== ON MESSAGE =========== #

@bot.event
async def on_message(message):

    # do nothing if it's a bot
    if message.author == bot.user or message.author.bot is True:
        return

    if not message.guild:
        await bot.process_commands(message)
        return

    if message.channel.type != discord.ChannelType.text:
        return

    user_id = message.author.id
    old_xp = 0.0
    new_xp = 0.0
    xp_added = 0.0
    xp_blacklisted = False

    # == XP == #
    # No Discord API calls happen inside this short write transaction.
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN IMMEDIATE") as cursor:
            xp_blacklisted = await is_xp_blacklisted(cursor, message.channel.id)
            if not xp_blacklisted:
                # channel's xp setting, category's xp setting, then global xp setting
                channel_xp = await get_xp_channel_multiplier(cursor, message.channel.id)
                category_xp = None
                if message.channel.category_id:
                    category_xp = await get_xp_category_multiplier(cursor, message.channel.category_id)
                if channel_xp is not None:
                    xp_added = channel_xp
                elif category_xp is not None:
                    xp_added = category_xp
                else:
                    xp_added = 1.0

                old_xp = await get_xp(cursor, user_id)
                temp_xp = await get_temp_xp(cursor, user_id)

                # new member
                if old_xp == 0:
                    print(f"First message for user {message.author.name} ({user_id}) [xp]")

                # ensure a money row exists (replaces the get_balance/set_money pair)
                await add_money(cursor, user_id, 0)

                # if a member wrote a msg in a whitelisted channel, add {xp_added} xp to that member
                if xp_added > 0:
                    xp_delta = round(old_xp + xp_added, 1) - old_xp
                    temp_delta = round(temp_xp + xp_added, 1) - temp_xp
                else:
                    xp_delta = 0.0
                    temp_delta = 0.0

                new_xp = await add_xp(cursor, user_id, xp_delta)
                new_temp_xp = await add_temp_xp(cursor, user_id, temp_delta)

                # add money for each 5 xp
                if new_temp_xp >= 5:
                    await add_money(cursor, user_id, int(new_temp_xp / 5))  # division without the remainder
                    await set_temp_xp(cursor, user_id, float(new_temp_xp % 5))  # leave the remainder in temp_xp
        await conn.commit()

    if not xp_blacklisted:
        if xp_added > 0:
            print(f"Added {xp_added} xp to \"{message.author.name}\" in guild \"{message.guild.name}\" (now {new_xp})")

        # Role updates are done outside any DB transaction/connection.
        await update_user_lvl_roles(message, bot, message.author, old_xp, float(new_xp))

    await bot.process_commands(message)


# ========== TEXT COMMANDS =========== #

@bot.command(
    name="reload",
    brief="Used to reload the bot (bot owner only)",
    description="Used to reload the bot (bot owner only)",
    hidden=True,
)
@commands.is_owner()
async def reload_cogs(ctx):
    print("reloading...")
    update_translations()
    for cog in os.listdir('./cogs'):
        if cog.endswith('.py') is True:
            bot.reload_extension(f'cogs.{cog[:-3]}')
        elif os.path.isdir(f'./cogs/{cog}'):
            for file in os.listdir(f'./cogs/{cog}'):
                if file.endswith('.py') is True:
                    bot.reload_extension(f'cogs.{cog}.{file[:-3]}')
    print("plugins reloaded :D")
    await ctx.send("Successfully reloaded all plugins!")


@bot.command(
    name="load",
    brief="Used to manually load plugins (bot owner only)",
    description="Used to manually load plugins (bot owner only)",
    hidden=True,
)
@commands.is_owner()
async def load_cogs(ctx):
    print("loading...")
    for cog in os.listdir('./cogs'):
        if cog.endswith('.py') is True:
            print(f"loading cogs.{cog[:-3]}...")
            bot.load_extension(f'cogs.{cog[:-3]}')
        elif os.path.isdir(f'./cogs/{cog}'):
            for file in os.listdir(f'./cogs/{cog}'):
                if file.endswith('.py') is True:
                    print(f"loading cogs.{cog}.{file[:-3]}...")
                    bot.load_extension(f'cogs.{cog}.{file[:-3]}')
    print("plugins loaded :D")
    await ctx.send("Successfully loaded all plugins!")


@bot.command(
    name="unload",
    brief="Used to manually unload plugins (bot owner only)",
    description="Used to manually unload plugins (bot owner only)",
    hidden=True,
)
@commands.is_owner()
async def unload_cogs(ctx):
    print("unloading...")
    for cog in os.listdir('./cogs'):
        if cog.endswith('.py') is True:
            try:
                print(f"unloading cogs.{cog[:-3]}...")
                bot.unload_extension(f'cogs.{cog[:-3]}')
            except Exception as e:
                print(e)
        elif os.path.isdir(f'./cogs/{cog}'):
            for file in os.listdir(f'./cogs/{cog}'):
                if file.endswith('.py') is True:
                    try:
                        print(f"unloading cogs.{cog}.{file[:-3]}...")
                        bot.unload_extension(f'cogs.{cog}.{file[:-3]}')
                    except Exception as e:
                        print(e)
    print("plugins unloaded :D")
    await ctx.send("Successfully unloaded all plugins!")

# =========SETUP========== #

# keep_alive()
bot.run(DISCORD_TOKEN)
