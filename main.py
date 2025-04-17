import os
import discord
from discord.ext import commands
import sqlite3
import aiosqlite
from dotenv import load_dotenv

# from keep_alive import keep_alive
from initialize_database import initialize_database
from handle_database import select_value, update_value, select_value_sync, update_value_sync
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
owner_ids = select_value_sync(cursor, 'permitted')


if OWNER_ID not in owner_ids:
    owner_ids.append(OWNER_ID)
    update_value_sync(cursor, 'permitted', owner_ids)
    conn.commit()
    print("\nADDED MALPKAKEFIREK AS THE OWNER\n")
cursor.close()


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
            value = await select_value(cursor, 'invites')

            # if the guild never had any invites
            if str(member.guild.id) not in value:
                value[str(member.guild.id)] = dict()
                print("assigned guild to invites dict")
                await update_value(cursor, 'invites', value)

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

            # fetch my profile (disabled)
            # malpka = await member.guild.fetch_member(336475402535174154)
            money = await select_value(cursor, 'money')
            alert_channel_id = int(await select_value(cursor, 'alert_channel'))

            # if user is a bot
            if member.bot:
                await conn.commit()
                print(f"Invited user `{member.name}` is a bot")
                await member.guild.get_channel(alert_channel_id).send(
                    f"Pominięto przypisanie mech coinów za zaproszenie użytkownika {member.mention}, ponieważ to jest bot."
                )
                return

            # find the used invite
            inv = find_used_invite(cursor, invites_before_join, invites_after_join)

            if inv is None:
                await conn.commit()
                print(f"Couldn't add money for inviting `{member.name}`, because invite was single use")
                await member.guild.get_channel(alert_channel_id).send(
                    f"Nie można było przypisać mech coinów za zaproszenie użytkownika {member.mention}, ponieważ zaproszenie było jednorazowe!"
                )
                return

            # attach an invite to member id
            invites = await select_value(cursor, 'invites')
            invites[str(member.id)] = [inv.code, inv.inviter.name, inv.inviter.id]
            await update_value(cursor, 'invites', invites)

            # update invites' num of uses
            previous_invitations[str(member.guild.id)] = invites_after_join

            # if member invited himself, don't give money
            if member.id == inv.inviter.id:
                return

            # add money
            money[str(inv.inviter.id)] = money.get(str(inv.inviter.id), 0) + 50
            await update_value(cursor, 'money', money)
            await conn.commit()

            # send all alerts
            print(f"Added 50 money to user {inv.inviter.name} for inviting {member.name} (now at {money[str(inv.inviter.id)]})")
            await member.guild.get_channel(alert_channel_id).send(
                f"Użytkownik `{inv.inviter.name}` otrzymał 50 mech coinów za zaproszenie {member.mention} (teraz {money[str(inv.inviter.id)]}) [`{inv.code}`]"
            )
            return


def find_used_invite(cursor, invites_before_join, invites_after_join):
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
            invites = await select_value(cursor, 'invites')
            alert_channel_id = int(await select_value(cursor, 'alert_channel'))

        if member.bot:
            print(f"{member.name} left the server, but was a bot")
            await member.guild.get_channel(alert_channel_id).send(
                f"Nie usunięto mech coinów, ponieważ użytkownik `{member.name}` jest botem."
            )
            return

        # remove money from inviter if invitee leaves
        if str(member.id) in invites:
            inviter_id = invites[str(member.id)][2]
            async with conn.execute("BEGIN TRANSACTION") as cursor:
                money = await select_value(cursor, 'money')
                money[str(inviter_id)] -= 50
                await update_value(cursor, 'money', money)
                await conn.commit()

            inviter = bot.get_user(inviter_id) or await bot.fetch_user(inviter_id)
            inviter_name = inviter.name if inviter else inviter_id

            print(f"REMOVED 50 MONEY FROM {inviter_name} (now {money[str(inviter_id)]})")
            await member.guild.get_channel(alert_channel_id).send(
                f"Usunięto 50 mech coinów użytkownikowi `{inviter_name}` (teraz {money[str(inviter_id)]}), ponieważ użytkownik `{member.name}` wyszedł z serwera :pensive:"
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

    str_user_id = str(message.author.id)
    str_channel_id = str(message.channel.id)
    str_category_id = str(message.channel.category_id)

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.execute("BEGIN TRANSACTION") as cursor:
            xp = await select_value(cursor, 'xp')
            temp_xp = await select_value(cursor, 'temp_xp')
            money = await select_value(cursor, 'money')
            xp_channel_settings = await select_value(cursor, 'xp_channel_settings')
            xp_category_settings = await select_value(cursor, 'xp_category_settings')

            # == XP == #
            if message.channel.type != discord.ChannelType.text:
                return

            # channel's xp setting
            if str_channel_id in xp_channel_settings:
                str_xp_added = str(xp_channel_settings[str_channel_id])
            # category's xp setting
            elif str_category_id in xp_category_settings:
                str_xp_added = str(xp_category_settings[str_category_id])
            # global xp setting
            else:
                str_xp_added = str(1)

            # new member
            if str_user_id not in xp:
                xp[str_user_id] = str(0)
                print(f"First message for user {message.author.name} ({str_user_id}) [xp]")

            if str_user_id not in temp_xp:
                temp_xp[str_user_id] = str(0)

            if str_user_id not in money:
                money[str_user_id] = 0

            old_xp = float(xp[str_user_id])

            # if a member wrote a msg in a whitelisted channel, add {str_xp_added} xp to that member
            if float(str_xp_added) > 0:
                xp[str_user_id] = str(round(float(xp[str_user_id]) + float(str_xp_added), 1))
                temp_xp[str_user_id] = str(round(float(temp_xp[str_user_id]) + float(str_xp_added), 1))

            # add money for each 5 xp
            if float(temp_xp[str_user_id]) >= 5:
                money[str_user_id] += int(float(temp_xp[str_user_id]) / 5)    # division without the remainder
                temp_xp[str_user_id] = str(float(temp_xp[str_user_id]) % 5)    # leave the remainder from division in temp_xp

            await update_value(cursor, 'temp_xp', temp_xp)
            await update_value(cursor, 'money', money)
            await update_value(cursor, 'xp', xp)
            await conn.commit()

        if float(str_xp_added) > 0:
            print(f"Added {str_xp_added} xp to \"{message.author.name}\" in guild \"{message.guild.name}\" (now {xp[str_user_id]})")

        async with conn.execute("BEGIN TRANSACTION") as cursor:
            await update_user_lvl_roles(message, bot, message.author, old_xp, float(xp[str_user_id]), cursor)
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
