import discord
from discord import app_commands
from datetime import datetime
import asyncio

import os
import aiohttp
from aiohttp import web

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

try:
    forum_channel_id = int(os.environ['FORUM'])
    fine_channel_id = int(os.environ['FINE'])

except:
    forum_channel_id = 0
    fine_channel_id = 0

##########
# 클래스
##########

class CheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="완료 / 취소", style=discord.ButtonStyle.green, custom_id="done_button")
    async def done(self, interaction, button):
        thread = interaction.channel
        post_date = thread.name
        today = datetime.now().strftime("%Y-%m-%d")

        if post_date != today:
            await interaction.response.send_message(
                "마감된 날짜입니다",
                ephemeral=True
            )

            return

        msg = await thread.fetch_message(thread.id)
        users = parse_users(msg.content)
        uid = str(interaction.user.mention)

        if uid in users:
            users.remove(uid)

        else:
            users.append(uid)

        await update_post(thread, users)
        
        await interaction.response.defer(ephemeral=True)



##########
# 메서드
##########

# 호스팅 메서드

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
                await s.get(os.environ['KOYEP_URL'])
                
        except:
            pass
        
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
    forum = None
    
    try:
        forum = await client.fetch_channel(forum_channel_id)
        
    finally:
        if forum == None or not isinstance(forum, discord.ForumChannel):
            print("ID Error! This is not Forum Channel.")
            return None
    
    threads = forum.threads
    
    if len(threads) == 0:
        return None
    
    return threads[-1]

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
    forum = client.get_channel(forum_channel_id)

    if not isinstance(forum, discord.ForumChannel):
        print("ID Error! This is not Forum Channel.")
        return False

    date_str = date.strftime("%Y-%m-%d")

    try:
        await forum.create_thread(
            name=date_str,
            content="완료자:\n\n없음\n\u200b",
            view=CheckView()
        )

        print(f"{date_str} 포스트 생성 완료")
        return True

    except Exception as e:
        print(e)
        return False

## 포스트 업데이트
async def update_post(thread, users):
    text = "완료자:\n\n"
    
    if len(users) == 0:
        text += "없음\n"
        
    else:
        for user in users:
            text += user + "\n"
    
    text += "\u200b"
    msg = await thread.fetch_message(thread.id)
    await msg.edit(content=text)

## 벌금 명단 생성
async def get_fine_members(date: str, thread: discord.Thread):
    msg = await thread.fetch_message(thread.id)
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
    if thread == None:
        return False
    
    fine_channel = None
    
    try:
        fine_channel = await client.fetch_channel(fine_channel_id)
        
    finally:
        if fine_channel == None or not isinstance(fine_channel, discord.TextChannel):
            print("ID Error! This is not Text Channel.")
            return False

    text = await get_fine_members(thread.name, thread)
    
    await fine_channel.send(text)
    
    return True

## 포럼 채널 ID 설정(관리자 명령어)
@tree.command(name="setforum", description="포럼 채널 설정")
@app_commands.checks.has_permissions(administrator=True)
async def setforum(interaction: discord.Interaction, channel: discord.ForumChannel):
    global forum_channel_id
    
    forum_channel_id = channel.id

    await interaction.response.send_message(
        f"포럼 채널 설정 완료: {channel.mention}",
        ephemeral=True
    )
    
## 벌금이력 채널 ID 설정(관리자 명령어)
@tree.command(name="setfine", description="벌금이력 채널 설정")
@app_commands.checks.has_permissions(administrator=True)
async def setfine(interaction: discord.Interaction, channel: discord.TextChannel):
    global fine_channel_id
    
    fine_channel_id = channel.id

    await interaction.response.send_message(
        f"벌금이력 채널 설정 완료: {channel.mention}",
        ephemeral=True
    )

## 새 포스트 강제 생성(관리자 명령어)
@tree.command(name="createpost", description="오늘 작업일지 포스트 생성")
@app_commands.checks.has_permissions(administrator=True)
async def createpost(interaction: discord.Interaction):
    today = datetime.now()
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

## 벌금이력 강제 생성(관리자 명령어)
@tree.command(name="createfine", description="벌금이력 생성")
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
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "포럼 채널의 포스트가 아닙니다.",
            ephemeral=True
        )
        
        return
    
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

    await update_post(thread, users)
        
    await interaction.response.send_message(
        "명단 수정 완료",
        ephemeral=True
    )

## 벌금이력 수정(관리자 명령어)
@tree.command(name="modifyfine", description="벌금이력 수정")
@app_commands.checks.has_permissions(administrator=True)
async def modifyfine(interaction: discord.Integration, messageid: str):
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "포럼 채널의 포스트가 아닙니다.",
            ephemeral=True
        )
        
        return
    
    thread = interaction.channel

    if not await check_forum_channel_valid(interaction, thread.parent_id): return

    fine_channel = client.get_channel(fine_channel_id)
    
    if not isinstance(fine_channel, discord.TextChannel):
        await interaction.response.send_message(
            "벌금 채널을 찾을 수 없습니다.",
            ephemeral=True
        )
    
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

    text = await get_fine_members(thread.name, thread)
    await msg.edit(content=text)
    
    await interaction.response.send_message(
        "벌금이력 수정 완료",
        ephemeral=True
    )

## 00시 초기화 루프
async def daily_check_loop():
    while True:
        time = datetime.now()
        date_str = time.strftime("%Y-%m-%d")
        last_created_post = await get_latest_post()
        last_created_date = last_created_post.name if last_created_post else None

        if last_created_date != date_str and time.hour == 0:
            await settlefine(last_created_post)
            await create_daily_post(time)
        
        await asyncio.sleep(60)
        
# 봇 로그인
@client.event
async def on_ready():
    print(f"Logged in as {client.user.name}")
    
    client.add_view(CheckView())
    await tree.sync()
    
    client.loop.create_task(daily_check_loop())

client.run(os.environ['TOKEN'])