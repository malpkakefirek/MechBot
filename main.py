import os
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
    get_invite,
    set_invite,
    get_balance,
    set_money,
    add_money,
    get_xp,
    set_xp,
    get_temp_xp,
    set_temp_xp,
    get_alert_channel,
    get_xp_channel_multiplier,
    get_xp_category_multiplier,
)
from cogs.xp_system import update_user_lvl_roles
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
        previous_invitations[str(guild.id)] = await guild.invites()
        print(f"{guild.name}:")
        for inv in previous_invitations[str(guild.id)]:
            print(f"{inv.code} – {inv.uses}")
        print()

    custom_activity = discord.Activity(type=2, name="/help")
    await bot.change_presence(activity=custom_activity)


# ========== FUNCTIONS =========== #


# fetch invite by invite's code
def find_invite_by_code(invite_list, code):
    for invite in invite_list:
        if invite.code == code:
            return invite
    else:
        return None


# ========== ON JOIN =========== #

@bot.event
async def on_member_join(member):
    if member == bot.user:
        print(f"I joined the server {member.guild.name}!")
        return

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN TRANSACTION") as cursor:
            # get invites' uses before join
            invites_before_join = previous_invitations.get(str(member.guild.id), [])

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

            # fetch invites after join
            invites_after_join = await member.guild.invites()

            alert_channel_id = await get_alert_channel(cursor)

            # if user is a bot
            if member.bot:
                await conn.commit()
                print(f"Invited user `{member.name}` is a bot")
                await member.guild.get_channel(alert_channel_id).send(
                    f"Pominięto przypisanie mech coinów za zaproszenie użytkownika {member.mention}, ponieważ to jest bot."
                )
                return

            # find the used invite
            inv = find_used_invite(invites_before_join, invites_after_join)

            if inv is None:
                await conn.commit()
                print(f"Couldn't add money for inviting `{member.name}`, because invite was single use")
                await member.guild.get_channel(alert_channel_id).send(
                    f"Nie można było przypisać mech coinów za zaproszenie użytkownika {member.mention}, ponieważ zaproszenie było jednorazowe!"
                )
                return

            # attach an invite to member id
            await set_invite(cursor, member.id, inv.code, inv.inviter.name, inv.inviter.id)

            # update invites' num of uses
            previous_invitations[str(member.guild.id)] = invites_after_join

            # if member invited himself, don't give money
            if member.id == inv.inviter.id:
                await conn.commit()
                return

            # add money
            new_balance = await add_money(cursor, inv.inviter.id, 50)
            await conn.commit()

            # send all alerts
            print(f"Added 50 money to user {inv.inviter.name} for inviting {member.name} (now at {new_balance})")
            await member.guild.get_channel(alert_channel_id).send(
                f"Użytkownik `{inv.inviter.name}` otrzymał 50 mech coinów za zaproszenie {member.mention} (teraz {new_balance}) [`{inv.code}`]"
            )
            return


def find_used_invite(invites_before_join, invites_after_join):
    for inv in invites_after_join:
        if inv in invites_before_join:
            if inv.uses <= find_invite_by_code(invites_before_join, inv.code).uses:
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

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            invite = await get_invite(cursor, member.id)
            alert_channel_id = await get_alert_channel(cursor)

        if member.bot:
            print(f"{member.name} left the server, but was a bot")
            await member.guild.get_channel(alert_channel_id).send(
                f"Nie usunięto mech coinów, ponieważ użytkownik `{member.name}` jest botem."
            )
            return

        # remove money from inviter if invitee leaves
        if invite:
            inviter_id = invite[2]
            async with conn.execute("BEGIN TRANSACTION") as cursor:
                new_balance = await add_money(cursor, inviter_id, -50)
                await conn.commit()

            inviter = bot.get_user(inviter_id) or await bot.fetch_user(inviter_id)
            inviter_name = inviter.name if inviter else inviter_id

            print(f"REMOVED 50 MONEY FROM {inviter_name} (now {new_balance})")
            await member.guild.get_channel(alert_channel_id).send(
                f"Usunięto 50 mech coinów użytkownikowi `{inviter_name}` (teraz {new_balance}), ponieważ użytkownik `{member.name}` wyszedł z serwera :pensive:"
            )
            return

    # no invite in db
    print(f"{member.name} left the server")
    await member.guild.get_channel(alert_channel_id).send(
        f"Nie usunięto mech coinów, ponieważ brak zaproszenia dla użytkownika `{member.name}`!"
    )
    return


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

    user_id = message.author.id

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN TRANSACTION") as cursor:
            # == XP == #
            if message.channel.type != discord.ChannelType.text:
                return

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

            if await get_balance(cursor, user_id) == 0:
                await set_money(cursor, user_id, 0)

            # if a member wrote a msg in a whitelisted channel, add {xp_added} xp to that member
            new_xp = round(old_xp + xp_added, 1) if xp_added > 0 else old_xp
            if xp_added > 0:
                temp_xp = round(temp_xp + xp_added, 1)

            # add money for each 5 xp
            if temp_xp >= 5:
                await add_money(cursor, user_id, int(temp_xp / 5))   # division without the remainder
                temp_xp = float(temp_xp % 5)                         # leave the remainder in temp_xp

            await set_temp_xp(cursor, user_id, temp_xp)
            await set_xp(cursor, user_id, new_xp)
            await conn.commit()

        if xp_added > 0:
            print(f"Added {xp_added} xp to \"{message.author.name}\" in guild \"{message.guild.name}\" (now {new_xp})")

        async with conn.execute("BEGIN TRANSACTION") as cursor:
            await update_user_lvl_roles(message, bot, message.author, old_xp, float(new_xp), cursor)
            await conn.commit()
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
