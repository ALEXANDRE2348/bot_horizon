import discord
import json
import os
import re
from discord.ext import commands, tasks
from mcstatus import JavaServer
from datetime import datetime
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Charger les fichiers json
RESSOURCE_PATH = "./ressource/"

with open(f"{RESSOURCE_PATH}config.json", "r") as configFile:
    configData = json.load(configFile)

with open(f"{RESSOURCE_PATH}emoji.json", "r") as emojiFile:
    emojiData = json.load(emojiFile)

# Les configs
MINECRAFT_SERVER = configData["MINECRAFT_SERVER"]
DISPLAY_SERVER = configData["DISPLAY_SERVER"]
DISCORD_CHANNEL_ID = configData["DISCORD_CHANNEL_ID"]
TOKEN = configData["TOKEN"]
EMOJI_LOGO = emojiData["logo"]

# Créer le bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Variable globale pour stocker le dernier message
last_status_message = None

# 📌 Fonction pour vérifier l'état du serveur Minecraft
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

# 📌 Fonction pour créer l'embed d'état du serveur
async def create_status_embed(status):
    if status['online']:
        embed = discord.Embed(
            title=f"{EMOJI_LOGO} État du serveur Minecraft",
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
            title=f"{EMOJI_LOGO} État du serveur Minecraft",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Statut & IP",
            value=f"🔴 Hors ligne  |  `{DISPLAY_SERVER}`",
            inline=False
        )

    return embed

# 📌 Tâche de mise à jour du statut
@tasks.loop(minutes=1)  # Actualisation toutes les 1 minute
async def update_status():
    global last_status_message  # Utilise la variable globale
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

# 📌 Commande pour vérifier manuellement le statut du serveur
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

# 📌 Fonction pour nettoyer le nom du serveur (remplace les espaces et caractères spéciaux)
def clean_server_name(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

# 📌 Fonction pour obtenir le chemin du fichier de config d'un serveur
def get_config_path(guild):
    server_name = guild.name  # Garder le nom du serveur tel quel
    return os.path.join("config", f"{server_name}_{guild.id}.json")

# 📌 Fonction pour charger la configuration d'un serveur
def load_config(guild):
    path = get_config_path(guild)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "server_name": guild.name,
        "server_id": guild.id,
        "protected_users": [],
        "restricted_roles": []
    }

# 📌 Fonction pour sauvegarder la configuration d'un serveur
def save_config(guild, data):
    path = get_config_path(guild)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté !')
    await bot.change_presence(activity=discord.Game(name="play.horizon-relax.org"))

    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if channel:
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                await message.delete()

    update_status.start()

# 📌 Événement pour détecter les mentions de membres protégés
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    config = load_config(message.guild)
    protected_users = config.get("protected_users", [])
    restricted_roles = config.get("restricted_roles", [])

    # Vérifie si l'auteur a un rôle restreint
    if any(role.id in restricted_roles for role in message.author.roles):
        for user_id in protected_users:
            if f"<@{user_id}>" in message.content:
                await message.channel.send(f"⚠️ {message.author.mention}, tu n'as pas le droit de mentionner ce membre !")
                break

    await bot.process_commands(message)

# 📌 Commande pour ajouter un membre protégé
@bot.command()
@commands.has_permissions(administrator=True)
async def add_protected(ctx, member: discord.Member):
    config = load_config(ctx.guild)

    if member.id not in config["protected_users"]:
        config["protected_users"].append(member.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ {member.mention} est maintenant protégé contre les mentions.")
    else:
        await ctx.send(f"⚠️ {member.mention} est déjà protégé.")

# 📌 Commande pour retirer un membre protégé
@bot.command()
@commands.has_permissions(administrator=True)
async def remove_protected(ctx, member: discord.Member):
    config = load_config(ctx.guild)

    if member.id in config["protected_users"]:
        config["protected_users"].remove(member.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ {member.mention} peut maintenant être mentionné.")
    else:
        await ctx.send(f"⚠️ {member.mention} n'est pas dans la liste des protégés.")

# 📌 Commande pour ajouter un rôle interdit de mentionner les protégés
@bot.command()
@commands.has_permissions(administrator=True)
async def add_restricted_role(ctx, role: discord.Role):
    config = load_config(ctx.guild)

    if role.id not in config["restricted_roles"]:
        config["restricted_roles"].append(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle `{role.name}` ne peut plus mentionner les membres protégés.")
    else:
        await ctx.send(f"⚠️ Le rôle `{role.name}` est déjà restreint.")

# 📌 Commande pour retirer un rôle interdit
@bot.command()
@commands.has_permissions(administrator=True)
async def remove_restricted_role(ctx, role: discord.Role):
    config = load_config(ctx.guild)

    if role.id in config["restricted_roles"]:
        config["restricted_roles"].remove(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle `{role.name}` peut maintenant mentionner les membres protégés.")
    else:
        await ctx.send(f"⚠️ Le rôle `{role.name}` n'était pas restreint.")

# 📌 Commande pour afficher la liste des protégés et des rôles interdits
@bot.command()
async def list_protected(ctx):
    config = load_config(ctx.guild)

    protected_users = config.get("protected_users", [])
    restricted_roles = config.get("restricted_roles", [])

    users_list = "\n".join([f"<@{uid}>" for uid in protected_users]) if protected_users else "Aucun"
    roles_list = "\n".join([f"<@&{rid}>" for rid in restricted_roles]) if restricted_roles else "Aucun"

    embed = discord.Embed(title="🔒 Liste des protections", color=discord.Color.blue())
    embed.add_field(name="Membres protégés", value=users_list, inline=False)
    embed.add_field(name="Rôles restreints", value=roles_list, inline=False)

    await ctx.send(embed=embed)

# Lancer le bot
bot.run(TOKEN)