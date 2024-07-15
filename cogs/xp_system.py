from my_utils import Paginator, get_placement_sign, get_placements_embed, get_lvl, NO_MENTIONS, TRANSLATIONS

from sys import exc_info
from asyncio import Lock
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
# from discord.errors import Forbidden
import aiosqlite
from handle_database import select_value, update_value

lock = Lock()


# =========FUNCTIONS========== #

async def check_lvl_role_validity(ctx, user, new_lvl, cursor):
    lvl_roles = await select_value(cursor, 'lvl_roles')
    lvl_role = ctx.guild.get_role(lvl_roles[str(new_lvl)])
    if lvl_role not in user.roles:
        try:
            await ctx.defer()
        except Exception:
            pass
        print(f"Invalid role for user \"{user.name}\" in guild \"{ctx.guild.name}\"!")
        all_user_roles_ids = [role.id for role in user.roles]
        all_user_lvl_roles = [
            ctx.guild.get_role(role_id) for role_id in lvl_roles.values() if role_id in all_user_roles_ids
        ]
        await user.remove_roles(*all_user_lvl_roles)
        await user.add_roles(*[lvl_role])
        print(f"Fixed role for user \"{user.name}\" in guild \"{ctx.guild.name}\"")


def get_required_xp_for_lvl(lvl: int):
    """Starting from lvl 0?"""  # TODO check
    return 2**(lvl+2)


async def update_user_lvl_roles(ctx, bot, user, old_xp, new_xp, cursor):
    async with lock:
        lvl_roles = await select_value(cursor, 'lvl_roles')

        old_lvl = get_lvl(old_xp)
        new_lvl = get_lvl(new_xp)
        lvls_added = []

        # if new lvl role doesn't exist yet
        if str(new_lvl) not in lvl_roles:
            # create all lvl roles below new_lvl_role that are missing
            guild_lvl_roles = [role for role in ctx.guild.roles if role.name.endswith(" LVL]")]
            for i in range(len(lvl_roles) + 1, new_lvl + 1):
                if str(i) not in lvl_roles:
                    role_id_list = [role.id for role in guild_lvl_roles if role.name == f"[{i} LVL]"]
                    if role_id_list:
                        lvl_roles[str(i)] = role_id_list[0]
                        print(f"Role \"[{i} LVL]\" already existed in guild \"{ctx.guild.name}\"")
                    else:
                        temp_lvl_role = await ctx.guild.create_role(
                            name=f"[{i} LVL]",
                            color=discord.Colour.purple()
                        )
                        lvl_roles[str(i)] = temp_lvl_role.id
                        print(f"Created role \"[{i} LVL]\" in guild \"{ctx.guild.name}\"")
                    lvls_added.append(str(i))
            await update_value(cursor, 'lvl_roles', lvl_roles)

        # return if levels didn't change
        if new_lvl == old_lvl:
            await check_lvl_role_validity(ctx, user, new_lvl, cursor)
            return

        new_lvl_role = ctx.guild.get_role(lvl_roles[str(new_lvl)])
        old_lvl_role = ctx.guild.get_role(lvl_roles[str(old_lvl)])
        await user.remove_roles(old_lvl_role)
        print(f"Removed role \"{old_lvl_role.name}\" from user \"{user.name}\" in guild \"{ctx.guild.name}\"")
        await user.add_roles(new_lvl_role)
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

    @discord.Cog.listener()
    async def on_error(self, interaction):
        exc = exc_info()
        print(f"interacted failed for {interaction}")
        if interaction.is_component():
            print(interaction.data)
        try:
            interaction.respond(exc)
        except Exception:
            try:
                user = await self.bot.fetch_user(336475402535174154)
                await user.send(exc)
            except Exception:
                pass

        with open("../errors.txt", 'a') as f:
            f.write(exc)
            f.write("<<<================================>>>")


    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ):
        if isinstance(error, commands.MissingPermissions):
            conn = await aiosqlite.connect('mechbot.db')
            cursor = await conn.cursor()
            locales = await select_value(cursor, 'locales')
            await cursor.close()
            await conn.close()
            errors = TRANSLATIONS['errors']
            locale = locales.get(str(ctx.author.id), 'pl')

            response = errors['missing_permissions'][locale]
            placeholders = error.missing_permissions[0].upper()
            await ctx.respond(response % placeholders, ephemeral=True)
            return
        raise error  # Here we raise other errors to ensure they aren't ignored

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp show']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if user is None:
            user = ctx.author

        avatar_url = user.avatar.url
        xp = await select_value(cursor, 'xp')
        await cursor.close()
        await conn.close()
        leaderboard_placement = await get_placement_sign(user.id, 'xp')

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp add']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if user is None:
            print("no user provided")
            user = ctx.author

        await cursor.execute("BEGIN TRANSACTION")
        xp = await select_value(cursor, 'xp')
        # If user has any xp
        if str(user.id) in xp:
            old_xp = float(xp[str(user.id)])
            xp[str(user.id)] = str(float(xp[str(user.id)]) + xp_amount)
        # If user has no xp
        else:
            old_xp = 0
            xp[str(user.id)] = str(xp_amount)
        await update_user_lvl_roles(ctx, self.bot, user, old_xp, float(xp[str(user.id)]), cursor)
        await update_value(cursor, 'xp', xp)
        await conn.commit()
        await cursor.close()
        await conn.close()

        lvl = get_lvl(float(xp[str(user.id)]))
        full_xp = float(xp[str(user.id)])

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp remove']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if user is None:
            user = ctx.author

        await cursor.execute("BEGIN TRANSACTION")
        xp = await select_value(cursor, 'xp')
        # If user has any xp
        if str(user.id) in xp:
            old_xp = float(xp[str(user.id)])
            xp[str(user.id)] = str(max(float(xp[str(user.id)]) - xp_amount, 0))
        # If user has no xp
        else:
            old_xp = 0
            xp[str(user.id)] = str(0)
        await update_user_lvl_roles(ctx, self.bot, user, old_xp, float(xp[str(user.id)]), cursor)
        await update_value(cursor, 'xp', xp)
        await conn.commit()
        await cursor.close()
        await conn.close()

        lvl = get_lvl(float(xp[str(user.id)]))
        full_xp = float(xp[str(user.id)])

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp channel']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if channel is None:
            channel = ctx.channel

        await cursor.execute("BEGIN TRANSACTION")
        xp_channel_settings = await select_value(cursor, 'xp_channel_settings')
        xp_category_settings = await select_value(cursor, 'xp_category_settings')

        if xp_amount == -1:
            del xp_channel_settings[str(channel.id)]

            if channel.category_id and xp_category_settings[channel.category_id]:
                category_default = xp_category_settings[channel.category_id]
            else:
                category_default = 1
            await update_value(cursor, 'xp_channel_settings', xp_channel_settings)
            await conn.commit()
            await cursor.close()
            await conn.close()

            response = command_texts['success_default'][locale]
            placeholders = (channel.mention, category_default)
            await ctx.respond(response % placeholders)
            return

        if xp_amount < 0:
            await conn.commit()
            await cursor.close()
            await conn.close()

            response = command_texts['negative_num'][locale]
            await ctx.respond(response, ephemeral=True)
            return

        xp_channel_settings[channel.id] = str(xp_amount)
        await update_value(cursor, 'xp_channel_settings', xp_channel_settings)
        await conn.commit()
        await cursor.close()
        await conn.close()

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp category']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if category is None:
            if not ctx.channel.category:
                response = command_texts['no_category'][locale]
                await ctx.respond(response)
                return
            category = ctx.channel.category

        await cursor.execute("BEGIN TRANSACTION")
        xp_category_settings = await select_value(cursor, 'xp_category_settings')

        if xp_amount == -1:
            del xp_category_settings[str(category.id)]
            await update_value(cursor, 'xp_category_settings', xp_category_settings)
            await conn.commit()
            await cursor.close()
            await conn.close()

            response = command_texts['success_default'][locale]
            await ctx.respond(response % category.mention)
            return

        if xp_amount < 0:
            await conn.commit()
            await cursor.close()
            await conn.close()

            response = command_texts['negative_num'][locale]
            await ctx.respond(response, ephemeral=True)
            return

        xp_category_settings[str(category.id)] = str(xp_amount)
        await update_value(cursor, 'xp_category_settings', xp_category_settings)
        await conn.commit()
        await cursor.close()
        await conn.close()

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
        # category: discord.commands.Option(
        #     discord.CategoryChannel,
        #     description="Which category to show settings of (all if not provided)",
        #     description_localizations=TRANSLATIONS['commands']['xp settings']['options'][''],
        #     default=None,
        # ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['xp settings']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        # if category and channel:
        #     await ctx.respond("You can only select one option!")
        #     return

        xp_channel_settings = await select_value(cursor, 'xp_channel_settings')
        xp_category_settings = await select_value(cursor, 'xp_category_settings')
        await cursor.close()
        await conn.close()

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
            if str(channel.category.id) in xp_category_settings:
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
        await ctx.respond(printable)

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
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        xp = await select_value(cursor, 'xp')
        await cursor.close()
        await conn.close()

        leaderboard = {
            k: float(v) for k, v in sorted(
                xp.items(),
                key=lambda item: float(item[1]),
                reverse=True
            )
        }

        embed = await get_placements_embed(self.bot, ctx, 'xp', leaderboard, page)
        await ctx.respond(embed=embed, view=Paginator(ctx, 'xp', page, leaderboard))


# =========SETUP========== #

def setup(bot):
    bot.add_cog(Xp(bot))
