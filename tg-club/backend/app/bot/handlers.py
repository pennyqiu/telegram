"""
tg-club Bot handlers

交互设计：
  /start          → 欢迎菜单（inline keyboard）
  /clubs          → 俱乐部分页列表
  /players        → 球员分页列表
  /search <text>  → 搜索俱乐部 / 球员
  /stats          → 系统统计（仅管理员）
  /help           → 命令帮助

Callback 路由（callback_data 格式 → 对应处理）：
  clubs:{page}                → 俱乐部分页列表
  club:{id}                   → 俱乐部详情
  club_players:{id}:{page}    → 某俱乐部下的球员列表
  players:{page}              → 球员分页列表
  player:{id}                 → 球员详情
  player_transfers:{id}       → 球员转会历史
  admin_stats                 → 管理员统计面板
  back_main                   → 返回主菜单
"""

from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import Club, ClubStatus
from app.models.player import Player, PlayerStatus
from app.models.transfer import Transfer
from app.core.config import settings

PAGE_SIZE = 8


# ─── 权限判断 ────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_telegram_ids_set


# ─── 格式化工具 ──────────────────────────────────────────────

def _club_line(c: Club) -> str:
    flag = {"active": "🟢", "disbanded": "⚫", "merged": "🔵"}.get(str(c.status), "⚪")
    short = f" ({c.short_name})" if c.short_name else ""
    return f"{flag} {c.name}{short}"


def _player_line(p: Player) -> str:
    icon = {"active": "✅", "retired": "🔴", "free_agent": "🟡", "loan": "🔄"}.get(str(p.status), "⚪")
    pos = f"[{p.position}]" if p.position else ""
    return f"{icon} {p.name} {pos}"


def _tier_label(tier: str) -> str:
    return {"free": "免费", "basic": "Basic", "pro": "Pro"}.get(tier, tier)


def _main_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🏟 浏览俱乐部", callback_data="clubs:1")],
        [InlineKeyboardButton("⚽ 浏览球员", callback_data="players:1")],
    ]
    if is_admin:
        buttons += [
            [InlineKeyboardButton("📊 管理统计", callback_data="admin_stats")],
            [InlineKeyboardButton("🖥 打开管理后台 ↗", url=settings.admin_web_url)],
        ]
    return InlineKeyboardMarkup(buttons)


# ─── /start ─────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin = _is_admin(user.id)
    role_tag = " 【管理员】" if admin else ""
    await update.message.reply_text(
        f"👋 你好，{user.first_name}{role_tag}！\n\n"
        "请选择操作：",
        reply_markup=_main_keyboard(admin),
    )


# ─── /help ──────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = _is_admin(update.effective_user.id)
    lines = [
        "/start          打开主菜单",
        "/clubs          浏览所有俱乐部",
        "/players        浏览所有球员",
        "/search <关键词> 搜索俱乐部或球员",
        "/help           显示此帮助",
    ]
    if admin:
        lines += [
            "",
            "── 管理员命令 ──",
            "/stats          查看系统统计",
        ]
    await update.message.reply_text("\n".join(lines))


# ─── /clubs ─────────────────────────────────────────────────

async def cmd_clubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_club_list(update, context, page=1, edit=False)


# ─── /players ───────────────────────────────────────────────

async def cmd_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_player_list(update, context, page=1, edit=False)


# ─── /search ────────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("用法：/search <关键词>\n例：/search 曼城")
        return

    async with context.bot_data["db_factory"]() as db:
        like = f"%{query}%"
        clubs = (await db.execute(
            select(Club).where(Club.name.ilike(like)).limit(5)
        )).scalars().all()
        players = (await db.execute(
            select(Player).where(Player.name.ilike(like)).limit(5)
        )).scalars().all()

    if not clubs and not players:
        await update.message.reply_text(f"未找到与「{query}」相关的内容。")
        return

    lines = [f"🔍 搜索「{query}」的结果：\n"]
    buttons = []

    if clubs:
        lines.append("🏟 俱乐部")
        for c in clubs:
            lines.append(f"  {_club_line(c)}")
            buttons.append([InlineKeyboardButton(f"🏟 {c.name}", callback_data=f"club:{c.id}")])

    if players:
        lines.append("\n⚽ 球员")
        for p in players:
            lines.append(f"  {_player_line(p)}")
            buttons.append([InlineKeyboardButton(f"⚽ {p.name}", callback_data=f"player:{p.id}")])

    buttons.append([InlineKeyboardButton("« 返回主菜单", callback_data="back_main")])
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── /stats（管理员） ────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ 该命令仅限管理员使用。")
        return
    await _send_stats(update, context, edit=False)


# ─── 内联键盘 Callback 分发 ──────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("clubs:"):
        page = int(data.split(":")[1])
        await _send_club_list(update, context, page=page, edit=True)

    elif data.startswith("club:"):
        club_id = int(data.split(":")[1])
        await _send_club_detail(update, context, club_id)

    elif data.startswith("club_players:"):
        _, club_id, page = data.split(":")
        await _send_club_players(update, context, int(club_id), int(page))

    elif data.startswith("players:"):
        page = int(data.split(":")[1])
        await _send_player_list(update, context, page=page, edit=True)

    elif data.startswith("player:"):
        player_id = int(data.split(":")[1])
        await _send_player_detail(update, context, player_id)

    elif data.startswith("player_transfers:"):
        player_id = int(data.split(":")[1])
        await _send_player_transfers(update, context, player_id)

    elif data == "admin_stats":
        if not _is_admin(update.effective_user.id):
            await query.answer("⛔ 无权限", show_alert=True)
            return
        await _send_stats(update, context, edit=True)

    elif data == "back_main":
        await query.edit_message_text(
            "请选择操作：",
            reply_markup=_main_keyboard(_is_admin(update.effective_user.id)),
        )


# ─── 内部渲染函数 ─────────────────────────────────────────────

async def _send_club_list(update: Update, context, page: int, edit: bool):
    async with context.bot_data["db_factory"]() as db:
        total = (await db.execute(select(func.count()).select_from(Club))).scalar_one()
        clubs = (await db.execute(
            select(Club).order_by(Club.name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        )).scalars().all()

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"🏟 俱乐部列表（第 {page}/{total_pages} 页，共 {total} 支）\n"]
    buttons = []

    for c in clubs:
        lines.append(_club_line(c))
        buttons.append([InlineKeyboardButton(_club_line(c), callback_data=f"club:{c.id}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("‹ 上一页", callback_data=f"clubs:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("下一页 ›", callback_data=f"clubs:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("« 返回主菜单", callback_data="back_main")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def _send_club_detail(update: Update, context, club_id: int):
    async with context.bot_data["db_factory"]() as db:
        club = await db.get(Club, club_id)
        player_count = (await db.execute(
            select(func.count()).select_from(Player).where(Player.current_club_id == club_id)
        )).scalar_one()

    if not club:
        await update.callback_query.edit_message_text("⚠️ 俱乐部不存在。")
        return

    lines = [
        f"🏟 {club.name}",
        f"{'─' * 24}",
        f"缩写：{club.short_name or '—'}",
        f"国家：{club.country or '—'}",
        f"成立：{club.founded_year or '—'} 年",
        f"主场：{club.stadium or '—'}",
        f"旗下球员：{player_count} 名",
        f"访问权限：{_tier_label(club.access_tier)}",
    ]
    if club.description:
        lines += ["", club.description]

    buttons = [
        [InlineKeyboardButton(f"⚽ 查看球员列表（{player_count}）", callback_data=f"club_players:{club_id}:1")],
        [InlineKeyboardButton("« 返回俱乐部列表", callback_data="clubs:1")],
    ]
    if _is_admin(update.effective_user.id):
        buttons.insert(1, [InlineKeyboardButton("✏️ 编辑（打开管理后台）", url=settings.admin_web_url)])

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _send_club_players(update: Update, context, club_id: int, page: int):
    async with context.bot_data["db_factory"]() as db:
        club = await db.get(Club, club_id)
        total = (await db.execute(
            select(func.count()).select_from(Player).where(Player.current_club_id == club_id)
        )).scalar_one()
        players = (await db.execute(
            select(Player)
            .where(Player.current_club_id == club_id)
            .order_by(Player.name)
            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        )).scalars().all()

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    club_name = club.name if club else f"#{club_id}"
    lines = [f"⚽ {club_name} 球员（第 {page}/{total_pages} 页，共 {total} 名）\n"]
    buttons = []

    for p in players:
        lines.append(_player_line(p))
        buttons.append([InlineKeyboardButton(_player_line(p), callback_data=f"player:{p.id}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("‹ 上一页", callback_data=f"club_players:{club_id}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("下一页 ›", callback_data=f"club_players:{club_id}:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("« 返回俱乐部详情", callback_data=f"club:{club_id}")])

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _send_player_list(update: Update, context, page: int, edit: bool):
    async with context.bot_data["db_factory"]() as db:
        total = (await db.execute(select(func.count()).select_from(Player))).scalar_one()
        players = (await db.execute(
            select(Player).order_by(Player.name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        )).scalars().all()

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"⚽ 球员列表（第 {page}/{total_pages} 页，共 {total} 名）\n"]
    buttons = []

    for p in players:
        lines.append(_player_line(p))
        buttons.append([InlineKeyboardButton(_player_line(p), callback_data=f"player:{p.id}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("‹ 上一页", callback_data=f"players:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("下一页 ›", callback_data=f"players:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("« 返回主菜单", callback_data="back_main")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def _send_player_detail(update: Update, context, player_id: int):
    is_admin = _is_admin(update.effective_user.id)
    async with context.bot_data["db_factory"]() as db:
        player = await db.get(Player, player_id)
        transfer_count = (await db.execute(
            select(func.count()).select_from(Transfer).where(Transfer.player_id == player_id)
        )).scalar_one()

        club_name = None
        if player and player.current_club_id:
            club = await db.get(Club, player.current_club_id)
            club_name = club.name if club else None

    if not player:
        await update.callback_query.edit_message_text("⚠️ 球员不存在。")
        return

    # 判断展示深度（管理员 = 全量，其余按设计简化）
    lines = [f"⚽ {player.name}"]
    if player.name_en:
        lines.append(f"英文名：{player.name_en}")
    lines += [
        f"{'─' * 24}",
        f"位置：{player.position or '—'}",
        f"国籍：{player.nationality or '—'}",
        "状态：" + {'active':'在役','retired':'已退役','free_agent':'自由球员','loan':'租借中'}.get(str(player.status), str(player.status)),
        f"效力：{club_name or '自由球员' if str(player.status) != 'retired' else '已退役'}",
    ]

    if is_admin or player.access_tier in ("free", "basic"):
        lines += [
            f"出生：{player.birth_date or '—'}",
            f"身高：{player.height_cm or '—'} cm",
            f"体重：{player.weight_kg or '—'} kg",
            "惯用脚：" + {'left':'左脚','right':'右脚','both':'双脚'}.get(player.preferred_foot or '', '—'),
        ]

    if is_admin:
        lines += [
            f"评分：{player.rating or '—'} / 10",
            f"球衣号：{player.jersey_number or '—'}",
            f"权限等级：{_tier_label(player.access_tier)}",
        ]
        if player.bio:
            lines += ["", f"简介：{player.bio}"]

    buttons = [
        [InlineKeyboardButton(f"🔄 转会历史（{transfer_count}条）", callback_data=f"player_transfers:{player_id}")],
        [InlineKeyboardButton("« 返回球员列表", callback_data="players:1")],
    ]
    if is_admin:
        buttons.insert(1, [InlineKeyboardButton("✏️ 编辑（打开管理后台）", url=settings.admin_web_url)])

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _send_player_transfers(update: Update, context, player_id: int):
    async with context.bot_data["db_factory"]() as db:
        player = await db.get(Player, player_id)
        result = await db.execute(
            select(Transfer, Club)
            .outerjoin(Club, Transfer.to_club_id == Club.id)
            .where(Transfer.player_id == player_id)
            .order_by(Transfer.transfer_date.desc())
            .limit(10)
        )
        rows = result.all()

    if not player:
        await update.callback_query.edit_message_text("⚠️ 球员不存在。")
        return

    type_label = {
        "permanent": "永久转会 💸",
        "loan": "租借 🔄",
        "loan_end": "租借结束",
        "free": "自由转会",
        "youth": "青训晋升 🌱",
    }

    lines = [f"🔄 {player.name} 转会历史\n{'─' * 24}"]
    if not rows:
        lines.append("暂无转会记录")
    else:
        for transfer, to_club in rows:
            t_label = type_label.get(str(transfer.type), str(transfer.type))
            fee = f"  转会费：{transfer.fee_display}" if transfer.fee_display else ""
            club_name = to_club.name if to_club else "未知"
            lines.append(
                f"📅 {transfer.transfer_date}  {t_label}\n"
                f"   → {club_name}{fee}"
            )

    buttons = [
        [InlineKeyboardButton("« 返回球员详情", callback_data=f"player:{player_id}")],
    ]
    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _send_stats(update: Update, context, edit: bool):
    async with context.bot_data["db_factory"]() as db:
        total_clubs = (await db.execute(select(func.count()).select_from(Club))).scalar_one()
        active_clubs = (await db.execute(
            select(func.count()).select_from(Club).where(Club.status == ClubStatus.active)
        )).scalar_one()
        total_players = (await db.execute(select(func.count()).select_from(Player))).scalar_one()
        active_players = (await db.execute(
            select(func.count()).select_from(Player).where(Player.status == PlayerStatus.active)
        )).scalar_one()
        retired_players = (await db.execute(
            select(func.count()).select_from(Player).where(Player.status == PlayerStatus.retired)
        )).scalar_one()
        total_transfers = (await db.execute(select(func.count()).select_from(Transfer))).scalar_one()
        recent_transfers = (await db.execute(
            select(Transfer, Player)
            .join(Player, Transfer.player_id == Player.id)
            .order_by(Transfer.transfer_date.desc())
            .limit(5)
        )).all()

    lines = [
        "📊 系统统计",
        f"{'─' * 24}",
        f"🏟 俱乐部：{total_clubs} 支（在役 {active_clubs}）",
        f"⚽ 球员：{total_players} 名（在役 {active_players} / 已退役 {retired_players}）",
        f"🔄 转会记录：{total_transfers} 条",
        "",
        "📋 最近 5 条转会",
    ]
    type_label = {"permanent": "签约", "loan": "租借", "free": "自由", "youth": "晋升"}
    for transfer, player in recent_transfers:
        label = type_label.get(str(transfer.type), str(transfer.type))
        fee = f" {transfer.fee_display}" if transfer.fee_display else ""
        lines.append(f"  • {player.name}  {label}{fee}  ({transfer.transfer_date})")

    buttons = [
        [InlineKeyboardButton("🖥 打开管理后台", url=settings.admin_web_url)],
        [InlineKeyboardButton("« 返回主菜单", callback_data="back_main")],
    ]
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)
