from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord.ext import tasks

from db import Database
from emoji import CHECK, CROSS
from ui import ClaimView, GiveawayView, TicketView, WinnerView
from utils import now_ts


log = logging.getLogger("helzerx-giveaway")


class GiveawayManager:
    def __init__(
        self,
        bot: discord.Client,
        db: Database,
        settings,
    ):
        self.bot = bot
        self.db = db
        self.settings = settings

        self.cache: dict[int, dict] = {}
        self.entry_cache: dict[int, int] = {}

    async def load_active(self) -> None:
        active = await self.db.fetchall(
            "SELECT * FROM giveaways WHERE status='active'"
        )

        for row in active:
            self.cache[row["id"]] = row
            self.entry_cache[row["id"]] = (
                await self.db.entry_count(row["id"])
            )

        winners = await self.db.fetchall(
            """
            SELECT * FROM winners
            WHERE reward_status='pending'
              AND claimed=0
            """
        )

        for row in winners:
            self.bot.add_view(
                ClaimView(
                    self,
                    row["giveaway_id"],
                    row["user_id"],
                )
            )

    def start(self) -> None:
        if not self.finalizer.is_running():
            self.finalizer.start()

    async def create(
        self,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        name: str,
        prize: str,
        host_id: int,
        sponsor_id: int | None,
        winners_count: int,
        end_at: int,
        image_url: str | None,
        reward: str | None,
        reward_delay: int,
        ticket_category_id: int | None,
        required_role_id: int | None,
    ) -> int:
        giveaway_id = await self.db.insert(
            """
            INSERT INTO giveaways
            (
                guild_id,
                channel_id,
                message_id,
                name,
                prize,
                host_id,
                sponsor_id,
                winners_count,
                end_at,
                image_url,
                reward,
                reward_delay,
                ticket_category_id,
                required_role_id,
                status,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, 'active', ?
            )
            """,
            (
                guild_id,
                channel_id,
                message_id,
                name,
                prize,
                host_id,
                sponsor_id,
                winners_count,
                end_at,
                image_url,
                reward,
                reward_delay,
                ticket_category_id,
                required_role_id,
                now_ts(),
            ),
        )

        row = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE id=?",
            (giveaway_id,),
        )

        self.cache[giveaway_id] = row
        self.entry_cache[giveaway_id] = 0

        return giveaway_id

    async def enter_giveaway(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
    ) -> None:
        data = self.cache.get(giveaway_id)

        if (
            not data
            or data["status"] != "active"
            or data["end_at"] <= now_ts()
        ):
            await interaction.response.send_message(
                f"{CROSS} This giveaway has already ended.",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                f"{CROSS} Giveaways can only be entered inside a server.",
                ephemeral=True,
            )
            return

        if data["required_role_id"]:
            member = interaction.guild.get_member(
                interaction.user.id
            )

            if not member:
                try:
                    member = await interaction.guild.fetch_member(
                        interaction.user.id
                    )
                except discord.HTTPException:
                    member = None

            if (
                not member
                or data["required_role_id"]
                not in {role.id for role in member.roles}
            ):
                await interaction.response.send_message(
                    f"{CROSS} You do not have the required role "
                    "to enter this giveaway.",
                    ephemeral=True,
                )
                return

        added = await self.db.add_entry(
            giveaway_id,
            interaction.user.id,
            now_ts(),
        )

        if not added:
            await interaction.response.send_message(
                f"{CROSS} You are already entered in this giveaway.",
                ephemeral=True,
            )
            return

        self.entry_cache[giveaway_id] = (
            self.entry_cache.get(giveaway_id, 0) + 1
        )

        await interaction.response.send_message(
            f"{CHECK} You entered the giveaway.",
            ephemeral=True,
        )

        await self.refresh_message(giveaway_id)

    async def refresh_message(
        self,
        giveaway_id: int,
    ) -> None:
        data = self.cache.get(giveaway_id)

        if not data:
            return

        channel = self.bot.get_channel(data["channel_id"])

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(
                data["message_id"]
            )

            await message.edit(
                view=GiveawayView(
                    self,
                    giveaway_id,
                    disabled=data["status"] != "active",
                )
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return

    @tasks.loop(seconds=5)
    async def finalizer(self) -> None:
        due = await self.db.fetchall(
            """
            SELECT id
            FROM giveaways
            WHERE status='active'
              AND end_at <= ?
            """,
            (now_ts(),),
        )

        for row in due:
            try:
                await self.finish(row["id"])
            except Exception:
                log.exception(
                    "Failed to finalize giveaway %s",
                    row["id"],
                )

    @finalizer.before_loop
    async def before_finalizer(self) -> None:
        await self.bot.wait_until_ready()

    async def finish(
        self,
        giveaway_id: int,
    ) -> list[int]:
        data = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE id=?",
            (giveaway_id,),
        )

        if not data or data["status"] != "active":
            return []

        changed = await self.db.execute(
            """
            UPDATE giveaways
            SET status='ended'
            WHERE id=?
              AND status='active'
            """,
            (giveaway_id,),
        )

        if changed != 1:
            return []

        data = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE id=?",
            (giveaway_id,),
        )

        if not data:
            return []

        entries = await self.db.fetchall(
            """
            SELECT user_id
            FROM entries
            WHERE giveaway_id=?
              AND valid=1
            """,
            (giveaway_id,),
        )

        candidates = [
            int(row["user_id"])
            for row in entries
        ]

        winners = (
            random.sample(
                candidates,
                min(
                    int(data["winners_count"]),
                    len(candidates),
                ),
            )
            if candidates
            else []
        )

        if winners:
            ready_at = (
                now_ts()
                + int(data["reward_delay"])
            )

            claim_expires = (
                ready_at
                + int(
                    self.settings.claim_window_seconds
                )
            )

            for position, user_id in enumerate(
                winners,
                start=1,
            ):
                await self.db.execute(
                    """
                    INSERT OR REPLACE INTO winners
                    (
                        giveaway_id,
                        user_id,
                        position,
                        claimed,
                        claim_expires,
                        reward_ready_at,
                        reward_status,
                        dm_sent
                    )
                    VALUES (
                        ?, ?, ?, 0, ?, ?,
                        'pending', 0
                    )
                    """,
                    (
                        giveaway_id,
                        user_id,
                        position,
                        claim_expires,
                        ready_at,
                    ),
                )

        channel = self.bot.get_channel(
            data["channel_id"]
        )

        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(
                    data["message_id"]
                )

                self.cache[giveaway_id] = dict(data)
                self.entry_cache[giveaway_id] = len(
                    candidates
                )

                await message.edit(
                    view=GiveawayView(
                        self,
                        giveaway_id,
                        disabled=True,
                    )
                )

                await channel.send(
                    view=WinnerView(
                        self,
                        data,
                        winners,
                    ),
                    allowed_mentions=(
                        discord.AllowedMentions(users=True)
                    ),
                )

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass

            finally:
                self.cache.pop(
                    giveaway_id,
                    None,
                )
                self.entry_cache.pop(
                    giveaway_id,
                    None,
                )

        for user_id in winners:
            self.bot.add_view(
                ClaimView(
                    self,
                    giveaway_id,
                    user_id,
                )
            )

            await self.send_winner_dm(
                data,
                user_id,
            )

        return winners

    async def _server_name(
        self,
        guild_id: int,
    ) -> str:
        guild = self.bot.get_guild(guild_id)

        if guild:
            return guild.name.replace(
                "\n",
                " ",
            )

        try:
            guild = await self.bot.fetch_guild(
                guild_id
            )

            return guild.name.replace(
                "\n",
                " ",
            )
        except discord.HTTPException:
            return "Giveaway Server"

    async def send_winner_dm(
        self,
        giveaway: dict,
        user_id: int,
    ) -> None:
        try:
            user = (
                self.bot.get_user(user_id)
                or await self.bot.fetch_user(user_id)
            )

            server_name = await self._server_name(
                giveaway["guild_id"]
            )

            view = ClaimView(
                self,
                giveaway["id"],
                user_id,
                giveaway=giveaway,
                server_name=server_name,
            )

            await user.send(
                view=view,
                allowed_mentions=(
                    discord.AllowedMentions(users=True)
                ),
            )

            await self.db.execute(
                """
                UPDATE winners
                SET dm_sent=1
                WHERE giveaway_id=?
                  AND user_id=?
                """,
                (
                    giveaway["id"],
                    user_id,
                ),
            )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            log.info(
                "Could not DM winner %s for giveaway %s",
                user_id,
                giveaway["id"],
            )

    async def claim_reward(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        user_id: int,
    ) -> None:
        if interaction.user.id != user_id:
            await interaction.response.send_message(
                f"{CROSS} This reward belongs to another user.",
                ephemeral=True,
            )
            return

        winner = await self.db.fetchone(
            """
            SELECT *
            FROM winners
            WHERE giveaway_id=?
              AND user_id=?
            """,
            (
                giveaway_id,
                user_id,
            ),
        )

        giveaway = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE id=?",
            (giveaway_id,),
        )

        if not winner or not giveaway:
            await interaction.response.send_message(
                f"{CROSS} Reward record not found.",
                ephemeral=True,
            )
            return

        if (
            winner["reward_status"] != "pending"
            or winner["claimed"]
        ):
            await interaction.response.send_message(
                f"{CROSS} This reward has already been "
                "claimed or is no longer claimable.",
                ephemeral=True,
            )
            return

        current = now_ts()
        ready_at = winner.get("reward_ready_at") or 0

        if ready_at > current:
            await interaction.response.send_message(
                f"{CHECK} Your reward unlocks "
                f"<t:{ready_at}:R>.",
                ephemeral=True,
            )
            return

        if (
            winner.get("claim_expires")
            and winner["claim_expires"] <= current
        ):
            await interaction.response.send_message(
                f"{CROSS} The reward claim window has expired. "
                "Ask staff for a reroll.",
                ephemeral=True,
            )
            return

        channel_id = self.settings.reward_claim_channel_id

        if not channel_id:
            await interaction.response.send_message(
                f"{CROSS} Reward claim channel is not configured. "
                "Please contact staff.",
                ephemeral=True,
            )
            return

        claimed = await self.db.execute(
            """
            UPDATE winners
            SET claimed=1,
                reward_status='claimed'
            WHERE giveaway_id=?
              AND user_id=?
              AND claimed=0
              AND reward_status='pending'
            """,
            (
                giveaway_id,
                user_id,
            ),
        )

        if claimed != 1:
            await interaction.response.send_message(
                f"{CROSS} This reward has already been claimed "
                "or is no longer claimable.",
                ephemeral=True,
            )
            return

        channel_url = (
            f"https://discord.com/channels/"
            f"{giveaway['guild_id']}/"
            f"{channel_id}"
        )

        view = discord.ui.LayoutView(timeout=None)

        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Button(
                label="Go to Reward Channel",
                emoji="🎁",
                style=discord.ButtonStyle.link,
                url=channel_url,
            )
        )

        view.add_item(
            discord.ui.Container(
                row,
                accent_colour=discord.Colour.green(),
            )
        )

        await interaction.response.send_message(
            view=view,
            ephemeral=True,
        )

    async def close_ticket(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        user_id: int,
    ) -> None:
        if (
            not interaction.guild
            or not interaction.user.guild_permissions.manage_channels
        ):
            await interaction.response.send_message(
                f"{CROSS} You need Manage Channels "
                "to close this ticket.",
                ephemeral=True,
            )
            return

        await self.db.execute(
            """
            UPDATE winners
            SET reward_status='closed'
            WHERE giveaway_id=?
              AND user_id=?
            """,
            (
                giveaway_id,
                user_id,
            ),
        )

        await interaction.response.send_message(
            f"{CHECK} Ticket closed.",
            ephemeral=True,
        )

        await asyncio.sleep(2)

        if interaction.channel:
            try:
                await interaction.channel.delete(
                    reason="Giveaway reward ticket closed"
                )
            except discord.HTTPException:
                pass
