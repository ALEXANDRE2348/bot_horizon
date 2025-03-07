import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
MINECRAFT_SERVER = "54.37.80.17:25566"  # IP réelle pour la connexion
DISPLAY_SERVER = "play.horizon-relax.org"  # IP affichée dans Discord
DISCORD_CHANNEL_ID = "1330452744946843670"  # Remplacez par l'ID de votre salon
TOKEN = "MTM0NTcwNDk5ODEyNTk2MTMwOQ.G2uloy.cT5laBovHq39At6jOKVOm8LYG1W7HJUqG09o2s"  # Remplacez par votre token Discord

# Créer le bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Variable globale pour stocker le dernier message
last_status_message = None


async def check_minecraft_server():
    try:
        server = JavaServer.lookup(MINECRAFT_SERVER)
        status = await server.async_status()
        players = []
        if status.players.sample:
            players = [player.name for player in status.players.sample]
        return {
            'online': True,
            'players': players,
            'player_count': status.players.online,
            'max_players': status.players.max
        }
    except:
        return {
            'online': False,
            'players': [],
            'player_count': 0,
            'max_players': 0
        }


async def create_status_embed(status):
    if status['online']:
        embed = discord.Embed(
            title="<:logo:1347624430603341834> État du serveur Minecraft",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Statut & IP",
            value=f"🟢 En ligne  |  `{DISPLAY_SERVER}`",
            inline=False
        )
        embed.add_field(
            name="Nombre de joueurs",
            value=f"**{status['player_count']}** / {status['max_players']}",
            inline=False
        )

        if status['players']:
            players_list = "\n".join([f"👤 {player}" for player in status['players']])
            embed.add_field(
                name="📋 Liste des joueurs connectés",
                value=players_list,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Liste des joueurs connectés",
                value="*Aucun joueur connecté*",
                inline=False
            )
    else:
        embed = discord.Embed(
            title="État du serveur Minecraft",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Statut & IP",
            value=f"🔴 Hors ligne  |  `{DISPLAY_SERVER}`",
            inline=False
        )

    return embed


@tasks.loop(minutes=1)  # Actualisation toutes les 1 minute
async def update_status():
    global last_status_message
    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if not channel:
        return

    status = await check_minecraft_server()
    embed = await create_status_embed(status)

    try:
        if last_status_message:
            await last_status_message.edit(embed=embed)
        else:
            last_status_message = await channel.send(embed=embed)
    except discord.NotFound:
        last_status_message = await channel.send(embed=embed)


@bot.event
async def on_ready():
    print(f'{bot.user} est connecté !')

    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if channel:
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                await message.delete()

    update_status.start()


@bot.command()
async def status(ctx):
    """Commande pour vérifier manuellement le statut du serveur"""
    status = await check_minecraft_server()

    if status['online']:
        message = f"🟢 En ligne  |  `{DISPLAY_SERVER}`\n"
        message += f"**{status['player_count']}**/{status['max_players']} joueurs\n"
        if status['players']:
            message += "\n📋 **Joueurs connectés:**\n"
            message += "\n".join([f"👤 {player}" for player in status['players']])
        else:
            message += "\n*Aucun joueur connecté*"
        await ctx.send(message)
    else:
        await ctx.send(f"🔴 Hors ligne  |  `{DISPLAY_SERVER}`")


# Lancer le bot
bot.run(TOKEN)