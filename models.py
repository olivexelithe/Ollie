from __future__ import annotations

import discord

from ollie_bot.config import Settings
from ollie_bot.utils import normalize_name


def member_keep_share_roles(member: discord.Member, settings: Settings) -> list[discord.Role]:
    keep_roles: list[discord.Role] = []
    configured = set(settings.keep_share_role_ids)
    prefixes = tuple(prefix.casefold() for prefix in settings.keep_role_prefixes)

    for role in member.roles:
        if role.id in configured:
            keep_roles.append(role)
            continue
        lowered = role.name.casefold()
        if prefixes and any(lowered.startswith(prefix) for prefix in prefixes):
            keep_roles.append(role)

    return keep_roles


def keep_share_keywords(member: discord.Member, settings: Settings) -> list[str]:
    keywords: list[str] = []
    for role in member_keep_share_roles(member, settings):
        text = role.name
        for prefix in settings.keep_role_prefixes:
            if text.casefold().startswith(prefix.casefold()):
                text = text[len(prefix) :].strip(" -:")
                break
        if text:
            keywords.append(text)
    return keywords


def nickname_mentions_keep(member: discord.Member, settings: Settings) -> bool:
    nickname = normalize_name(member.nick or member.display_name)
    if not nickname:
        return False
    keywords = keep_share_keywords(member, settings)
    if not keywords:
        return False
    return any(normalize_name(keyword) in nickname for keyword in keywords)

