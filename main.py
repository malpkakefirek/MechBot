import os
from replit import db
import discord
from discord.ext import commands

from keep_alive import keep_alive
from initialize_database import initialize_database
from cogs.xp_system import update_user_lvl_roles

# import tracemalloc
# tracemalloc.start()

# ========== START =========== #


# Create all missing databases
initialize_database()


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
owner_ids = db['permitted']


if OWNER_ID not in owner_ids:
    owner_ids.append(OWNER_ID)
    db['permitted'] = owner_ids
    print("\nADDED MALPKAKEFIREK AS THE OWNER\n")


# ========== LOADING COGS =========== #


if __name__=='__main__':
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

    matches = db.prefix("")
    print(f"====== DATABASE ======\n{matches}")

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
    value = db['invites']

    # if the guild never had any invites
    if str(member.guild.id) not in value:
        value[str(member.guild.id)] = dict()
        print("assigned guild to invites dict")

    db['invites'] = value

    # get invites' uses before join
    invites_before_join = previous_invitations[str(member.guild.id)]

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
    money = db['money']
    alert_channel_id = db['alert_channel']

    # if user is a bot
    if member.bot:
        print(f"Invited user `{member.name}` is a bot")
        await member.guild.get_channel(alert_channel_id).send(
            f"Pominięto przypisanie mech coinów za zaproszenie użytkownika {member.mention}, ponieważ to jest bot."
        )
        return
    
    # find the used invite
    for inv_old in invites_before_join:
        inv = find_invite_by_code(invites_after_join, inv_old.code)

        if not inv or inv.uses <= inv_old.uses:
            continue

        print(f"old invite used for {member.name}")

        # attach an invite to member id
        value = db['invites']
        value[str(member.id)] = [inv.code, inv.inviter.name, inv.inviter.id]
        db['invites'] = value

        # update invites' num of uses
        previous_invitations[str(member.guild.id)] = invites_after_join

        # if member invited himself, don't give money
        if member.id == inv.inviter.id:
            return

        # add money
        if str(inv.inviter.id) in money:
            money[str(inv.inviter.id)] += 50
        else:
            money[str(inv.inviter.id)] = 50

        # send all alerts
        print(f"Added 50 money to user {inv.inviter.name} for inviting {member.name} (now at {money[str(inv.inviter.id)]})")
        # (disabled)
        # await malpka.create_dm()
        # await malpka.dm_channel.send(f"`{inv.inviter.name}` earned 50 money for inviting `{member.name}`")  
        await member.guild.get_channel(alert_channel_id).send(f"Użytkownik `{inv.inviter.name}` otrzymał 50 mech coinów za zaproszenie {member.mention} (teraz {money[str(inv.inviter.id)]}) [`{inv.code}`]") 
        return
    else:
        for inv in invites_after_join:
            if inv in invites_before_join or inv.uses <= 0:
                continue

            print("new invite used")

            # attach an invite to member id
            value = db['invites']
            value[str(member.id)] = [inv.code, inv.inviter.name, inv.inviter.id]
            db['invites'] = value

            # update invites' num of uses
            previous_invitations[str(member.guild.id)] = invites_after_join

            # if member invited himself, don't give money
            if member.id == inv.inviter.id:
                return

            # add money
            if str(inv.inviter.id) in money:  
                money[str(inv.inviter.id)] += 50
            else:
                money[str(inv.inviter.id)] = 50

            # send all alerts
            print(f"Added 50 money to user {inv.inviter.name} for inviting {member.name} (now at {money[str(inv.inviter.id)]})")
            # (disabled)
            # await malpka.create_dm()
            # await malpka.dm_channel.send(f"`{inv.inviter.name}` earned 50 money for inviting `{member.name}`")
            await member.guild.get_channel(alert_channel_id).send(f"Użytkownik `{inv.inviter.name}` otrzymał 50 mech coinów za zaproszenie {member.mention} (teraz {money[str(inv.inviter.id)]}) [`{inv.code}`]")
            return

        else:
            # send all alerts
            print(f"Couldn't add money for inviting `{member.name}`, because invite was single use")
            # (disabled)
            # await malpka.create_dm()
            # await malpka.dm_channel.send(f"Couldn't add money for inviting `{member.name}`, because invite was one use")
            await member.guild.get_channel(alert_channel_id).send(
                f"Nie można było przypisać mech coinów za zaproszenie użytkownika {member.mention}, ponieważ zaproszenie było jednorazowe!"
            )
            return


# ========== ON LEAVE =========== #


@bot.event
async def on_member_remove(member):
    if member == bot.user:
        print(f"I left the server {member.guild.name}!")
        return
    
    invites = db['invites']
    # fetch my profile (disabled)
    # malpka = await member.guild.fetch_member(336475402535174154)
    alert_channel_id = db['alert_channel']

    # remove money from inviter if invitee leaves
    if str(member.id) in invites:
        money = db['money']
        inviter_id = invites[str(member.id)][2]
        money[str(inviter_id)] -= 50
        db['money'] = money

        print(f"REMOVED 50 MONEY FROM {bot.get_user(inviter_id).name} (now {money[str(inviter_id)]})")
        # disabled
        # await malpka.create_dm()
        # await malpka.dm_channel.send(f"Removed 50 money from `{member.guild.get_member(int(inviter_id)).name}`, because `{member.name}` left")
        await member.guild.get_channel(alert_channel_id).send(f"Usunięto 50 mech coinów użytkownikowi `{bot.get_user(inviter_id).name}` (teraz {money[str(inviter_id)]}), ponieważ użytkownik `{member.name}` wyszedł z serwera :pensive:")
    elif member.bot:
        print(f"{member.name} left the server, but was a bot")
        await member.guild.get_channel(alert_channel_id).send(f"Nie usunięto mech coinów, ponieważ użytkownik `{member.name}` jest botem.")
    # no invite in db
    else:
        print(f"{member.name} left the server")
        await member.guild.get_channel(alert_channel_id).send(f"Nie usunięto mech coinów, ponieważ brak zaproszenia dla użytkownika `{member.name}`!")


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

    xp = db['xp']
    temp_xp = db['temp_xp']
    money = db['money']
    xp_channel_settings = db['xp_channel_settings']
    xp_category_settings = db['xp_category_settings']

    # == XP == #
    if message.channel.type == discord.ChannelType.text:
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
            # try:
            #     await message.author.add_roles(message.guild.get_role(lvl_roles['1']))
            # except Exception as e:
            #     print("Could not add a role:")
            #     print(e)

        if str_user_id not in temp_xp:
            temp_xp[str_user_id] = str(0)

        if str_user_id not in money:
            money[str_user_id] = 0

        old_xp = float(xp[str_user_id])

        # if a member wrote a msg in a whitelisted channel, add {str_xp_added} xp to that member
        if float(str_xp_added) > 0:
            xp[str_user_id] = str(round(float(xp[str_user_id]) + float(str_xp_added), 1))
            temp_xp[str_user_id] = str(round(float(temp_xp[str_user_id]) + float(str_xp_added), 1))
            print(f"Added {str_xp_added} xp to \"{message.author.name}\" in guild \"{message.guild.name}\" (now {xp[str_user_id]})")

        await update_user_lvl_roles(message, bot, message.author, old_xp, float(xp[str_user_id]))

        # add money for each 5 xp
        if float(temp_xp[str_user_id]) >= 5:
            money[str_user_id] += int(float(temp_xp[str_user_id]) / 5)    # division without the remainder
            temp_xp[str_user_id] = str(float(temp_xp[str_user_id]) % 5)    # leave the remainder from division in temp_xp

        db['temp_xp'] = temp_xp
        db['money'] = money
        db['xp'] = xp

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

keep_alive()
bot.run(DISCORD_TOKEN)
