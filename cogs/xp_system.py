from my_utils import Paginator, get_placement_sign, get_placements_embed, get_lvl, NO_MENTIONS, TRANSLATIONS

import inspect
import traceback
from asyncio import Lock
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
import aiosqlite
from handle_database import (
    get_locale,
    get_lvl_roles,
    set_lvl_role,
    get_xp,
    get_all_xp,
    add_xp as db_add_xp,
    remove_xp as db_remove_xp,
    get_xp_channel_settings,
    get_xp_category_settings,
    get_xp_category_multiplier,
    set_xp_channel_multiplier,
    set_xp_category_multiplier,
)

lock = Lock()
OWNER_ID = 336475402535174154


# =========FUNCTIONS========== #

async def _get_locale(user_id):
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            return await get_locale(cursor, user_id)


async def check_lvl_role_validity(ctx, user, new_lvl, lvl_roles):
    """Remove stale level roles and ensure the user has the new level's role."""
    new_role_id = lvl_roles.get(str(new_lvl))
    new_lvl_role = ctx.guild.get_role(new_role_id) if new_role_id is not None else None
    # Without a usable mapping/role there is nothing valid to assign.
    if new_lvl_role is None:
        return False
    if new_lvl_role in user.roles:
        return True

    print(f"Invalid role for user \"{user.name}\" in guild \"{ctx.guild.name}\"!")
    user_role_ids = {role.id for role in user.roles}
    stale_roles = []
    for role_id in lvl_roles.values():
        role = ctx.guild.get_role(role_id) if role_id is not None else None
        if role is not None and role != new_lvl_role and role.id in user_role_ids:
            stale_roles.append(role)

    if stale_roles:
        await user.remove_roles(*stale_roles)
    await user.add_roles(new_lvl_role)
    print(f"Fixed role for user \"{user.name}\" in guild \"{ctx.guild.name}\"")
    return True


def get_required_xp_for_lvl(lvl: int):
    """Starting from lvl 0?"""  # TODO check
    return 2**(lvl+2)


async def update_user_lvl_roles(ctx, bot, user, old_xp, new_xp, *, commit=None):
    """Update a member's level roles.

    Calling convention:
        The XP/DB transaction must be committed before this coroutine is
        awaited. Call it as ``await update_user_lvl_roles(ctx, bot, user,
        old_xp, new_xp)``. If it has to be called while the caller still holds
        an open transaction, pass a (sync or async) ``commit`` callback, e.g.
        ``await update_user_lvl_roles(ctx, bot, user, old_xp, new_xp,
        commit=conn.commit)``; it is called before any Discord API request.
    """
    async with lock:
        if commit is not None:
            result = commit()
            if inspect.isawaitable(result):
                await result

        # Never read role mappings through the caller's (possibly open)
        # transaction; use a short, independent read instead.
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                lvl_roles = await get_lvl_roles(cursor)

        old_lvl = get_lvl(float(old_xp))
        new_lvl = get_lvl(float(new_xp))

        # A slash-command user option may be a plain User (not a Member),
        # which has neither .roles nor role-management methods.
        member = ctx.guild.get_member(user.id)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(user.id)
            except Exception:
                member = None
        if member is None:
            return

        guild_lvl_roles = {}
        for role in ctx.guild.roles:
            if role.name.endswith(" LVL]"):
                guild_lvl_roles.setdefault(role.name, []).append(role)

        # Walk contiguous levels 1..new_lvl: len(lvl_roles) is not a level.
        # A mapped role may also have been deleted from the guild.
        new_role_ids = {}
        for level in range(1, new_lvl + 1):
            key = str(level)
            role_id = lvl_roles.get(key)
            role = ctx.guild.get_role(role_id) if role_id is not None else None
            if role is not None:
                continue

            existing_roles = guild_lvl_roles.get(f"[{level} LVL]", [])
            if existing_roles:
                role = existing_roles[0]
                print(f"Role \"{role.name}\" already existed in guild \"{ctx.guild.name}\"")
            else:
                role = await ctx.guild.create_role(
                    name=f"[{level} LVL]",
                    color=discord.Colour.purple()
                )
                print(f"Created role \"[{level} LVL]\" in guild \"{ctx.guild.name}\"")
            lvl_roles[key] = role.id
            new_role_ids[key] = role.id

        # Persist the new mappings in a transaction of their own, after all
        # Discord API calls and independently of any XP transaction.
        if new_role_ids:
            async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
                async with conn.execute("BEGIN IMMEDIATE") as cursor:
                    for key, role_id in new_role_ids.items():
                        await set_lvl_role(cursor, int(key), role_id)
                await conn.commit()

        new_role_id = lvl_roles.get(str(new_lvl))
        new_lvl_role = ctx.guild.get_role(new_role_id) if new_role_id is not None else None
        if new_lvl_role is None:
            return

        if new_lvl == old_lvl:
            await check_lvl_role_validity(ctx, member, new_lvl, lvl_roles)
            return

        old_role_id = lvl_roles.get(str(old_lvl))
        old_lvl_role = ctx.guild.get_role(old_role_id) if old_role_id is not None else None
        if (
            old_lvl_role is not None
            and old_lvl_role != new_lvl_role
            and old_lvl_role in member.roles
        ):
            await member.remove_roles(old_lvl_role)
            print(f"Removed role \"{old_lvl_role.name}\" from user \"{user.name}\" in guild \"{ctx.guild.name}\"")

        if new_lvl_role not in member.roles:
            await member.add_roles(new_lvl_role)
            print(f"Added role \"{new_lvl_role.name}\" to user \"{user.name}\" in guild \"{ctx.guild.name}\"")


# =========CLASSES========== #

class Xp(discord.Cog):
    """
    XP and Level commands
    """
    def __init__(self, bot):
        self.bot = bot
        print(f"** SUCCESSFULLY LOADED {__name__} **")

    xp_system = SlashCommandGroup(
        "xp",
        description="Commands connected with the xp system",
        description_localizations=TRANSLATIONS['groups']['xp']['description'],
        guild_only=True
    )

    # =========EVENTS========== #

    async def _respond_error(self, ctx, message, *, ephemeral=False):
        try:
            if getattr(ctx, 'responded', False) and hasattr(ctx, 'send_followup'):
                await ctx.send_followup(message, ephemeral=ephemeral)
            elif isinstance(ctx, discord.ApplicationContext):
                await ctx.respond(message, ephemeral=ephemeral)
            else:
                await ctx.send(message)
        except Exception:
            pass

    async def _handle_error(self, ctx, error):
        if getattr(error, '_xp_error_handled', False):
            return
        error._xp_error_handled = True

        user = getattr(ctx, 'author', None) or getattr(ctx, 'user', None)
        locale = await _get_locale(user.id if user is not None else 0)

        if isinstance(error, commands.MissingPermissions):
            response = TRANSLATIONS['errors']['missing_permissions'].get(
                locale,
                TRANSLATIONS['errors']['missing_permissions'].get('en', 'You do not have %s permission to execute this command!')
            )
            missing = error.missing_permissions[0].upper() if error.missing_permissions else 'required'
            await self._respond_error(ctx, response % missing, ephemeral=True)
            return

        formatted = ''.join(traceback.format_exception(
            type(error), error, getattr(error, '__traceback__', None)
        ))
        print(formatted)
        try:
            with open('errors.txt', 'a') as f:
                f.write(formatted)
                f.write("<<<================================>>>\n")
        except Exception as file_error:
            print(f"Could not write errors.txt: {file_error}")

        try:
            owner = await self.bot.fetch_user(OWNER_ID)
            await owner.send(formatted[:1900])
        except Exception:
            pass

        await self._respond_error(ctx, f"An error occurred: {error}", ephemeral=True)

    # Application-command errors are handled centrally in main.py.

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        await self._handle_error(ctx, error)

    # =========COMMANDS========== #

    @xp_system.command(
        name="show",
        description="Shows lvl and amount of xp",
        description_localizations=TRANSLATIONS['commands']['xp show']['description'],
    )
    async def show_xp(
        self,
        ctx,
        user: discord.commands.Option(
            discord.User,
            description="User you want to check the xp",
            description_localizations=TRANSLATIONS['commands']['xp show']['options']['user'],
            default=None,
        ),
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                command_texts = TRANSLATIONS['commands']['xp show']['texts']

                if user is None:
                    user = ctx.author

                avatar_url = user.display_avatar.url
                xp = await get_all_xp(cursor)
        leaderboard_placement = await get_placement_sign(user.id, xp)

        lvl_text = command_texts['lvl'][locale]
        xp_text = command_texts['xp'][locale]
        placement_text = command_texts['placement'][locale]
        # If user has any xp
        if str(user.id) in xp:
            lvl = get_lvl(float(xp[str(user.id)]))
            full_xp = float(xp[str(user.id)])

            if full_xp.is_integer():
                full_xp = int(full_xp)

            response = f"{lvl_text}\n{xp_text}\n{placement_text}"
            placeholders = (
                lvl,
                full_xp,
                get_required_xp_for_lvl(lvl+1),
                leaderboard_placement,
                len(xp)
            )
            embed = discord.Embed(
                color=discord.Color.purple(),
                description=response % placeholders,
            )
            embed.set_author(
                name=user,
                icon_url=avatar_url,
            )
        # If user has no xp
        else:
            response = f"{lvl_text}\n{xp_text}"
            placeholders = (
                1,
                0,
                get_required_xp_for_lvl(1)
            )
            embed = discord.Embed(
                color=discord.Color.purple(),
                description=response % placeholders,
            )
            embed.set_author(
                name=user,
                icon_url=avatar_url,
            )

        await ctx.respond(embed=embed)


    @xp_system.command(
        name="add",
        description="Add xp (admin only)",
        description_localizations=TRANSLATIONS['commands']['xp add']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def add_xp(
        self,
        ctx,
        xp_amount: discord.commands.Option(
            float,
            description="Amount of xp you want to add to someone",
            description_localizations=TRANSLATIONS['commands']['xp add']['options']['xp_amount'],
            min_value=0,
            required=True,
        ),
        user: discord.commands.Option(
            discord.User,
            description="User you want to add xp to",
            description_localizations=TRANSLATIONS['commands']['xp add']['options']['user'],
            default=None,
        ),
    ):
        if user is None:
            print("no user provided")
            user = ctx.author

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                old_xp = await get_xp(cursor, user.id)
                new_xp = await db_add_xp(cursor, user.id, xp_amount)
            await conn.commit()

        command_texts = TRANSLATIONS['commands']['xp add']['texts']
        # XP is committed; role/Discord work happens after the transaction.
        await update_user_lvl_roles(ctx, self.bot, user, old_xp, new_xp)

        lvl = get_lvl(new_xp)
        full_xp = new_xp

        response = command_texts['response'][locale]
        placeholders = (xp_amount, user.mention, full_xp, lvl)
        await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)


    @xp_system.command(
        name="remove",
        description="remove xp (admin only)",
        description_localizations=TRANSLATIONS['commands']['xp remove']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def remove_xp(
        self,
        ctx,
        xp_amount: discord.commands.Option(
            float,
            description="Amount of xp you want to remove from someone",
            description_localizations=TRANSLATIONS['commands']['xp remove']['options']['xp_amount'],
            min_value=0,
            required=True,
        ),
        user: discord.commands.Option(
            discord.User,
            description="User you want to remove xp from",
            description_localizations=TRANSLATIONS['commands']['xp remove']['options']['user'],
            default=None,
        ),
    ):
        if user is None:
            user = ctx.author

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                old_xp = await get_xp(cursor, user.id)
                new_xp = await db_remove_xp(cursor, user.id, xp_amount)
                if new_xp is None:
                    new_xp = max(old_xp - xp_amount, 0)
            await conn.commit()

        command_texts = TRANSLATIONS['commands']['xp remove']['texts']
        await update_user_lvl_roles(ctx, self.bot, user, old_xp, new_xp)

        lvl = get_lvl(new_xp)
        full_xp = new_xp

        response = command_texts['response'][locale]
        placeholders = (xp_amount, user.mention, full_xp, lvl)
        await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)


    @xp_system.command(
        name="channel",
        description="Configure channel's xp gain (admin only)",
        description_localizations=TRANSLATIONS['commands']['xp channel']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def xp_channel_setting(
        self,
        ctx,
        xp_amount: discord.commands.Option(
            float,
            description="Amount of xp to gain (`0` to disable | `-1` to set to category's default)",
            description_localizations=TRANSLATIONS['commands']['xp channel']['options']['xp_amount'],
            required=True,
        ),
        channel: discord.commands.Option(
            discord.TextChannel,
            description="Channel to configure (this channel by default)",
            description_localizations=TRANSLATIONS['commands']['xp channel']['options']['channel'],
            default=None,
        ),
    ):
        if channel is None:
            channel = ctx.channel

        has_category = channel.category_id is not None
        category_default = 1
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                if xp_amount == -1:
                    await set_xp_channel_multiplier(cursor, channel.id, None)
                    if has_category:
                        found_default = await get_xp_category_multiplier(cursor, channel.category_id)
                        if found_default is not None:
                            category_default = found_default
                elif xp_amount < 0:
                    pass
                else:
                    await set_xp_channel_multiplier(cursor, channel.id, xp_amount)
            await conn.commit()

        command_texts = TRANSLATIONS['commands']['xp channel']['texts']
        if xp_amount == -1:
            response = command_texts['success_default'][locale]
            # Some locales spell out "1 xp" and only take the channel mention;
            # others have a placeholder for the effective default as well.
            placeholders = (channel.mention, category_default)
            if response.count('%s') == 1:
                placeholders = (channel.mention,)
            await ctx.respond(response % placeholders)
            return

        if xp_amount < 0:
            await ctx.respond(command_texts['negative_num'][locale], ephemeral=True)
            return

        response = command_texts['success_custom'][locale]
        placeholders = (channel.mention, xp_amount)
        await ctx.respond(response % placeholders)
        return


    @xp_system.command(
        name="category",
        description="Configure category's default xp gain (admin only)",
        description_localizations=TRANSLATIONS['commands']['xp category']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def xp_category_setting(
        self,
        ctx,
        xp_amount: discord.commands.Option(
            float,
            description="Amount of xp to gain (`0` to disable | `-1` to set to bot's default)",
            description_localizations=TRANSLATIONS['commands']['xp category']['options']['xp_amount'],
            required=True,
        ),
        category: discord.commands.Option(
            discord.CategoryChannel,
            description="Category to configure (this category by default)",
            description_localizations=TRANSLATIONS['commands']['xp category']['options']['category'],
            default=None,
        ),
    ):
        if category is None:
            category = ctx.channel.category

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                if category is None:
                    pass
                elif xp_amount == -1:
                    await set_xp_category_multiplier(cursor, category.id, None)
                elif xp_amount < 0:
                    pass
                else:
                    await set_xp_category_multiplier(cursor, category.id, xp_amount)
            await conn.commit()

        command_texts = TRANSLATIONS['commands']['xp category']['texts']
        if category is None:
            await ctx.respond(command_texts['no_category'][locale])
            return

        if xp_amount == -1:
            response = command_texts['success_default'][locale]
            await ctx.respond(response % category.mention)
            return

        if xp_amount < 0:
            await ctx.respond(command_texts['negative_num'][locale], ephemeral=True)
            return

        response = command_texts['success_custom'][locale]
        placeholders = (category.mention, xp_amount)
        await ctx.respond(response % placeholders)
        return


    @xp_system.command(
        name="settings",
        description="Shows all xp settings (admin only)",
        description_localizations=TRANSLATIONS['commands']['xp settings']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def xp_show_settings(
        self,
        ctx,
        channel_or_category: discord.commands.Option(
            (discord.TextChannel, discord.CategoryChannel),
            description="Which channel/category to show settings of? (All if not provided)",
            description_localizations=TRANSLATIONS['commands']['xp settings']['options']['channel_or_category'],
            default=None,
        ),
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                xp_channel_settings = await get_xp_channel_settings(cursor)
                xp_category_settings = await get_xp_category_settings(cursor)

        command_texts = TRANSLATIONS['commands']['xp settings']['texts']
        if isinstance(channel_or_category, discord.CategoryChannel):
            category = channel_or_category
            printable = ""
            if str(category.id) in xp_category_settings:
                xp_category_setting = xp_category_settings[str(category.id)]
                printable += f"{category.mention} - {xp_category_setting} xp\n"
                for channel in category.channels:
                    if str(channel.id) in xp_channel_settings:
                        xp_channel_setting = xp_channel_settings[str(channel.id)]
                        if len(printable + f"> {channel.mention} - {xp_channel_setting} xp\n") > 2000:
                            await ctx.respond(printable)
                            printable = ""
                        printable += f"> {channel.mention} - {xp_channel_setting} xp\n"
                    else:
                        if len(printable + f"> {channel.mention} - {xp_category_setting} xp\n") > 2000:
                            await ctx.respond(printable)
                            printable = ""
                        printable += f"> {channel.mention} - {xp_category_setting} xp\n"
                await ctx.respond(printable)
                return
            printable += f"{category.mention} - {1} xp\n"
            for channel in category.channels:
                if str(channel.id) in xp_channel_settings:
                    xp_channel_setting = xp_channel_settings[str(channel.id)]
                    if len(printable + f"> {channel.mention} - {xp_channel_setting} xp\n") > 2000:
                        await ctx.respond(printable)
                        printable = ""
                    printable += f"> {channel.mention} - {xp_channel_setting} xp\n"
                else:
                    if len(printable + f"> {channel.mention} - {1} xp\n") > 2000:
                        await ctx.respond(printable)
                        printable = ""
                    printable += f"> {channel.mention} - {1} xp\n"
            await ctx.respond(printable)
            return

        if isinstance(channel_or_category, discord.TextChannel):
            channel = channel_or_category
            if str(channel.id) in xp_channel_settings:
                xp_setting = xp_channel_settings[str(channel.id)]
                await ctx.respond(f"{channel.mention} - {xp_setting} xp")
                return
            if channel.category and str(channel.category.id) in xp_category_settings:
                xp_setting = xp_category_settings[str(channel.category.id)]
                await ctx.respond(f"{channel.mention} - {xp_setting} xp")
                return
            await ctx.respond(f"{channel.mention} - {1} xp")
            return

        printable = ""
        for by_category in ctx.guild.by_category():
            category = by_category[0]
            if category and str(category.id) in xp_category_settings:
                category_setting = xp_category_settings[str(category.id)]
            else:
                category_setting = 1

            if category:
                category_mention = category.mention
            else:
                category_mention = command_texts['no_category'][locale]
            if len(printable + f"{category_mention} - {category_setting} xp\n") > 2000:
                await ctx.respond(printable)
                printable = ""
            printable += f"{category_mention} - {category_setting} xp\n"

            for channel in by_category[1]:
                if channel.type != discord.ChannelType.text:
                    continue
                if str(channel.id) in xp_channel_settings:
                    channel_setting = xp_channel_settings[str(channel.id)]
                    if len(printable + f"> {channel.mention} - {channel_setting} xp\n") > 2000:
                        await ctx.respond(printable)
                        printable = ""
                    printable += f"> {channel.mention} - {channel_setting} xp\n"
                    continue
                if len(printable + f"> {channel.mention} - {category_setting} xp\n") > 2000:
                    await ctx.respond(printable)
                    printable = ""
                printable += f"> {channel.mention} - {category_setting} xp\n"
        if printable:
            await ctx.respond(printable)
        else:
            await ctx.respond(command_texts['no_category'][locale])

    @xp_system.command(
        name="leaderboard",
        description="Shows a leaderboard of most experienced Mechs",
        description_localizations=TRANSLATIONS['commands']['xp leaderboard']['description'],
    )
    async def xp_leaderboard(
        self,
        ctx,
        page: discord.commands.Option(
            int,
            description="Page you want to show (1 by default)",
            description_localizations=TRANSLATIONS['commands']['xp leaderboard']['options']['page'],
            min_value=1,
            default=1,
        ),
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                xp = await get_all_xp(cursor)

        leaderboard = {
            k: float(v) for k, v in sorted(
                xp.items(),
                key=lambda item: float(item[1]),
                reverse=True
            )
        }

        paginator = Paginator(ctx, 'xp', page, leaderboard)
        embed = await get_placements_embed(
            self.bot, ctx, 'xp', leaderboard, paginator.page
        )
        paginator.embed = embed
        await ctx.respond(embed=embed, view=paginator)

    @xp_system.command(
        name="summary",
        description="Shows a summary of all XP",
        description_localizations=TRANSLATIONS['commands']['xp summary']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def xp_summary(
        self,
        ctx,
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                xp = await get_all_xp(cursor)

        summary = round(sum(float(v) for v in xp.values()), 2)
        await ctx.respond(f"Summary of all XP: {summary}")


# =========SETUP========== #

def setup(bot):
    bot.add_cog(Xp(bot))
