import discord
from discord.ext import commands
from replit import db

from my_utils import NO_MENTIONS, TRANSLATIONS

# =========STATIC VARIABLES========== #

# =========FUNCTIONS========== #

# =========CLASSES========== #

class Utility(commands.Cog):
    """Komendy użytkowe"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.owner_ids = db['permitted']
    
    # =========EVENTS========== #
    
    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        locales = db['locales']
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        if isinstance(error, commands.MissingPermissions):
            response = errors['missing_permissions'][locale]
            placeholders = error.missing_permissions[0].upper()
            await ctx.respond(response % placeholders, ephemeral=True)
            return
        raise error  # Here we raise other errors to ensure they aren't ignored
    
    # =========COMMANDS========== #
    
    @commands.slash_command(
        name="funfact",
        description="Shows a funfact about the bot",
        description_localizations=TRANSLATIONS['commands']['funfact']['description'],
    )
    async def fun_fact(self, ctx):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['funfact']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        await ctx.respond(command_texts['response'][locale])
    
    
    @commands.slash_command(
        name="delete_lvl_roles",
        description="Delete all level roles",
        description_localizations=TRANSLATIONS['commands']['delete_lvl_roles']['description'],
        guild_only=True,
    )
    @commands.has_permissions(administrator=True)
    async def delete_lvl_roles(self, ctx):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['delete_lvl_roles']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        lvl_roles = db['lvl_roles']
        for role in [role for role in ctx.guild.roles if role.name.endswith(" LVL]")]:
            await role.delete()
        db['lvl_roles'] = dict()
        await ctx.respond(command_texts['response'][locale])
    
    
    @commands.slash_command(
        name="give_everyone_role",
        description="Give a role to every user with a specified role",
        description_localizations=TRANSLATIONS['commands']['give_everyone_role']['description'],
        guild_only=True,
    )
    @commands.has_permissions(administrator=True)
    async def give_a_role_to_everyone(
        self,
        ctx,
        role_to_give: discord.Option(
            discord.Role,
            description="What role to give",
            description_localizations=TRANSLATIONS['commands']['give_everyone_role']['options']['role_to_give'],
        ),
        give_to_roles: discord.Option(
            discord.Role,
            description="What roles get this role (@everyone by default)",
            description_localizations=TRANSLATIONS['commands']['give_everyone_role']['options']['give_to_roles'],
            required=False,
        ),
        include_bots: discord.Option(
            int,
            description="Should this also include bots (False by default",
            description_localizations=TRANSLATIONS['commands']['give_everyone_role']['options']['include_bots'],
            choices=[
                discord.OptionChoice(
                    name="Yes",
                    value=1,
                    name_localizations=TRANSLATIONS['commands']['give_everyone_role']['options']['yes'],
                ),
                discord.OptionChoice(
                    name="No",
                    value=0,
                    name_localizations=TRANSLATIONS['commands']['give_everyone_role']['options']['no'],
                )
            ],
            default=0,
        ),
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['give_everyone_role']['texts']
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        if not role_to_give.is_assignable():
            text = errors['role_hierarchy'][locale]
            response = text % (role_to_give.mention, ctx.guild.me.top_role.mention)
            await ctx.respond(response, allowed_mentions=NO_MENTIONS)
            return
    
        if not give_to_roles:
            give_to_roles = ctx.guild.default_role
        members_given_role_amount = 0
        members_ignored_amount = 0
        bots_given_role_amount = 0
        bots_ignored_amount = 0
        await ctx.defer()
        for member in ctx.guild.members:
            if give_to_roles not in member.roles:
                continue
            if member.bot:
                if not include_bots:
                    continue
                if role_to_give not in member.roles:
                    await member.add_roles(role_to_give)
                    bots_given_role_amount += 1
                    continue
                bots_ignored_amount += 1
            else:
                if role_to_give not in member.roles:
                    await member.add_roles(role_to_give)
                    members_given_role_amount += 1
                    continue
                members_ignored_amount += 1
    
        response = command_texts['members_added'][locale] % (role_to_give.mention, members_given_role_amount)
        if members_ignored_amount:
            response += command_texts['members_ignored'][locale] % members_ignored_amount
        if include_bots:
            response += command_texts['bots_added'][locale] % bots_given_role_amount
            if bots_ignored_amount:
                response += command_texts['bots_ignored'][locale] % bots_ignored_amount
        await ctx.respond(response, allowed_mentions=NO_MENTIONS)
    
    
    @commands.slash_command(
        name="set_alert_channel",
        description="Set a channel for invite alerts",
        description_localizations=TRANSLATIONS['commands']['set_alert_channel']['description'],
        guild_only=True,
    )
    @commands.has_permissions(administrator=True)
    async def set_alert_channel(
        self,
        ctx,
        channel: discord.Option(
            discord.abc.GuildChannel,
            description="Channel for alerts (this channel by default)",
            description_localizations=TRANSLATIONS['commands']['set_alert_channel']['options']['channel'],
            default=None,
        )
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['set_alert_channel']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        if not channel:
            channel = ctx.channel
            return
    
        db['alert_channel'] = channel.id
        response = command_texts['response'][locale] % channel.mention
        await ctx.respond(response)
    
    
    @commands.slash_command(
        name="create_channel",
        description="Create a channel",
        description_localizations=TRANSLATIONS['commands']['create_channel']['description'],
        guild_only=True,
    )
    @commands.has_permissions(administrator=True)
    async def create_channel(
        self,
        ctx,
        name: discord.Option(
            str,
            description="Name of the channel",
            description_localizations=TRANSLATIONS['commands']['create_channel']['options']['name'],
        ),
        channel_type: discord.Option(
            discord.ChannelType,
            description="Type of the channel",
            description_localizations=TRANSLATIONS['commands']['create_channel']['options']['channel_type'],
            default=discord.TextChannel,
        )
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['create_channel']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        channel_type = str(discord.ChannelType(channel_type))
        no_view_permission = discord.PermissionOverwrite(read_messages=False)
        create_channel_function = getattr(ctx.guild, f"create_{channel_type}_channel")
        channel = await create_channel_function(
            name=name,
            overwrites={ctx.guild.default_role: no_view_permission}
        )
        
        await ctx.respond(command_texts['response'][locale] % channel.mention)
    
    
    @commands.slash_command(
        name="language",
        description="Set your language for this bot",
        description_localizations=TRANSLATIONS['commands']['language']['description'],
    )
    async def language(
        self,
        ctx,
        language: discord.Option(
            str,
            description="Language you want to use",
            description_localizations=TRANSLATIONS['commands']['language']['options']['language'],
            choices=[
                discord.OptionChoice(
                    name="English",
                    value="en",
                    name_localizations=TRANSLATIONS['commands']['language']['options']['en'],
                ),
                discord.OptionChoice(
                    name="Polish",
                    value="pl",
                    name_localizations=TRANSLATIONS['commands']['language']['options']['pl'],
                )
            ],
            default=None,
        )
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['language']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')
    
        if not language:
            response = command_texts['current_language'][locale]
            await ctx.respond(response)
            return
    
        locale = language
        locales[str(ctx.author.id)] = language
        db['locales'] = locales
    
        response = command_texts['change_success'][locale]
        await ctx.respond(response)
    
    
    @commands.command(
        name="debug",
        brief="Print database to console (bot owner only)",
        description="`$debug <database_name>`\n\nInput \"all\" to print all databases.",
        hidden=True,
    )
    @commands.is_owner()
    async def debug(self, ctx, *, value):
        if value == "all":
            for key in db.keys():
                print(key)
                print(f"{key} ——— {db[key]}")
            return
        print(db[value])
        print(type(db[value]))
    
    
    @commands.command(
        name="fix",
        brief="Fix a database (bot owner only)",
        description="`$debug <database_name>`\n\nConvert database values to correct ones or reset the database if it doesn't work.",
        hidden=True,
    )
    @commands.is_owner()
    async def fix(self, ctx, *, value):
        if value == "money":
            money = db['money']
            for member_id in money:
                if ctx.guild.get_member(member_id).bot:
                    del money[member_id]
                    continue
                money[member_id] = int(float(money[member_id]))
            db['money'] = money
            await ctx.send("Fixed money db")
        elif value == "xp":
            xp = db['xp']
            for key, value in db['xp']:
                xp[key] = str(value)
            db['xp'] = xp
            await ctx.send("Fixed lvl_roles db")
        elif value == "xp_hard":
            db['xp'] = dict()
            db['temp_xp'] = dict()
            await ctx.send("Fixed lvl_roles db")
        else:
            await ctx.send("Couldn't fix the db, try doing it manually in the console")
    
    print(f"** SUCCESSFULLY LOADED {__name__} **")

# =========SETUP========== #

def setup(bot):
	"""Every cog needs a setup function like this."""
	bot.add_cog(Utility(bot))