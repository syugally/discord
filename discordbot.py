# -- coding: utf-8 --
import discord
from discord.ext import commands
import yt_dlp

ydl_opts = {
    'cookiesfrombrowser': ('chrome',),  # 使用するブラウザを指定（例: Chrome）
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download(['https://www.youtube.com/watch?v=IKBO7PaIKl4'])



import asyncio
import os
from dotenv import load_dotenv
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import time

# Intents の設定（discord.py v2.0以降では message_content などが必要な場合があります）
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot の接頭辞を '/' として初期化（プレフィックスコマンド用）
bot = commands.Bot(command_prefix='/', intents=intents)

# 各ギルドごとに曲のキュー（リスト）を保持する辞書
queues = {}


# yt_dlp の設定
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # IPv4 を強制]


}
ffmpeg_options = {
    'options': '-vn',
    'executable': r'C:\ffmpeg\bin\ffmpeg.exe'  # FFmpeg の絶対パスを記入
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# YouTube から音声を取得し、FFmpeg で再生するためのクラス
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# 再生終了時にキューから次の曲を再生するヘルパー関数
async def play_next(guild: discord.Guild):
    voice_client = guild.voice_client
    if not voice_client:
        return

    # キューに次の曲があれば再生
    if guild.id in queues and len(queues[guild.id]) > 0:
        next_player = queues[guild.id].pop(0)
        voice_client.play(
            next_player,
            after=lambda e: bot.loop.create_task(play_next(guild))
        )
        print(f"再生中: {next_player.title}")

# 起動時にスラッシュコマンドを同期
@bot.event
async def on_ready():
    await bot.tree.sync()  # アプリケーションコマンドを同期
    print('ログインしました')

# =============================
# 以下、従来のテキストコマンド（プレフィックスコマンド）
# =============================

@bot.command(name='join')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"{channel} に接続しました。")
    else:
        await ctx.send("あなたはボイスチャンネルに参加していません。")

@bot.command(name='play')
async def play(ctx, url: str):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            return await ctx.send("あなたはボイスチャンネルに参加していません。")
    voice_client = ctx.voice_client

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, stream=True)
        except Exception as e:
            return await ctx.send(f"エラーが発生しました: {e}")

    if voice_client.is_playing():
        queues.setdefault(ctx.guild.id, []).append(player)
        await ctx.send(f"**{player.title}** をキューに追加しました。")
    else:
        voice_client.play(
            player,
            after=lambda e: bot.loop.create_task(play_next(ctx.guild))
        )
        await ctx.send(f"再生中: **{player.title}**")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # 停止すると after コールバックで play_next が呼ばれる
        await ctx.send("曲をスキップしました。")
    else:
        await ctx.send("再生中の曲がありません。")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    q_list = queues.get(ctx.guild.id, [])
    if len(q_list) == 0:
        await ctx.send("キューに曲はありません。")
    else:
        msg = "\n".join([f"{i+1}. {item.title}" for i, item in enumerate(q_list)])
        await ctx.send(f"キュー一覧:\n{msg}")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues.pop(ctx.guild.id, None)  # キューをクリア
        await ctx.send("ボイスチャンネルから切断しました。")
    else:
        await ctx.send("Botはボイスチャンネルに参加していません。")

@bot.command(name='neko')
async def neko(ctx):
    await ctx.send('にゃーん')

# =============================
# 以下、スラッシュコマンド（/を入力した際に候補に表示されるもの）
# =============================

@bot.tree.command(name="join", description="ボイスチャンネルに接続します")
async def slash_join(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        await channel.connect()
        await interaction.response.send_message(f"{channel} に接続しました。")
    else:
        await interaction.response.send_message("あなたはボイスチャンネルに参加していません。")

@bot.tree.command(name="play", description="Play a song")
async def slash_play(interaction: discord.Interaction, url: str):
    # 応答を遅延
    await interaction.response.defer()

    try:
        # 音楽を再生する処理
        # 例: yt-dlp を使って音声を取得
        audio_url = await download_audio(url)
        await interaction.followup.send(f"Now playing: {url}")
    except Exception as e:
        # エラーが発生した場合の処理
        await interaction.followup.send(f"An error occurred: {e}")

    if not interaction.guild:
        await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。")
        return

    voice_client = interaction.guild.voice_client
    if not voice_client:
        if interaction.user.voice:
            await interaction.user.voice.channel.connect()
            voice_client = interaction.guild.voice_client
        else:
            await interaction.response.send_message("あなたはボイスチャンネルに参加していません。")
            return

    await interaction.response.defer()
    try:
        player = await YTDLSource.from_url(url, stream=True)
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {e}")
        return

    if voice_client.is_playing():
        queues.setdefault(interaction.guild.id, []).append(player)
        await interaction.followup.send(f"{player.title} をキューに追加しました。")
    else:
        voice_client.play(
            player,
            after=lambda e: bot.loop.create_task(play_next(interaction.guild))
        )
        await interaction.followup.send(f"再生中: {player.title}")

@bot.tree.command(name="skip", description="現在の曲をスキップします")
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("曲をスキップしました。")
    else:
        await interaction.response.send_message("再生中の曲がありません。")

@bot.tree.command(name="queue", description="現在のキュー一覧を表示します")
async def slash_queue(interaction: discord.Interaction):
    q_list = queues.get(interaction.guild.id, [])
    if len(q_list) == 0:
        await interaction.response.send_message("キューに曲はありません。")
    else:
        msg = "\n".join([f"{i+1}. {item.title}" for i, item in enumerate(q_list)])
        await interaction.response.send_message(f"キュー一覧:\n{msg}")

@bot.tree.command(name="leave", description="Botをボイスチャンネルから切断します")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        queues.pop(interaction.guild.id, None)
        await interaction.response.send_message("ボイスチャンネルから切断しました。")
    else:
        await interaction.response.send_message("Botはボイスチャンネルに参加していません。")

@bot.tree.command(name="neko", description="にゃーんと返答します")
async def slash_neko(interaction: discord.Interaction):
    await interaction.response.send_message("にゃーん")

# =============================
# 自動再起動機能（手動再起動コマンド + watchdog による自動監視）
# =============================

def restart_bot():
    """Bot を再起動する関数"""
    os.execv(sys.executable, ['python'] + sys.argv)

@bot.command(name="restart", help="Bot を再起動します")
async def restart(ctx):
    await ctx.send("Bot を再起動します...")
    restart_bot()

class RestartHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print("コードが変更されました。Bot を再起動します...")
            restart_bot()

def watch_changes():
    event_handler = RestartHandler()
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# 監視スレッドを開始（ファイル変更を検知して自動再起動）
thread = threading.Thread(target=watch_changes, daemon=True)
thread.start()

# .env ファイルを読み込む
load_dotenv()

# 環境変数からトークンを取得
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot を起動
bot.run(TOKEN)
