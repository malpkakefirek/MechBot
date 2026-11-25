"""Utilites for my bot"""
from handle_database import get_locale

from math import ceil
import json
import sqlite3
import discord
import aiosqlite


def update_translations():
    global TRANSLATIONS
    with open('translations.json', 'r') as file:
        TRANSLATIONS = json.load(file)


update_translations()

CURRENCY_NAME = " mech coins"
NO_MENTIONS = discord.AllowedMentions().none()


def _get_locale_sync(user_id):
    """Locale lookup for the synchronous Paginator constructor."""
    try:
        with sqlite3.connect('mechbot.db', timeout=10) as conn:
            row = conn.execute(
                "SELECT locale FROM locales WHERE user_id = ?",
                (int(user_id),)
            ).fetchone()
    except Exception:
        return 'pl'
    return row[0] if row else 'pl'


def _get_text(texts, key, locale, default):
    """Read a translated string, accepting either a locale dict or a string."""
    value = texts.get(key)
    if isinstance(value, dict):
        return value.get(locale, value.get('en', value.get('pl', default)))
    return value if value is not None else default


def build_empty_placements_embed(database, locale):
    """Return a valid leaderboard embed when there are no entries at all."""
    if database not in ('xp', 'money'):
        raise Exception("WRONG DATABASE!")

    command_texts = TRANSLATIONS['get_placements_embed']
    is_xp = database == 'xp'
    title = _get_text(
        command_texts,
        'xp_title' if is_xp else 'money_title',
        locale,
        'XP Leaderboard' if is_xp else 'Money Leaderboard',
    )
    description = _get_text(
        command_texts, 'no_entries', locale, 'No entries to display.'
    )
    embed = discord.Embed(
        title=title,
        color=discord.Color.purple() if is_xp else discord.Color.green(),
        description=description,
    )
    page_text = _get_text(command_texts, 'page', locale, 'Page %s/%s')
    try:
        embed.set_footer(text=page_text % (1, 1))
    except TypeError:
        embed.set_footer(text='Page 1/1')
    return embed


class LeftButton(discord.ui.Button):
    """Left button for Paginator"""
    def __init__(self, parent, bot, database, disabled=False):
        self.parent = parent
        self.bot = bot
        self.database = database
        super().__init__(emoji='⬅', disabled=disabled)

    async def callback(self, interaction):
        await interaction.response.defer()
        if not self.parent.leaderboard:
            return

        self.parent.page = max(1, self.parent.page - 1)
        self.parent.update_buttons()
        embed = await get_placements_embed(
            self.bot,
            self.parent.ctx,
            self.database,
            self.parent.leaderboard,
            self.parent.page,
            self.parent.lines_per_page,
        )
        self.parent.embed = embed
        await interaction.edit_original_response(embed=embed, view=self.parent)


class RightButton(discord.ui.Button):
    """Right button for Paginator"""
    def __init__(self, parent, bot, database, disabled=False):
        self.parent = parent
        self.bot = bot
        self.database = database
        super().__init__(emoji='➡', disabled=disabled)

    async def callback(self, interaction):
        await interaction.response.defer()
        if not self.parent.leaderboard:
            return

        self.parent.page = min(self.parent.last_page, self.parent.page + 1)
        self.parent.update_buttons()
        embed = await get_placements_embed(
            self.bot,
            self.parent.ctx,
            self.database,
            self.parent.leaderboard,
            self.parent.page,
            self.parent.lines_per_page,
        )
        self.parent.embed = embed
        await interaction.edit_original_response(embed=embed, view=self.parent)


class Paginator(discord.ui.View):
    """Custom paginator for embeds with 2 buttons (left and right)"""
    def __init__(self, ctx, database: str, page: int, leaderboard, lines_per_page=10, embed=None):
        super().__init__(timeout=None)
        if database not in ('xp', 'money'):
            raise Exception("WRONG DATABASE!")

        self.ctx = ctx
        self.bot = ctx.bot
        self.database = database
        self.leaderboard = leaderboard or {}
        self.lines_per_page = max(1, int(lines_per_page))
        self.last_page = max(1, ceil(len(self.leaderboard) / self.lines_per_page))
        # Keep the requested page inside the available range, including an
        # empty leaderboard (which always has a single, empty page).
        self.page = max(1, min(int(page), self.last_page))
        self.embed = embed
        if not self.leaderboard and self.embed is None:
            self.embed = build_empty_placements_embed(
                self.database, _get_locale_sync(ctx.author.id)
            )

        self.left_button = LeftButton(self, self.bot, self.database, self.page <= 1)
        self.right_button = RightButton(
            self, self.bot, self.database, self.page >= self.last_page
        )
        self.add_item(self.left_button)
        self.add_item(self.right_button)

    def update_buttons(self):
        """Disable a button only when there is no page in that direction."""
        self.left_button.disabled = not self.leaderboard or self.page <= 1
        self.right_button.disabled = not self.leaderboard or self.page >= self.last_page


def get_lvl(xp: float):
    xp_list = [1]
    xp_list.extend([i-2 for i in range(3, 100) if (2**i) <= xp])
    return xp_list[-1]


async def get_placement_sign(user_id: int, database: dict):
    """Returns a placement display when provided with a user_id and a loaded ranking"""
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
    if database not in ('xp', 'money'):
        raise Exception("WRONG DATABASE!")

    async with aiosqlite.connect('mechbot.db', timeout=10) as conn:
        async with conn.cursor() as cursor:
            locale = await get_locale(cursor, ctx.author.id)
    command_texts = TRANSLATIONS['get_placements_embed']

    lines_per_page = max(1, int(lines_per_page))
    last_page = max(1, ceil(len(leaderboard) / lines_per_page))
    page = max(1, min(int(page), last_page))

    if not leaderboard:
        return build_empty_placements_embed(database, locale)

    placement_medals = {1: ":first_place:", 2: ":second_place:", 3: ":third_place:"}
    first_position = (page - 1) * lines_per_page + 1
    last_position = first_position + lines_per_page - 1
    lines = []

    for user_position, (user_id, value) in enumerate(leaderboard.items(), start=1):
        if user_position < first_position:
            continue
        if user_position > last_position:
            break

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
            user_xp = float(value)
            if user_xp.is_integer():
                user_xp = int(user_xp)
            user_lvl = get_lvl(float(user_xp))
            lines.append(f"{placement_sign} {user} **{user_xp}** xp (lvl {user_lvl})")
        else:
            lines.append(
                f"{placement_sign} {user} **{value}** {CURRENCY_NAME}"
            )

    title = _get_text(
        command_texts,
        'xp_title' if database == 'xp' else 'money_title',
        locale,
        'XP Leaderboard' if database == 'xp' else 'Money Leaderboard',
    )
    embed = discord.Embed(
        title=title,
        color=discord.Color.purple() if database == 'xp' else discord.Color.green(),
        description="\n".join(lines),
    )
    page_text = _get_text(command_texts, 'page', locale, 'Page %s/%s')
    try:
        footer = page_text % (page, last_page)
    except TypeError:
        footer = f"Page {page}/{last_page}"
    embed.set_footer(text=footer)
    return embed
