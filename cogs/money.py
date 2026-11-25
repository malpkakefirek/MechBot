from my_utils import Paginator, get_placements_embed, get_placement_sign, CURRENCY_NAME, NO_MENTIONS, TRANSLATIONS

import tracemalloc
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
import aiosqlite
from handle_database import (
    add_money as db_add_money,
    debit_money,
    get_balance,
    get_balances,
    get_locale,
)

# import time

tracemalloc.start()

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

    # Application-command errors are handled centrally in main.py.

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                command_texts = TRANSLATIONS['commands']['money show']['texts']
                description = command_texts['response'][locale]
                if user is None:
                    user = ctx.author

                avatar_url = user.display_avatar.url
                money = await get_balances(cursor)
        leaderboard_placement = await get_placement_sign(user.id, money)
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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
            command_texts = TRANSLATIONS['commands']['money add']['texts']

            if user is None:
                user = ctx.author

            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                balance = await db_add_money(cursor, user.id, money_amount)
                await conn.commit()

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
            command_texts = TRANSLATIONS['commands']['money remove']['texts']

            if user is None:
                user = ctx.author

            async with conn.execute("BEGIN IMMEDIATE") as cursor:
                balance = await db_add_money(cursor, user.id, -money_amount)
                await conn.commit()

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
            command_texts = TRANSLATIONS['commands']['money pay']['texts']

            sender = ctx.author
            debited = False
            missing_amount = 0
            sender_balance = 0
            async with conn.cursor() as cursor:
                await cursor.execute("BEGIN IMMEDIATE")
                debited = await debit_money(cursor, sender.id, money_amount)
                if debited:
                    await db_add_money(cursor, receiver.id, money_amount)
                    sender_balance = await get_balance(cursor, sender.id)
                    await conn.commit()
                else:
                    balance = await get_balance(cursor, sender.id)
                    missing_amount = max(0, money_amount - balance)
                    await conn.rollback()

        # Respond only after the transaction has been committed or rolled back.
        if not debited:
            response = TRANSLATIONS['errors']['insufficient_funds'][locale]
            await ctx.respond(response % (missing_amount, CURRENCY_NAME))
            return

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
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                money = await get_balances(cursor)

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
