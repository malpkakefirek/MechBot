"""Utilites for my bot"""
from handle_database import select_value    # , update_value

from math import ceil
import json
import discord
import aiosqlite


def update_translations():
    global TRANSLATIONS
    with open('translations.json', 'r') as file:
        TRANSLATIONS = json.load(file)


update_translations()

CURRENCY_NAME = " mech coins"
NO_MENTIONS = discord.AllowedMentions().none()


class LeftButton(discord.ui.Button):
    """Left button for Paginator"""
    def __init__(self, parent, bot, database, disabled=False):
        self.parent = parent
        self.bot = bot
        self.database = database
        super().__init__(emoji='⬅', disabled=disabled)

    async def callback(self, interaction):
        for button in self.parent.children:
            button.disabled = False

        self.parent.page -= 1
        if self.parent.page == 1:
            self.disabled = True
        embed = await get_placements_embed(
            self.bot,
            self.parent.ctx,
            self.database,
            self.parent.leaderboard,
            self.parent.page
        )
        await interaction.response.edit_message(embed=embed, view=self.parent)


class RightButton(discord.ui.Button):
    """Right button for Paginator"""
    def __init__(self, parent, bot, database, disabled=False):
        self.parent = parent
        self.bot = bot
        self.database = database
        super().__init__(emoji='➡', disabled=disabled)

    async def callback(self, interaction):
        for button in self.parent.children:
            button.disabled = False

        self.parent.page += 1
        if self.parent.page == self.parent.last_page:
            self.disabled = True
        embed = await get_placements_embed(
            self.bot,
            self.parent.ctx,
            self.database,
            self.parent.leaderboard,
            self.parent.page
        )
        await interaction.response.edit_message(embed=embed, view=self.parent)


class Paginator(discord.ui.View):
    """Custom paginator for embeds with 2 buttons (left and right)"""
    def __init__(self, ctx, database: str, page: int, leaderboard, lines_per_page=10):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.database = database
        self.page = page
        self.leaderboard = leaderboard
        self.last_page = ceil(len(self.leaderboard)/lines_per_page)
        self.add_item(LeftButton(self, ctx.bot, self.database, self.page == 1))
        self.add_item(RightButton(self, ctx.bot, self.database, self.page == self.last_page))


def get_lvl(xp: float):
    xp_list = [1]
    xp_list.extend([i-2 for i in range(3, 100) if (2**i) <= xp])
    return xp_list[-1]


async def get_placement_sign(user_id: int, database_name):
    """Returns a placement display when provided with a user_id and database"""
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            database = await select_value(cursor, database_name)
    placement_medals = {1: ":first_place:", 2: ":second_place:", 3: ":third_place:"}

    if str(user_id) not in database.keys():
        return -1

    # sort database by money and get placement of the user_id
    # (indexing starts from 0, that's why +1)
    placement = [
        int(k) for k, v in sorted(
            database.items(),
            key=lambda item: float(item[1]),
            reverse=True
        )
    ].index(user_id) + 1
    # if in first 3, then return medal, else return placement
    placement_sign = placement_medals.get(placement, f"**#{placement}**")
    return placement_sign


async def get_placements_embed(bot, ctx, database: str, leaderboard: dict, page: int, lines_per_page=10):
    """Returns an embed with the placements"""
    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            locales = await select_value(cursor, 'locales')
    command_texts = TRANSLATIONS['get_placements_embed']
    locale = locales.get(str(ctx.author.id), 'pl')

    text = ""
    user_position = 1
    placement_medals = {1: ":first_place:", 2: ":second_place:", 3: ":third_place:"}
    last_page = ceil(len(leaderboard)/lines_per_page)
    page = min(page, last_page)

    for user_id in leaderboard.keys():
        if user_position <= lines_per_page*(page - 1):
            user_position += 1
            continue

        if user_position == lines_per_page*page + 1:
            break

        if user_position > 1:
            text += "\n"

        # if in first 3, then return medal, else return user_position
        placement_sign = placement_medals.get(user_position, f"**#{user_position}**")

        try:
            user = bot.get_user(int(user_id)).mention
        except Exception:
            try:
                user = await bot.fetch_user(int(user_id))
                user = user.mention
            except Exception:
                user = f"*__{user_id}__*"

        if database == 'xp':
            user_xp = leaderboard[user_id]
            if user_xp.is_integer():
                user_xp = int(user_xp)
            user_lvl = get_lvl(float(user_xp))
            text += f"{placement_sign} {user} **{user_xp}** xp (lvl {user_lvl})"
            user_position += 1

            title = command_texts['xp_title'][locale]
            embed = discord.Embed(
                title=title,
                color=discord.Color.purple(),
                description=text,
            )
            page_text = command_texts['page'][locale]
            embed.set_footer(
                text=page_text % (page, last_page)
            )
        elif database == 'money':
            text += f"{placement_sign} {user} **{leaderboard[user_id]}** {CURRENCY_NAME}"
            user_position += 1

            title = command_texts['money_title'][locale]
            embed = discord.Embed(
                title=title,
                color=discord.Color.green(),
                description=text,
            )
            page_text = command_texts['page'][locale]
            embed.set_footer(
                text=page_text % (page, last_page)
            )
        else:
            raise Exception("WRONG DATABASE!")
    return embed
