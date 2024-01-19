import tracemalloc
from sys import exc_info
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
# from discord.errors import Forbidden
from replit import db
# from math import ceil
# import time

tracemalloc.start()

from my_utils import CURRENCY_NAME, NO_MENTIONS, TRANSLATIONS

# =========FUNCTIONS========== #

# db['shop'] = {'some item name': {'price': int, 'role_id': Optional[int], 'description': str, 'returnable': bool}, ...}
def get_shop_autocomplete(ctx: discord.AutocompleteContext):
    return list(db['shop'])

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

    @shop_system.command(
        name="list",
        description="Shows all items in shop",
        description_localizations=TRANSLATIONS['commands']['shop list']['description']
    )
    async def shop_list(
        self,
        ctx,
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['shop list']['texts']
        locale = locales.get(str(ctx.author.id), 'pl')

        shop = db['shop']
        text = ""
        for item_name in shop:
            price = shop[item_name]['price']
            # if shop[item_name]['role_id']:
            #     role = ctx.guild.get_role(shop[item_name]['role_id'])
            description = shop[item_name]['description']
            if shop[item_name]['returnable']:
                non_returnable = ""
            else:
                non_returnable = command_texts['non-returnable'][locale]
            text += f"**{item_name}** {non_returnable}- {price} {CURRENCY_NAME}\n {description}\n\n"
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
    @discord.commands.option(
        "item",
        description="Name of the item you want to purchase",
        description_localizations=TRANSLATIONS['commands']['shop buy']['options']['item'],
        choices=list(db['shop']),
    )
    async def shop_buy(
        self,
        ctx: discord.ApplicationContext,
        item: str,
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['shop buy']['texts']
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')

        money = db['money']
        shop = db['shop']
        item = item.lower()
        item_details = shop[item]
        if str(ctx.author.id) not in money or money[str(ctx.author.id)] < item_details['price']:
            response = errors['insufficient_funds'][locale]
            await ctx.respond(response) # TODO possibly add info about missing money
            return

        if item_details['role_id']:
            role = ctx.guild.get_role(item_details['role_id'])
            if role in ctx.author.roles:
                response = errors['role_present'][locale]
                await ctx.respond(response, ephemeral=True)
                return

            try:
                await ctx.author.add_roles(role)
            except discord.Forbidden:
                response = errors['role_hierarchy'][locale]
                await ctx.respond(response)
        else:
            # TODO implement or remove this feature
            await ctx.respond("This feature is not yet implemented!")
            return
        money[str(ctx.author.id)] -= item_details['price']
        db['money'] = money

        response = command_texts['response'][locale]
        await ctx.respond(response % item)


    @shop_system.command(
        name="return",
        description="Return an item, you bought from the shop",
        description_localizations=TRANSLATIONS['commands']['shop return']['description'],
    )
    @discord.commands.option(
        "item",
        str,
        description="Name of the item you want to return (non-returnable items aren't on this list)",
        description_localizations=TRANSLATIONS['commands']['shop return']['options']['item'],
        choices=[item for item, description in db['shop'].items() if description['returnable']],
    )
    async def shop_return(
        self,
        ctx,
        item: str,
    ):
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['shop return']['texts']
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')

        money = db['money']
        shop = db['shop']
        item = item.lower()
        item_details = shop[item]
        if str(ctx.author.id) not in money:
            money[str(ctx.author.id)] = 0

        if item_details['role_id']:
            role = ctx.guild.get_role(item_details['role_id'])
            if role not in ctx.author.roles:
                response = errors['role_absent'][locale]
                await ctx.respond(response, ephemeral=True)
                return

            try:
                await ctx.author.remove_roles(role)
            except discord.Forbidden:
                response = errors['role_hierarchy'][locale]
                await ctx.respond(response)
        else:
            # TODO implement or remove this feature
            await ctx.respond("This feature is not yet implemented!")
            return
        money[str(ctx.author.id)] += item_details['price']
        db['money'] = money

        response = command_texts['response'][locale]
        await ctx.respond(response % item)


    @shop_system.command(
        name="modify",
        description="Modify the shop (admin only). When editing, leave empty to keep old settings",
        description_localizations=TRANSLATIONS['commands']['shop modify']['description']
    )
    @commands.has_permissions(administrator=True)
    # @discord.commands.option(
    #   "item_name",
    #   str,
    #   description="The item you want to return (non-returnable items aren't on this list)",
    #   autocomplete=[item for item in db['shop']]
    # )
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
            description="The item name [Due to a bug, autocomplete doesn't work]",
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
        locales = db['locales']
        command_texts = TRANSLATIONS['commands']['shop modify']['texts']
        errors = TRANSLATIONS['errors']
        locale = locales.get(str(ctx.author.id), 'pl')

        shop = db['shop']
        item_name = item_name.lower()

        if action == "Add":
            if item_name in shop:
                response = errors['item_already_exists'][locale]
                await ctx.respond(response % item_name, ephemeral=True)
                return

            if price is None:
                response = errors['price_not_provided'][locale]
                await ctx.respond(response, ephemeral=True)
                return

            role_id = role.id if role else None
            role_mention = ctx.guild.get_role(role_id) if role_id else "`None`"
            description = description or "No description"
            returnable = True if returnable == -1 else bool(returnable)

            shop[item_name] = {
                'price': price,
                'role_id': role_id,
                'description': description,
                'returnable': returnable,
            }
            db['shop'] = shop
            response = command_texts['add_success'][locale]
            placeholders = (item_name, price, role_mention, description, returnable)
            await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)
            return

        if action == "Edit":
            if item_name not in list(shop):
                response = errors['item_doesnt_exist'][locale]
                await ctx.respond(response % item_name, ephemeral=True)
                return

            item_details = shop[item_name]
            price = item_details['price'] if price is None else price
            no_description = command_texts['no_description'][locale]
            description = description or no_description
            if remove_role:
                role_id = None
                role_mention = command_texts['no_role'][locale]
            else:
                role_id = item_details['role_id'] if not role else role.id
                if role_id:
                    role_mention = ctx.guild.get_role(role_id)
                else:
                    role_mention = command_texts['no_role'][locale]
            returnable = item_details['returnable'] if returnable == -1 else bool(returnable)

            changes = ""
            if price != shop[item_name]['price']:
                response = command_texts['price_change'][locale]
                placeholders = (shop[item_name]['price'], price)

                changes += response % placeholders
                shop[item_name]['price'] = price

            if role_id != shop[item_name]['role_id']:
                response = command_texts['role_change'][locale]
                if shop[item_name]['role_id']:
                    role_mention_old = ctx.guild.get_role(shop[item_name]['role_id']).mention
                else:
                    role_mention_old = command_texts['no_role'][locale]
                placeholders = (role_mention_old, role_mention)

                changes += response % placeholders
                shop[item_name]['role_id'] = role_id

            if description != shop[item_name]['description']:
                response = command_texts['description_change'][locale]
                placeholders = (shop[item_name]['description'], description)

                changes += response % placeholders
                shop[item_name]['description'] = description

            if returnable != shop[item_name]['returnable']:
                response = command_texts['returnable_change'][locale]
                placeholders = (shop[item_name]['returnable'], returnable)

                changes += response % placeholders
                shop[item_name]['returnable'] = returnable

            db['shop'] = shop
            response = command_texts['edit_success'][locale]
            placeholders = (item_name, changes)
            await ctx.respond(response % placeholders, allowed_mentions=NO_MENTIONS)
            return

        if action == "Remove":
            if item_name not in shop:
                response = errors['item_doesnt_exist'][locale]
                await ctx.respond(response % item_name, ephemeral=True)
                return

            del shop[item_name]
            response = command_texts['remove_success'][locale]
            await ctx.respond(response % item_name)
            return

        # when none of the ifs get caught
        await ctx.respond("?????")
        return

# =========SETUP========== #

def setup(bot):
    bot.add_cog(Shop(bot))
