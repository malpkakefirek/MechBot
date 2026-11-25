import discord
from discord.ext import commands
import aiosqlite

from handle_database import (
    clear_lvl_roles,
    clear_temp_xp,
    clear_xp,
    delete_money,
    get_all_xp,
    get_balances,
    get_locale,
    get_permitted_sync,
    get_table_snapshot,
    get_tables,
    set_alert_channel,
    set_locale,
    set_money,
    set_xp,
)

from my_utils import NO_MENTIONS, TRANSLATIONS

# =========STATIC VARIABLES========== #

# =========FUNCTIONS========== #


# =========CLASSES========== #

class Utility(commands.Cog):
    """Komendy użytkowe"""
    def __init__(self, bot):
        import sqlite3
        conn = sqlite3.connect('mechbot.db')
        cursor = conn.cursor()
        self.bot = bot
        self.bot.owner_ids = get_permitted_sync(cursor)
        cursor.close()
        conn.close()

    # =========EVENTS========== #

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
        errors = TRANSLATIONS['errors']

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
        command_texts = TRANSLATIONS['commands']['funfact']['texts']

        await ctx.respond(command_texts['response'][locale])


    @commands.slash_command(
        name="delete_lvl_roles",
        description="Delete all level roles",
        description_localizations=TRANSLATIONS['commands']['delete_lvl_roles']['description'],
        guild_only=True,
    )
    @commands.has_permissions(administrator=True)
    async def delete_lvl_roles(self, ctx):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                command_texts = TRANSLATIONS['commands']['delete_lvl_roles']['texts']
                locale = await get_locale(cursor, ctx.author.id)

        # Discord API calls must not happen while a DB transaction is open.
        for role in [role for role in ctx.guild.roles if role.name.endswith(" LVL]")]:
            try:
                await role.delete()
            except discord.Forbidden:
                print(f"Missing permissions to delete role {role.name} ({role.id})")
            except discord.HTTPException as error:
                print(f"Couldn't delete role {role.name} ({role.id}): {error}")

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                await clear_lvl_roles(cursor)
                await conn.commit()

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
        command_texts = TRANSLATIONS['commands']['give_everyone_role']['texts']
        errors = TRANSLATIONS['errors']

        if not role_to_give.is_assignable():
            response = errors['role_hierarchy'][locale] % (
                role_to_give.mention, ctx.guild.me.top_role.mention
            )
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
        if channel is None:
            channel = ctx.channel

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                command_texts = TRANSLATIONS['commands']['set_alert_channel']['texts']
                locale = await get_locale(cursor, ctx.author.id)
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                await set_alert_channel(cursor, channel.id)
                await conn.commit()

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
            default=discord.ChannelType.text,
        )
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
        command_texts = TRANSLATIONS['commands']['create_channel']['texts']

        if not isinstance(channel_type, discord.ChannelType):
            try:
                channel_type = discord.ChannelType(channel_type)
            except (TypeError, ValueError):
                channel_type = discord.ChannelType[str(channel_type).lower()]
        no_view_permission = discord.PermissionOverwrite(read_messages=False)
        create_channel_function = getattr(ctx.guild, f"create_{channel_type.name}_channel")
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
        command_texts = TRANSLATIONS['commands']['language']['texts']
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                if not language:
                    response = command_texts['current_language'][locale]
                    await ctx.respond(response)
                    return

                await set_locale(cursor, ctx.author.id, language)
            await conn.commit()

        response = command_texts['change_success'][language]
        await ctx.respond(response)


    @commands.command(
        name="debug",
        brief="Print database to console (bot owner only)",
        description="`$debug <database_name>`\n\nInput \"all\" to print all databases.",
        hidden=True,
    )
    @commands.is_owner()
    async def debug(self, ctx, *, value):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                if value == "all":
                    for table in await get_tables(cursor):
                        print(table)
                        print(f"{table} ——— {await get_table_snapshot(cursor, table)}")
                    return

                record = await get_table_snapshot(cursor, value)
                print(record)
                print(type(record))


    @commands.command(
        name="fix",
        brief="Fix a database (bot owner only)",
        description="`$fix <database_name>`\n\nConvert database values to correct ones or reset the database if it doesn't work.",
        hidden=True,
    )
    @commands.is_owner()
    async def fix(self, ctx, *, value):
        responses = []
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                if value == "money":
                    balances = await get_balances(cursor)
                    for member_id, amount in balances.items():
                        member_id = int(member_id)
                        member = ctx.guild.get_member(member_id) if ctx.guild else None
                        if member is not None and member.bot:
                            await delete_money(cursor, member_id)
                            continue
                        await set_money(cursor, member_id, int(float(amount)))
                    responses.append("Fixed money db")
                elif value == "xp":
                    xp = await get_all_xp(cursor)
                    for member_id, amount in xp.items():
                        await set_xp(cursor, int(member_id), str(amount))
                    responses.append("Fixed xp db")
                elif value == "xp_hard":
                    await clear_xp(cursor)
                    await clear_temp_xp(cursor)
                    responses.extend(("Fixed xp db", "Fixed temp xp db"))
                else:
                    responses.append("Couldn't fix the db, try doing it manually in the console")
            await conn.commit()

        for response in responses:
            await ctx.send(response)

    print(f"** SUCCESSFULLY LOADED {__name__} **")


# =========SETUP========== #

def setup(bot):
    """Every cog needs a setup function like this."""
    bot.add_cog(Utility(bot))
