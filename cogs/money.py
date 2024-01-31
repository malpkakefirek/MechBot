import tracemalloc
from sys import exc_info
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
# from discord.errors import Forbidden
import aiosqlite
from handle_database import select_value, update_value

# import time

tracemalloc.start()

from my_utils import Paginator, get_placements_embed, get_placement_sign, CURRENCY_NAME, NO_MENTIONS, TRANSLATIONS

# =========STATIC VARIABLES========== #

# =========FUNCTIONS========== #

# =========CLASSES========== #

class Money(discord.Cog):
    """
    Money commands
    """
    def __init__(self, bot):
        self.bot = bot
        print(f"** SUCCESSFULLY LOADED {__name__} **")

    money_system = SlashCommandGroup(
        "money",
        description="Commands connected with the money system",
        description_localizations=TRANSLATIONS['groups']['money']['description'],
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
        except:
            try:
                user = await self.bot.fetch_user(336475402535174154)
                await user.send(exc)
            except:
                pass

        with open("../errors.txt", 'a') as _f:
            _f.write(exc)
            _f.write("<<<================================>>>")


    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        await cursor.close()
        await conn.close()
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')

        if isinstance(error, commands.MissingPermissions):
            response = errors['missing_permissions'][locale]
            placeholders = error.missing_permissions[0].upper()
            await ctx.respond(response % placeholders, ephemeral=True)
            return
        raise error  # Here we raise other errors to ensure they aren't ignored

    # =========COMMANDS========== #

    @money_system.command(
        name="show",
        description="Show amount of money",
        description_localizations=TRANSLATIONS['commands']['money show']['description'],
    )
    async def show_money(
        self,
        ctx,
        user: discord.Option(
            discord.User,
            description="User you want to check the balance",
            description_localizations=TRANSLATIONS['commands']['money show']['options']['user'],
            default=None,
        ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['money show']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')
        description = command_texts['response'][locale]
        if user is None:
            user = ctx.author

        avatar_url = user.avatar.url
        money = await select_value(cursor, 'money')
        await cursor.close()
        await conn.close()
        leaderboard_placement = await get_placement_sign(user.id, 'money')
        # If user has any money
        if str(user.id) in money:
            balance = money[str(user.id)]

            placeholders = (balance, CURRENCY_NAME, leaderboard_placement, len(money))
            embed = discord.Embed(
                color=discord.Color.green(),
                description=description % placeholders,
            )
            embed.set_author(
                name=user,
                icon_url=avatar_url,
            )
        # If user has no money
        else:
            placeholders = (0, CURRENCY_NAME, 'N', 'A')
            embed = discord.Embed(
                color=discord.Color.green(),
                description=description % placeholders,
            )
            embed.set_author(
                name=user,
                icon_url=avatar_url,
            )

        await ctx.respond(embed=embed)


    @money_system.command(
        name="add",
        description="Add money to a user (admin only)",
        description_localizations=TRANSLATIONS['commands']['money add']['description'],
    )
    @commands.has_permissions(administrator=True)
    async def add_money(
        self,
        ctx,
        money_amount: discord.Option(
            int,
            description="Amount of money you want to add to someone",
            description_localizations=TRANSLATIONS['commands']['money add']['options']['money_amount'],
            min_value=0,
            required=True,
        ),
        user: discord.Option(
            discord.User,
            description="User you want to add money to",
            description_localizations=TRANSLATIONS['commands']['money add']['options']['user'],
            default=None,
        ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['money add']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if user is None:
            user = ctx.author

        await cursor.execute("BEGIN TRANSACTION")
        money = await select_value(cursor, 'money')
        # If user has any money
        if str(user.id) in money:
            money[str(user.id)] = int(money[str(user.id)]) + money_amount
        # If user has no money
        else:
            money[str(user.id)] = money_amount
        await update_value(cursor, 'money', money)
        await conn.commit()
        await cursor.close()
        await conn.close()

        balance = money[str(user.id)]
        response = command_texts['response'][locale]
        placeholders = (money_amount, CURRENCY_NAME, user.mention, balance, CURRENCY_NAME)
        await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)


    @money_system.command(
        name="remove",
        description="Remove money from a user (admin only)",
        description_localizations=TRANSLATIONS['commands']['money remove']['description']
    )
    @commands.has_permissions(administrator=True)
    async def remove_money(
        self,
        ctx,
        money_amount: discord.Option(
            int,
            description="Amount of money you want to remove from someone",
            description_localizations=TRANSLATIONS['commands']['money remove']['options']['money_amount'],
            min_value=0,
            required=True,
        ),
        user: discord.Option(
            discord.User,
            description="User you want to remove money from",
            description_localizations=TRANSLATIONS['commands']['money remove']['options']['user'],
            default=None,
        ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['money remove']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        if user is None:
            user = ctx.author

        await cursor.execute("BEGIN TRANSACTION")
        money = await select_value(cursor, 'money')
        # If user has any money
        if str(user.id) in money:
            money[str(user.id)] = int(money[str(user.id)]) - money_amount
        # If user has no money
        else:
            money[str(user.id)] = -money_amount
        await update_value(cursor, 'money', money)
        await conn.commit()
        await cursor.close()
        await conn.close()

        balance = money[str(user.id)]
        response = command_texts['response'][locale]
        placeholders = (money_amount, CURRENCY_NAME, user.mention, balance, CURRENCY_NAME)
        await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)


    @money_system.command(
        name="pay",
        description="Pay someone",
        description_localizations=TRANSLATIONS['commands']['money pay']['description'],
    )
    async def pay(
        self,
        ctx,
        money_amount: discord.Option(
            int,
            description="Amount of money you want to pay someone",
            description_localizations=TRANSLATIONS['commands']['money pay']['options']['money_amount'],
            min_value=1,
            required=True,
        ),
        receiver: discord.Option(
            discord.User,
            description="User you want to pay",
            description_localizations=TRANSLATIONS['commands']['money pay']['options']['receiver'],
            required=True,
        ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        locales = await select_value(cursor, 'locales')
        command_texts = TRANSLATIONS['commands']['money pay']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        await cursor.execute("BEGIN TRANSACTION")
        money = await select_value(cursor, 'money')
        sender = ctx.author
        # If user has any money
        if str(sender.id) not in money:
            money[str(sender.id)] = 0

        old_sender_balance = int(money[str(sender.id)])
        if old_sender_balance < money_amount:
            response = TRANSLATIONS['errors']['insufficient_funds'][locale]
            await ctx.respond(response) # TODO possibly add info about missing balance
            return

        if str(receiver.id) not in money:
            money[str(receiver.id)] = 0

        money[str(sender.id)] = int(money[str(sender.id)]) - money_amount
        money[str(receiver.id)] = int(money[str(receiver.id)]) + money_amount

        await update_value(cursor, 'money', money)
        await conn.commit()
        await cursor.close()
        await conn.close()

        sender_balance = money[str(sender.id)]
        response = command_texts['response'][locale]
        placeholders = (
            money_amount,
            CURRENCY_NAME,
            receiver.mention,
            sender_balance,
            CURRENCY_NAME
        )
        await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)


    @money_system.command(
        name="leaderboard",
        description="Show leaderboard of richest Mechs",
        description_localizations=TRANSLATIONS['commands']['money leaderboard']['description'],
    )
    async def money_leaderboard(
        self,
        ctx,
        page: discord.Option(
            int,
            description="Page you want to show (1 by default)",
            description_localization=TRANSLATIONS['commands']['money leaderboard']['options']['page'],
            min_value=1,
            default=1,
        ),
    ):
        conn = await aiosqlite.connect('mechbot.db')
        cursor = await conn.cursor()
        money = await select_value(cursor, 'money')
        await cursor.close()
        await conn.close()

        leaderboard = {
            k: int(v) for k, v in sorted(
                money.items(),
                key=lambda item: int(item[1]),
                reverse=True,
            )
        }

        embed = await get_placements_embed(self.bot, ctx, 'money', leaderboard, page)
        await ctx.respond(embed=embed, view=Paginator(ctx, 'money', page, leaderboard))

# =========SETUP========== #

def setup(bot):
    bot.add_cog(Money(bot))
