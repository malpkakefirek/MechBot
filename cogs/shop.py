from my_utils import CURRENCY_NAME, NO_MENTIONS, TRANSLATIONS

import asyncio
import tracemalloc
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
import aiosqlite
from handle_database import (
    add_money,
    debit_money,
    get_balance,
    get_locale,
    get_shop,
    get_shop_item,
    remove_shop_item,
    set_shop_item,
)

tracemalloc.start()

shop_return_lock = asyncio.Lock()


# =========FUNCTIONS========== #

async def get_shop_autocomplete(ctx: discord.AutocompleteContext):
    """Return the current shop items as autocomplete choices."""
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            shop = await get_shop(cursor)
    return {name: name for name in shop}


async def get_returnable_shop_autocomplete(ctx: discord.AutocompleteContext):
    """Return only currently returnable shop items as autocomplete choices."""
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            shop = await get_shop(cursor)
    return {name: name for name, details in shop.items() if details['returnable']}


async def apply_money_delta(user_id, amount):
    """Apply a money delta in its own short transaction (for compensation)."""
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("BEGIN IMMEDIATE")
            await add_money(cursor, user_id, amount)
            await conn.commit()


def format_role_hierarchy_error(locale, role, bot_member):
    bot_top_role = bot_member.top_role if bot_member is not None else None
    return TRANSLATIONS['errors']['role_hierarchy'][locale] % (
        role.mention if role is not None else "`None`",
        bot_top_role.mention if bot_top_role is not None else "`None`",
    )


# =========CLASSES========== #

class Shop(discord.Cog):
    """
    Shop commands
    """
    def __init__(self, bot):
        self.bot = bot
        print(f"** SUCCESSFULLY LOADED {__name__} **")

    shop_system = SlashCommandGroup(
        "shop",
        description="Commands connected with the shop",
        description_localizations=TRANSLATIONS['groups']['shop']['description'],
        guild_only=True,
    )

    # Application-command errors are handled centrally in main.py.

    # =========COMMANDS========== #

    @shop_system.command(
        name="list",
        description="Shows all items in shop",
        description_localizations=TRANSLATIONS['commands']['shop list']['description']
    )
    async def shop_list(
        self,
        ctx,
    ):
        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                command_texts = TRANSLATIONS['commands']['shop list']['texts']
                locale = await get_locale(cursor, ctx.author.id)

                shop = await get_shop(cursor)
        text = ""
        for item_name in shop:
            price = shop[item_name]['price']
            description = shop[item_name]['description']
            if shop[item_name]['returnable']:
                non_returnable = ""
            else:
                non_returnable = command_texts['non-returnable'][locale]
            text += f"**{item_name}** {non_returnable}- {price}{CURRENCY_NAME}\n {description}\n\n"
        embed = discord.Embed(
            title=command_texts['title'][locale],
            color=discord.Color.gold(),
            description=text,
        )

        await ctx.respond(embed=embed)


    @shop_system.command(
        name="buy",
        description="Buy something from the shop",
        description_localizations=TRANSLATIONS['commands']['shop buy']['description'],
    )
    async def shop_buy(
        self,
        ctx: discord.ApplicationContext,
        item: discord.Option(
            str,
            description="Name of the item you want to purchase",
            description_localizations=TRANSLATIONS['commands']['shop buy']['options']['item'],
            autocomplete=get_shop_autocomplete,
        ),
    ):
        command_texts = TRANSLATIONS['commands']['shop buy']['texts']
        errors = TRANSLATIONS['errors']
        item = item.lower()

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                item_details = await get_shop_item(cursor, item)

            # The item might have been removed/renamed since the autocomplete was shown.
            if item_details is None:
                await ctx.respond(errors['item_doesnt_exist'][locale] % item, ephemeral=True)
                return

            role_id = item_details['role_id']
            if not role_id:
                # TODO implement or remove this feature
                await ctx.respond("This feature is not yet implemented!")
                return

            role = ctx.guild.get_role(role_id)
            if role is None:
                await ctx.respond("The role for this item no longer exists.", ephemeral=True)
                return
            if role in ctx.author.roles:
                await ctx.respond(errors['role_present'][locale], ephemeral=True)
                return

            bot_member = ctx.guild.me
            if bot_member is None or not bot_member.guild_permissions.manage_roles:
                await ctx.respond("I don't have permission to manage roles.", ephemeral=True)
                return
            if bot_member.top_role <= role:
                await ctx.respond(
                    format_role_hierarchy_error(locale, role, bot_member),
                    allowed_mentions=NO_MENTIONS,
                )
                return

            price = item_details['price']
            missing_amount = 0
            debited = False
            async with conn.cursor() as cursor:
                await cursor.execute("BEGIN IMMEDIATE")
                # A free item doesn't need an existing balance row.
                debited = price == 0 or await debit_money(cursor, ctx.author.id, price)
                if debited:
                    await conn.commit()
                else:
                    balance = await get_balance(cursor, ctx.author.id)
                    missing_amount = max(0, price - balance)
                    await conn.rollback()

        # Respond after the transaction is closed; no Discord API calls inside it.
        if not debited:
            response = errors['insufficient_funds'][locale]
            await ctx.respond(response % (missing_amount, CURRENCY_NAME))
            return

        try:
            await ctx.author.add_roles(role)
        except discord.Forbidden:
            await apply_money_delta(ctx.author.id, price)
            await ctx.respond(
                format_role_hierarchy_error(locale, role, ctx.guild.me),
                allowed_mentions=NO_MENTIONS,
            )
            return
        except discord.HTTPException:
            await apply_money_delta(ctx.author.id, price)
            await ctx.respond(
                "I couldn't give you the role, so your money was refunded.",
                ephemeral=True,
            )
            return

        response = command_texts['response'][locale]
        await ctx.respond(response % item)


    @shop_system.command(
        name="return",
        description="Return an item, you bought from the shop",
        description_localizations=TRANSLATIONS['commands']['shop return']['description'],
    )
    async def shop_return(
        self,
        ctx,
        item: discord.Option(
            str,
            description="Name of the item you want to return (non-returnable items aren't on this list)",
            description_localizations=TRANSLATIONS['commands']['shop return']['options']['item'],
            autocomplete=get_returnable_shop_autocomplete,
        ),
    ):
        command_texts = TRANSLATIONS['commands']['shop return']['texts']
        errors = TRANSLATIONS['errors']
        await shop_return_lock.acquire()
        try:
            item = item.lower()

            async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
                async with conn.cursor() as cursor:
                    locale = await get_locale(cursor, ctx.author.id)
                    item_details = await get_shop_item(cursor, item)

                if item_details is None:
                    await ctx.respond(errors['item_doesnt_exist'][locale] % item, ephemeral=True)
                    return
                if not item_details['returnable']:
                    await ctx.respond("This item cannot be returned.", ephemeral=True)
                    return

                role_id = item_details['role_id']
                if not role_id:
                    # TODO implement or remove this feature
                    await ctx.respond("This feature is not yet implemented!")
                    return

                role = ctx.guild.get_role(role_id)
                if role is None:
                    await ctx.respond("The role for this item no longer exists.", ephemeral=True)
                    return
                # Re-fetch under the lock so a concurrent return can't reuse a
                # stale cached role list and refund twice.
                try:
                    member = ctx.guild.get_member(ctx.author.id) or await ctx.guild.fetch_member(ctx.author.id)
                except Exception:
                    member = ctx.author
                if role not in member.roles:
                    await ctx.respond(errors['role_absent'][locale], ephemeral=True)
                    return

                bot_member = ctx.guild.me
                if bot_member is None or not bot_member.guild_permissions.manage_roles:
                    await ctx.respond("I don't have permission to manage roles.", ephemeral=True)
                    return
                if bot_member.top_role <= role:
                    await ctx.respond(
                        format_role_hierarchy_error(locale, role, bot_member),
                        allowed_mentions=NO_MENTIONS,
                    )
                    return

                async with conn.cursor() as cursor:
                    await cursor.execute("BEGIN IMMEDIATE")
                    await add_money(cursor, ctx.author.id, item_details['price'])
                    await conn.commit()

            # Role API calls happen only after the refund has been committed.
            try:
                await member.remove_roles(role)
            except discord.Forbidden:
                await apply_money_delta(ctx.author.id, -item_details['price'])
                await ctx.respond(
                    format_role_hierarchy_error(locale, role, ctx.guild.me),
                    allowed_mentions=NO_MENTIONS,
                )
                return
            except discord.HTTPException:
                await apply_money_delta(ctx.author.id, -item_details['price'])
                await ctx.respond(
                    "I couldn't remove the role, so the refund was reversed.",
                    ephemeral=True,
                )
                return

            response = command_texts['response'][locale]
            await ctx.respond(response % item)

        finally:
            shop_return_lock.release()

    @shop_system.command(
        name="modify",
        description="Modify the shop (admin only). When editing, leave empty to keep old settings",
        description_localizations=TRANSLATIONS['commands']['shop modify']['description']
    )
    @commands.has_permissions(administrator=True)
    async def shop_modify(
        self,
        ctx,
        action: discord.Option(
            str,
            description="What you want to do?",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['action'],
            choices=[
                discord.OptionChoice(
                    name="Add",
                    value="Add",
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['add'],
                ),
                discord.OptionChoice(
                    name="Edit",
                    value="Edit",
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['edit'],
                ),
                discord.OptionChoice(
                    name="Remove",
                    value="Remove",
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['remove'],
                )
            ],
        ),
        item_name: discord.Option(
            str,
            description="The item name",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['item_name'],
            autocomplete=get_shop_autocomplete,
        ),
        price: discord.Option(
            int,
            description="Price of the item",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['price'],
            required=False,
        ),
        role: discord.Option(
            discord.Role,
            description="Role you want to sell",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['role'],
            required=False,
        ),
        description: discord.Option(
            str,
            description="Description of this item",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['description'],
            required=False,
        ),
        returnable: discord.Option(
            int,
            description="Can this item be returned? (Yes by default)",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['returnable'],
            choices=[
                discord.OptionChoice(
                    name="Yes",
                    value=1,
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['yes'],
                ),
                discord.OptionChoice(
                    name="No",
                    value=0,
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['no'],
                )
            ],
            default=-1,
        ),
        remove_role: discord.Option(
            int,
            description="Do you want to remove the role from this item? (edit mode only | No by default)",
            description_localizations=TRANSLATIONS['commands']['shop modify']['options']['remove_role'],
            choices=[
                discord.OptionChoice(
                    name="Yes",
                    value=1,
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['yes'],
                ),
                discord.OptionChoice(
                    name="No",
                    value=0,
                    name_localizations=TRANSLATIONS['commands']['shop modify']['options']['no'],
                )
            ],
            default=0,
        ),
    ):
        command_texts = TRANSLATIONS['commands']['shop modify']['texts']
        errors = TRANSLATIONS['errors']
        item_name = item_name.lower()

        async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
            async with conn.cursor() as cursor:
                locale = await get_locale(cursor, ctx.author.id)
                shop = await get_shop(cursor)
                item_details = await get_shop_item(cursor, item_name)

            if action == "Add":
                if item_name in shop:
                    await ctx.respond(
                        errors['item_already_exists'][locale] % item_name,
                        ephemeral=True,
                    )
                    return

                if price is None:
                    await ctx.respond(errors['price_not_provided'][locale], ephemeral=True)
                    return

                role_id = role.id if role else None
                role_mention = role.mention if role else "`None`"
                description = description or "No description"
                returnable_value = True if returnable == -1 else bool(returnable)

                item_details = {
                    'price': price,
                    'role_id': role_id,
                    'description': description,
                    'returnable': returnable_value,
                }
                # Re-check inside the transaction so two admins can't both add it.
                async with conn.cursor() as cursor:
                    await cursor.execute("BEGIN IMMEDIATE")
                    already_added = await get_shop_item(cursor, item_name) is not None
                    if not already_added:
                        await set_shop_item(
                            cursor,
                            item_name,
                            price,
                            role_id,
                            description,
                            returnable_value,
                        )
                        await conn.commit()
                    else:
                        await conn.rollback()

                if already_added:
                    await ctx.respond(
                        errors['item_already_exists'][locale] % item_name,
                        ephemeral=True,
                    )
                    return

                response = command_texts['add_success'][locale]
                placeholders = (item_name, price, role_mention, description, returnable_value)
                print(f"[DEBUG] User {ctx.author} ({ctx.author.id}) added item: {item_details}")
                await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)
                return

            if action == "Edit":
                if item_details is None:
                    await ctx.respond(
                        errors['item_doesnt_exist'][locale] % item_name,
                        ephemeral=True,
                    )
                    return

                price = item_details['price'] if price is None else price
                # An omitted description keeps the existing one.
                description = item_details['description'] if description is None else description
                if remove_role:
                    role_id = None
                    role_mention = command_texts['no_role'][locale]
                else:
                    role_id = item_details['role_id'] if role is None else role.id
                    if role_id:
                        current_role = role or ctx.guild.get_role(role_id)
                        role_mention = (
                            current_role.mention if current_role is not None
                            else command_texts['no_role'][locale]
                        )
                    else:
                        role_mention = command_texts['no_role'][locale]
                returnable_value = (
                    item_details['returnable'] if returnable == -1 else bool(returnable)
                )

                changes = ""
                if price != item_details['price']:
                    response = command_texts['price_change'][locale]
                    placeholders = (item_details['price'], price)

                    changes += response % placeholders
                    item_details['price'] = price

                if role_id != item_details['role_id']:
                    response = command_texts['role_change'][locale]
                    if item_details['role_id']:
                        old_role = ctx.guild.get_role(item_details['role_id'])
                        role_mention_old = (
                            old_role.mention if old_role is not None
                            else command_texts['no_role'][locale]
                        )
                    else:
                        role_mention_old = command_texts['no_role'][locale]
                    placeholders = (role_mention_old, role_mention)

                    changes += response % placeholders
                    item_details['role_id'] = role_id

                if description != item_details['description']:
                    response = command_texts['description_change'][locale]
                    placeholders = (item_details['description'], description)

                    changes += response % placeholders
                    item_details['description'] = description

                if returnable_value != item_details['returnable']:
                    response = command_texts['returnable_change'][locale]
                    placeholders = (item_details['returnable'], returnable_value)

                    changes += response % placeholders
                    item_details['returnable'] = returnable_value

                async with conn.cursor() as cursor:
                    await cursor.execute("BEGIN IMMEDIATE")
                    still_exists = await get_shop_item(cursor, item_name) is not None
                    if still_exists:
                        await set_shop_item(
                            cursor,
                            item_name,
                            item_details['price'],
                            item_details['role_id'],
                            item_details['description'],
                            item_details['returnable'],
                        )
                        await conn.commit()
                    else:
                        await conn.rollback()

                if not still_exists:
                    await ctx.respond(
                        errors['item_doesnt_exist'][locale] % item_name,
                        ephemeral=True,
                    )
                    return

                response = command_texts['edit_success'][locale]
                placeholders = (item_name, changes)
                print(f"[DEBUG] User {ctx.author} ({ctx.author.id}) edited item: {item_details} with changes: {changes}")
                await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)
                return

            if action == "Remove":
                if item_name not in shop:
                    await ctx.respond(
                        errors['item_doesnt_exist'][locale] % item_name,
                        ephemeral=True,
                    )
                    return

                print(f"[DEBUG] User {ctx.author} ({ctx.author.id}) removed item: {shop[item_name]}")
                async with conn.cursor() as cursor:
                    await cursor.execute("BEGIN IMMEDIATE")
                    await remove_shop_item(cursor, item_name)
                    await conn.commit()

                response = command_texts['remove_success'][locale]
                await ctx.respond(response % item_name)
                return

        # if none of the ifs get caught (should never happen)
        print(f"[DEBUG] Unexpected action or error occurred by user {ctx.author} ({ctx.author.id})")
        await ctx.respond("?????")
        return


# =========SETUP========== #

def setup(bot):
    bot.add_cog(Shop(bot))
