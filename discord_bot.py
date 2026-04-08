import discord
from discord import app_commands
import asyncio

import os
import aiohttp
from aiohttp import web

from collections import defaultdict
from datetime import datetime, timezone, timedelta

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

try:
    forum_channel_id = int(os.environ['FORUM'])
    fine_channel_id = int(os.environ['FINE'])
    fine_stat_channel_id = int(os.environ["FINE_STAT"])

except:
    forum_channel_id = 0
    fine_channel_id = 0
    fine_stat_channel_id = 0

forum_channel = None
fine_channel = None
fine_stat_channel = None
last_created_post = None
last_created_fine = None
recent_msg = None

KST = timezone(timedelta(hours=9))

##########
# 클래스
##########

class CheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="완료 / 취소", style=discord.ButtonStyle.green, custom_id="done_button")
    async def done(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        
        thread = interaction.channel
        post_date = thread.name
        today = now_kst().strftime("%Y-%m-%d")

        if post_date != today:
            await interaction.followup.send(
                "마감된 날짜입니다",
                ephemeral=True
            )

            return

        if thread == last_created_post:
            msg =  recent_msg
        else:
            msg = await thread.fetch_message(thread.id)
            
        users = parse_users(msg.content)
        uid = str(interaction.user.mention)

        if uid in users:
            users.remove(uid)

        else:
            users.append(uid)

        await update_post(msg, users, True)



##########
# 메서드
##########

# 호스팅 메서드

def now_kst():
    return datetime.now(KST)

async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', health_check) # Health Check API 추가
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()

async def ping_self():
    await client.wait_until_ready()
    
    while not client.is_closed():
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(os.environ['KOYEB_URL']) as r:
                    print("Ping:", r.status)
                
        except Exception as e:
            print("Ping error:", e)
        
        await asyncio.sleep(180)


# 봇 메서드
 
## 닉네임 파싱
def parse_users(text: str):
    users = []
    raw_users = text.split("\n")[2:]
    
    if raw_users[0] != "없음":
        for user in raw_users:
            if user == "\u200b":
                break
            
            users.append(user)
    
    return users

## 가장 최근에 생성된 포스트 가져오기
async def get_latest_post():
    threads = forum_channel.threads
    
    if not threads:
        return None
    
    return max(threads, key=lambda t: t.name)

## 포럼 채널 검사
async def check_forum_channel_valid(interaction: discord.Interaction, channel_id: int):
    if channel_id != forum_channel_id:
        await interaction.response.send_message(
            "설정된 포럼 채널에서만 사용 가능합니다.",
            ephemeral=True
        )
        
        return False

    return True

## 새 포스트 생성
async def create_daily_post(date: datetime):
    global last_created_post, recent_msg

    if forum_channel == None: return False

    date_str = date.strftime("%Y-%m-%d")

    try:
        created_post = await forum_channel.create_thread(
            name=date_str,
            content="완료자:\n\n없음\n\u200b",
            view=CheckView()
        )
        
        last_created_post = created_post.thread
        recent_msg = created_post.message

        print(f"{date_str} 포스트 생성 완료")
        return True

    except Exception as e:
        print(e)
        return False

## 포스트 업데이트
async def update_post(msg: discord.Message, users, today):
    global  recent_msg
    
    text = "완료자:\n\n"
    
    if len(users) == 0:
        text += "없음\n"
        
    else:
        for user in users:
            text += user + "\n"
    
    text += "\u200b"
    
    res = await msg.edit(content=text)
    
    if today:
        recent_msg = res

## 벌금 명단 생성
async def get_fine_members(date: str, msg: discord.Message):
    completed_members = parse_users(msg.content)
    fine_users = []
    
    for mem in client.guilds[0].members:
        if mem.bot:
            continue
        
        if mem.mention not in completed_members:
            fine_users.append(mem.mention)
    
    text = date + " 벌금 대상\n\n"
    
    if len(fine_users) == 0:
        text += "없음"

    else:
        for user in fine_users:
            text += user + "\n"
        
    return text

## 벌금 이력 작성
async def settlefine(thread: discord.Thread):
    if forum_channel == None or fine_channel == None: return False
    
    if thread == last_created_post:
        msg = recent_msg
    else:
        msg = await forum_channel.fetch_message(thread.id)
    
    text = await get_fine_members(thread.name, msg)
    
    await fine_channel.send(text)
    
    return text

## 벌금 현황 텍스트 반환
def get_fine_stat_text(dict: defaultdict):
    txt = "벌금 현황\n\n"
    
    for mem in client.guilds[0].members:
        if mem.bot:
            continue
        
        txt += f"{mem.mention} : {dict[mem.mention]}회\n"
        
    return txt

## 벌금 현황 업데이트
async def update_fine_stat(fine_text: str):
    global last_created_fine
    
    if last_created_fine == None:
        return
    
    fine_stat_dict = defaultdict(int)
    
    for txt in last_created_fine.content.split("\n")[1:]:
        mem, _, num = txt.split()
        num = int(num[:-1])
        
        fine_stat_dict[mem] = num
    
    for mem in fine_text.split("\n")[1:]:
        fine_stat_dict[mem] += 1
    
    txt = get_fine_stat_text(fine_stat_dict)
    last_created_fine = await last_created_fine.edit(content=txt)

## 포럼 채널 ID 설정(관리자 명령어)
@tree.command(name="setforum", description="포럼 채널 설정")
@app_commands.checks.has_permissions(administrator=True)
async def setforum(interaction: discord.Interaction, channel: discord.ForumChannel):
    global forum_channel, forum_channel_id

    forum_channel = channel
    forum_channel_id = channel.id
    
    await interaction.response.send_message(
        f"포럼 채널 설정 완료: {channel.mention}",
        ephemeral=True
    )
    
## 벌금 이력 채널 ID 설정(관리자 명령어)
@tree.command(name="setfine", description="벌금 이력 채널 설정")
@app_commands.checks.has_permissions(administrator=True)
async def setfine(interaction: discord.Interaction, channel: discord.TextChannel):
    global fine_channel, fine_channel_id
    
    fine_channel = channel
    fine_channel_id = channel.id

    await interaction.response.send_message(
        f"벌금이력 채널 설정 완료: {channel.mention}",
        ephemeral=True
    )

## 새 포스트 강제 생성(관리자 명령어)
@tree.command(name="createpost", description="오늘 작업일지 포스트 생성")
@app_commands.checks.has_permissions(administrator=True)
async def createpost(interaction: discord.Interaction):
    today = now_kst()
    success = await create_daily_post(today)

    if success:
        await interaction.response.send_message(
            "포스트 생성 완료",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "생성 실패",
            ephemeral=True
        )

## 벌금 이력 강제 생성(관리자 명령어)
@tree.command(name="createfine", description="벌금 이력 생성")
@app_commands.checks.has_permissions(administrator=True)
async def createfine(interaction: discord.Interaction):
    success = await settlefine(interaction.channel)
    
    if success:
        await interaction.response.send_message(
            "벌금이력 생성 완료",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "생성 실패",
            ephemeral=True
        )
        

## 완료자 명단 수정(관리자 명령어)
@tree.command(name="modifylist", description="완료자 명단 수정")
@app_commands.checks.has_permissions(administrator=True)
async def modifylist(interaction: discord.Interaction, member: discord.Member, value: bool):
    thread = interaction.channel

    if not await check_forum_channel_valid(interaction, thread.parent_id): return
        
    msg = await thread.fetch_message(thread.id)
    users = parse_users(msg.content)
    user = member.mention
        
    if user in users:
        if value == False:
            users.remove(user)
        
    else:
        if value == True:
            users.append(user)

    await update_post(msg, users, thread.name == last_created_post.name)
        
    await interaction.response.send_message(
        "명단 수정 완료",
        ephemeral=True
    )

## 벌금 이력 수정(관리자 명령어)
@tree.command(name="modifyfine", description="벌금 이력 수정")
@app_commands.checks.has_permissions(administrator=True)
async def modifyfine(interaction: discord.Interaction, messageid: str):
    if forum_channel == None or fine_channel == None:
        await interaction.response.send_message(
            "채널 없음.",
            ephemeral=True
        )
        
        return
    
    thread = interaction.channel

    if not await check_forum_channel_valid(interaction, thread.parent_id): return

    try:
        msg = await fine_channel.fetch_message(int(messageid))
    except:
        await interaction.response.send_message(
            "메시지를 찾을 수 없습니다.",
            ephemeral=True
        )
        
        return
    
    if msg.author != client.user:
        await interaction.response.send_message(
            "봇이 생성한 메시지만 수정 가능합니다.",
            ephemeral=True
        )
        
        return

    post_msg = await thread.fetch_message(thread.id)
    text = await get_fine_members(thread.name, post_msg)
    await msg.edit(content=text)
    
    await interaction.response.send_message(
        "벌금이력 수정 완료",
        ephemeral=True
    )

## 벌금 현황 생성(관리자 명령어)
@tree.command(name="createfinestat", description="벌금 현황 생성")
@app_commands.checks.has_permissions(administrator=True)
async def createfinestat(interaction: discord.Interaction):
    global last_created_fine
    
    if fine_stat_channel == None:
        await interaction.response.send_message(
            "채널 없음.",
            ephemeral=True
        )
        
        return

    try:
        last_created_fine = await fine_stat_channel.send(get_fine_stat_text(defaultdict(int)))
        await interaction.response.send_message(
            "벌금 현황 생성 완료",
            ephemeral=True
        )
        
    except:
        await interaction.response.send_message(
            "벌금 현황 생성 실패",
            ephemeral=True
        )

## 벌금 현황 생성(관리자 명령어)
@tree.command(name="modifyfinestat", description="벌금 현황 수정")
@app_commands.checks.has_permissions(administrator=True)
async def modifyfinestat(interaction: discord.Interaction, start_message_id: str = ""):
    global last_created_fine
    
    start_msg = None
    fine_stat_dict = defaultdict(int)
    
    if start_message_id != "":
        start_msg = await fine_channel.fetch_message(start_message_id)
        
        if "벌금 대상" in start_msg.content and "없음" not in start_msg.content:
            for user in start_msg.mentions:
                fine_stat_dict[user.mention] += 1
    
    async for msg in fine_channel.history(after=start_msg):
        if "벌금 대상" not in msg.content:
            continue

        if "없음" in msg.content:
            continue
        
        for user in msg.mentions:
            fine_stat_dict[user.mention] += 1
    
    txt = get_fine_stat_text(fine_stat_dict)
    try:
        last_created_fine = await last_created_fine.edit(content=txt)
        await interaction.response.send_message(
            "벌금 현황 수정 완료",
            ephemeral=True
        )
        
    except:
        await interaction.response.send_message(
            "벌금 현황 수정 실패",
            ephemeral=True
        )
    
    
## 00시 초기화 루프
async def daily_check_loop():
    last_created_date = last_created_post.name if last_created_post else None
        
    while True:
        time = now_kst()
        date_str = time.strftime("%Y-%m-%d")

        if last_created_date != date_str and time.hour == 0:
            await update_fine_stat(await settlefine(last_created_post))
            await create_daily_post(time)
            last_created_date = date_str
        
        await asyncio.sleep(60)
        
# 봇 로그인
@client.event
async def on_ready():
    global forum_channel, fine_channel, fine_stat_channel, last_created_post, last_created_fine, recent_msg
    
    print(f"Logged in as {client.user.name}")
    
    try:
        forum_channel = await client.fetch_channel(forum_channel_id)
        fine_channel = await client.fetch_channel(fine_channel_id)
        fine_stat_channel = await client.fetch_channel(fine_stat_channel_id)
        
    finally:
        if forum_channel == None or not isinstance(forum_channel, discord.ForumChannel):
            print("ID Error! This is not Forum Channel.")
            return None
        
        if fine_channel == None or not isinstance(fine_channel, discord.TextChannel):
            print("ID Error! This is not Text Channel.")
            return None
        
        if fine_stat_channel == None or not isinstance(fine_stat_channel, discord.TextChannel):
            print("ID Error! This is not Text Channel.")
            return None
        
    last_created_post = await get_latest_post()
    if last_created_post != None:
        recent_msg = await last_created_post.fetch_message(last_created_post.id)
    
    msgs = [msg async for msg in fine_stat_channel.history(limit=1)]
    last_created_fine = msgs[0] if msgs else None
    
    client.add_view(CheckView())
    await tree.sync()
    
    client.loop.create_task(start_web_server())
    client.loop.create_task(ping_self())
    client.loop.create_task(daily_check_loop())

client.run(os.environ['TOKEN'])