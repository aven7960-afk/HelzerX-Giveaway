from __future__ import annotations

import discord

from emoji import (
    ARROW,
    GIFT,
    USERS,
    HOST,
    SPONSOR,
    WINNER,
    TICKET,
    CLAIM,
)
from utils import discord_timestamp


def _separator() -> discord.ui.Separator:
    """Official Discord Components V2 separator."""
    return discord.ui.Separator(
        visible=True,
        spacing=discord.SeparatorSpacing.small,
    )


def _gallery(
    url: str | None,
    description: str,
) -> discord.ui.MediaGallery | None:
    if not url:
        return None

    gallery = discord.ui.MediaGallery()
    gallery.add_item(
        media=url,
        description=description[:1024],
    )
    return gallery


class GiveawayView(discord.ui.LayoutView):
    def __init__(
        self,
        manager,
        giveaway_id: int,
        *,
        disabled: bool = False,
    ):
        super().__init__(timeout=None)
        self.manager = manager
        self.giveaway_id = giveaway_id
        self.disabled = disabled
        self._build()

    def _build(self) -> None:
        data = self.manager.cache.get(self.giveaway_id)
        if not data:
            return

        entries = self.manager.entry_cache.get(
            self.giveaway_id,
            0,
        )
        sponsor = data.get("sponsor_id")

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"# {GIFT} {data['name']} {GIFT}"
            ),
            _separator(),
            discord.ui.TextDisplay(
                f"> {ARROW} **Prize**: {data['prize']}\n"
                f"> {ARROW} **Ends**: "
                f"{discord_timestamp(data['end_at'])}\n"
                f"> {HOST} **Hosted By**: "
                f"<@{data['host_id']}>"
            ),
            discord.ui.TextDisplay(
                f"> {USERS} **Entries**: `{entries}`"
            ),
        ]

        if sponsor:
            children.append(
                discord.ui.TextDisplay(
                    f"> {SPONSOR} **Sponsored by**: "
                    f"<@{sponsor}>"
                )
            )

        children.append(_separator())

        children.append(
            discord.ui.TextDisplay(
                "• Click **Enter Giveaway** Below to participate."
            )
        )

        image = _gallery(
            data.get("image_url"),
            data["name"],
        )

        if image:
            children.append(_separator())
            children.append(image)

        children.append(_separator())

        row = discord.ui.ActionRow()

        button = discord.ui.Button(
            label="Enter Giveaway",
            emoji=GIFT,
            style=discord.ButtonStyle.primary,
            custom_id=f"giveaway:enter:{self.giveaway_id}",
            disabled=self.disabled,
        )

        async def callback(
            interaction: discord.Interaction,
        ) -> None:
            await self.manager.enter_giveaway(
                interaction,
                self.giveaway_id,
            )

        button.callback = callback
        row.add_item(button)
        children.append(row)

        self.add_item(
            discord.ui.Container(
                *children,
                accent_colour=discord.Colour.blurple(),
            )
        )


class WinnerView(discord.ui.LayoutView):
    def __init__(
        self,
        manager,
        giveaway: dict,
        winner_ids: list[int],
    ):
        super().__init__(timeout=None)
        self.manager = manager
        self.giveaway = giveaway
        self.winner_ids = winner_ids
        self._build()

    def _build(self) -> None:
        if self.winner_ids:
            mentions = "\n".join(
                f"{['🥇', '🥈', '🥉'][i] if i < 3 else WINNER} "
                f"<@{uid}>"
                for i, uid in enumerate(self.winner_ids)
            )
        else:
            mentions = "No eligible entries were found."

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"# {GIFT} Giveaway Winners {GIFT}"
            ),
            _separator(),
            discord.ui.TextDisplay(
                f"**Winners**\n\n"
                f"{mentions}\n\n"
                f"> {ARROW} **Prize**: "
                f"{self.giveaway['prize']}\n"
                f"> {HOST} **Hosted By**: "
                f"<@{self.giveaway['host_id']}>"
            ),
            _separator(),
            discord.ui.TextDisplay(
                f"{GIFT} Winners can claim their reward "
                f"from the DM sent by HelzerX."
            ),
        ]

        self.add_item(
            discord.ui.Container(
                *children,
                accent_colour=discord.Colour.gold(),
            )
        )


class ClaimView(discord.ui.LayoutView):
    def __init__(
        self,
        manager,
        giveaway_id: int,
        user_id: int,
        giveaway: dict | None = None,
        server_name: str | None = None,
    ):
        super().__init__(timeout=None)

        self.manager = manager
        self.giveaway_id = giveaway_id
        self.user_id = user_id
        self.giveaway = giveaway
        self.server_name = server_name

        self._build()

    def _build(self) -> None:
        if self.giveaway and self.server_name:
            title = discord.ui.TextDisplay(
                f"# {GIFT} {self.server_name} — "
                f"Giveaway Winner {GIFT}"
            )

            details = discord.ui.TextDisplay(
                f"> {ARROW} Congratulations, "
                f"<@{self.user_id}>!\n\n"
                f"> {ARROW} **Giveaway**: "
                f"{self.giveaway['name']}\n"
                f"> {ARROW} **Prize**: "
                f"{self.giveaway['prize']}\n"
                f"> {ARROW} **Server**: "
                f"{self.server_name}\n"
                f"> {HOST} **Hosted By**: "
                f"<@{self.giveaway['host_id']}>"
            )

            instruction = discord.ui.TextDisplay(
                "Use **Claim Reward** to notify "
                "the giveaway staff and claim your reward."
            )
        else:
            title = discord.ui.TextDisplay(
                f"# {CLAIM} Giveaway Reward"
            )

            details = discord.ui.TextDisplay(
                f"<@{self.user_id}> — use **Claim Reward** "
                "to notify the giveaway staff and claim your reward."
            )

            instruction = discord.ui.TextDisplay(
                "The button remains available until "
                "the claim window expires."
            )

        row = discord.ui.ActionRow()

        button = discord.ui.Button(
            label="Claim Reward",
            emoji=CLAIM,
            style=discord.ButtonStyle.success,
            custom_id=(
                f"giveaway:claim:"
                f"{self.giveaway_id}:"
                f"{self.user_id}"
            ),
        )

        async def callback(
            interaction: discord.Interaction,
        ) -> None:
            await self.manager.claim_reward(
                interaction,
                self.giveaway_id,
                self.user_id,
            )

        button.callback = callback
        row.add_item(button)

        self.add_item(
            discord.ui.Container(
                title,
                _separator(),
                details,
                _separator(),
                instruction,
                row,
                accent_colour=discord.Colour.green(),
            )
        )


class TicketView(discord.ui.LayoutView):
    """Legacy view for old ticket messages.

    New Claim Reward interactions never create tickets.
    """

    def __init__(
        self,
        manager,
        giveaway: dict,
        winner_id: int,
    ):
        super().__init__(timeout=None)

        self.manager = manager
        self.giveaway = giveaway
        self.winner_id = winner_id

        text = discord.ui.TextDisplay(
            f"# {TICKET} Giveaway Reward Ticket\n"
            f"**Winner:** <@{winner_id}>\n"
            f"**Giveaway:** {giveaway['name']}\n"
            f"**Prize:** {giveaway['prize']}\n\n"
            "A staff member can now process the reward."
        )

        row = discord.ui.ActionRow()

        button = discord.ui.Button(
            label="Close Ticket",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id=(
                f"giveaway:close-ticket:"
                f"{giveaway['id']}:{winner_id}"
            ),
        )

        async def callback(
            interaction: discord.Interaction,
        ) -> None:
            await self.manager.close_ticket(
                interaction,
                giveaway["id"],
                winner_id,
            )

        button.callback = callback
        row.add_item(button)

        self.add_item(
            discord.ui.Container(
                text,
                _separator(),
                row,
                accent_colour=discord.Colour.orange(),
            )
        )
