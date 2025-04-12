import discord
import json
import os
import re
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
from mcstatus import JavaServer
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Chargement des configurations
load_dotenv()

# Chemins des fichiers de configuration
RESSOURCE_PATH = "./ressource/"

# Chargement des fichiers JSON
with open(f"{RESSOURCE_PATH}config.json", "r") as configFile:
    configData = json.load(configFile)

with open(f"{RESSOURCE_PATH}emoji.json", "r") as emojiFile:
    emojiData = json.load(emojiFile)

# Configuration principale
MINECRAFT_SERVER = configData["MINECRAFT_SERVER"]
DISPLAY_SERVER = configData["DISPLAY_SERVER"]
DISCORD_CHANNEL_ID = configData["DISCORD_CHANNEL_ID"]
TOKEN = configData["TOKEN"]
EMOJI_LOGO = emojiData["logo"]

# Configuration du système de suggestions
SUGGESTIONS_CHANNEL_ID = configData["SUGGESTIONS_CHANNEL_ID"]  # Salon des suggestions
PROMPT_CHANNEL_ID = configData["PROMPT_CHANNEL_ID"]  # Salon du bouton d'envoi
NOTIFICATION_ROLE_ID = configData["NOTIFICATION_ROLE_ID"]  # Rôle à mentionner pour nouvelles suggestions
REVIEW_ROLE_ID = configData["REVIEW_ROLE_ID"]  # Rôle à mentionner pour les décisions
REVIEW_CHANNEL_ID = configData["REVIEW_CHANNEL_ID"]  # Salon où les résultats sont annoncés

ACCEPT_THRESHOLD = 10
REJECT_THRESHOLD = 5

# Initialisation du bot
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Variables globales
last_status_message = None
pending_suggestions = {}


################################################################
### PARTIE 1 : SYSTÈME DE SUGGESTIONS
################################################################

class SuggestionModal(Modal, title='Nouvelle suggestion'):
    suggestion = TextInput(
        label='Votre suggestion',
        style=discord.TextStyle.long,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = bot.get_channel(SUGGESTIONS_CHANNEL_ID)
        role = interaction.guild.get_role(NOTIFICATION_ROLE_ID)

        embed = discord.Embed(
            title="💡 Nouvelle suggestion",
            description=self.suggestion.value,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
        embed.set_footer(text="Votez avec 👍/👎 - Décision dans 3 jours")

        message = await channel.send(
            content=f"{role.mention} Nouvelle suggestion!",
            embed=embed
        )
        await message.add_reaction("👍")
        await message.add_reaction("👎")

        pending_suggestions[message.id] = {
            "author_id": interaction.user.id,
            "created_at": datetime.now(),
            "status": "En vote"
        }

        await interaction.response.send_message("Suggestion envoyée!", ephemeral=True)


class SuggestionView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Faire une suggestion", style=discord.ButtonStyle.green, custom_id="suggestion_button")
    async def suggestion_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SuggestionModal())


async def setup_suggestion_prompt():
    channel = bot.get_channel(PROMPT_CHANNEL_ID)
    view = SuggestionView()

    embed = discord.Embed(
        title="💡 Système de suggestions",
        description="Cliquez sur le bouton ci-dessous pour proposer une amélioration!",
        color=discord.Color.gold()
    )

    await channel.purge(limit=5)
    await channel.send(embed=embed, view=view)


@tasks.loop(hours=1)
async def check_expired_suggestions():
    now = datetime.now()
    to_remove = []

    for message_id, suggestion in list(pending_suggestions.items()):
        if now >= suggestion["created_at"] + timedelta(days=3):
            await evaluate_suggestion(message_id)
            to_remove.append(message_id)

    for msg_id in to_remove:
        pending_suggestions.pop(msg_id, None)


async def evaluate_suggestion(message_id):
    suggestion = pending_suggestions.get(message_id)
    if not suggestion: return

    try:
        channel = bot.get_channel(SUGGESTIONS_CHANNEL_ID)
        message = await channel.fetch_message(message_id)

        upvotes = sum(r.count - 1 for r in message.reactions if str(r.emoji) == "👍")
        downvotes = sum(r.count - 1 for r in message.reactions if str(r.emoji) == "👎")

        if upvotes >= ACCEPT_THRESHOLD and upvotes > downvotes:
            new_status, color = "✅ Acceptée", discord.Color.green()
        elif downvotes >= REJECT_THRESHOLD and downvotes > upvotes:
            new_status, color = "❌ Rejetée", discord.Color.red()
        else:
            new_status, color = "🤷 Non décidée", discord.Color.orange()

        embed = message.embeds[0]
        embed.color = color
        embed.add_field(name="Statut", value=new_status, inline=False)
        embed.add_field(name="Votes", value=f"👍 {upvotes} | 👎 {downvotes}", inline=False)

        await message.edit(embed=embed)
        await message.clear_reactions()

        review_channel = bot.get_channel(REVIEW_CHANNEL_ID)
        role = message.guild.get_role(REVIEW_ROLE_ID)
        await review_channel.send(
            f"{role.mention} Décision prise:\n"
            f"Auteur: <@{suggestion['author_id']}>\n"
            f"Résultat: {new_status}\n"
            f"Lien: {message.jump_url}"
        )
    except:
        pass


################################################################
### PARTIE 2 : MONITORING MINECRAFT
################################################################

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


@tasks.loop(minutes=1)
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


################################################################
### PARTIE 3 : SYSTÈME DE PROTECTION DES MENTIONS
################################################################

def clean_server_name(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def get_config_path(guild):
    return os.path.join("config", f"{guild.name}_{guild.id}.json")


def load_config(guild):
    path = get_config_path(guild)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "server_name": guild.name,
        "server_id": guild.id,
        "protected_users": [],
        "restricted_roles": [],
        "whitelist_roles": []
    }


def save_config(guild, data):
    path = get_config_path(guild)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    config = load_config(message.guild)
    protected_users = config.get("protected_users", [])
    restricted_roles = config.get("restricted_roles", [])
    whitelist_roles = config.get("whitelist_roles", [])

    if any(role.id in whitelist_roles for role in message.author.roles):
        await bot.process_commands(message)
        return

    if any(role.id in restricted_roles for role in message.author.roles):
        for user_id in protected_users:
            if f"<@{user_id}>" in message.content:
                await message.channel.send(
                    f"⚠️ {message.author.mention}, tu n'as pas le droit de mentionner ce membre !")
                await message.delete()
                break

    await bot.process_commands(message)


################################################################
### COMMANDES DE PROTECTION
################################################################

@bot.command()
@commands.has_permissions(administrator=True)
async def add_protected(ctx, member: discord.Member):
    """Ajoute un membre protégé"""
    config = load_config(ctx.guild)
    if member.id not in config["protected_users"]:
        config["protected_users"].append(member.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ {member.mention} est maintenant protégé contre les mentions.")
    else:
        await ctx.send(f"⚠️ {member.mention} est déjà protégé.")


@bot.command()
@commands.has_permissions(administrator=True)
async def remove_protected(ctx, member: discord.Member):
    """Retire un membre protégé"""
    config = load_config(ctx.guild)
    if member.id in config["protected_users"]:
        config["protected_users"].remove(member.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ {member.mention} n'est plus protégé.")
    else:
        await ctx.send(f"⚠️ {member.mention} n'était pas protégé.")


@bot.command()
@commands.has_permissions(administrator=True)
async def add_restricted_role(ctx, role: discord.Role):
    """Ajoute un rôle restreint"""
    config = load_config(ctx.guild)
    if role.id not in config["restricted_roles"]:
        config["restricted_roles"].append(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle {role.mention} ne peut plus mentionner les protégés.")
    else:
        await ctx.send(f"⚠️ Le rôle {role.mention} est déjà restreint.")


@bot.command()
@commands.has_permissions(administrator=True)
async def remove_restricted_role(ctx, role: discord.Role):
    """Retire un rôle restreint"""
    config = load_config(ctx.guild)
    if role.id in config["restricted_roles"]:
        config["restricted_roles"].remove(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle {role.mention} peut maintenant mentionner les protégés.")
    else:
        await ctx.send(f"⚠️ Le rôle {role.mention} n'était pas restreint.")


@bot.command()
@commands.has_permissions(administrator=True)
async def add_whitelist_role(ctx, role: discord.Role):
    """Ajoute un rôle whitelist"""
    config = load_config(ctx.guild)
    if role.id not in config["whitelist_roles"]:
        config["whitelist_roles"].append(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle {role.mention} peut maintenant mentionner tous les membres.")
    else:
        await ctx.send(f"⚠️ Le rôle {role.mention} est déjà whitelist.")


@bot.command()
@commands.has_permissions(administrator=True)
async def remove_whitelist_role(ctx, role: discord.Role):
    """Retire un rôle whitelist"""
    config = load_config(ctx.guild)
    if role.id in config["whitelist_roles"]:
        config["whitelist_roles"].remove(role.id)
        save_config(ctx.guild, config)
        await ctx.send(f"✅ Le rôle {role.mention} a été retiré de la whitelist.")
    else:
        await ctx.send(f"⚠️ Le rôle {role.mention} n'était pas whitelist.")


@bot.command()
async def list_protected(ctx):
    """Liste les protections"""
    config = load_config(ctx.guild)

    protected = "\n".join([f"<@{uid}>" for uid in config["protected_users"]]) or "Aucun"
    restricted = "\n".join([f"<@&{rid}>" for rid in config["restricted_roles"]]) or "Aucun"
    whitelist = "\n".join([f"<@&{rid}>" for rid in config["whitelist_roles"]]) or "Aucun"

    embed = discord.Embed(title="🔒 Liste des protections", color=discord.Color.blue())
    embed.add_field(name="Membres protégés", value=protected, inline=False)
    embed.add_field(name="Rôles restreints", value=restricted, inline=False)
    embed.add_field(name="Rôles whitelist", value=whitelist, inline=False)

    await ctx.send(embed=embed)


################################################################
### COMMANDES DIVERSES
################################################################

@bot.command()
async def status(ctx):
    """Affiche le statut du serveur Minecraft"""
    status = await check_minecraft_server()
    embed = await create_status_embed(status)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def setup_suggestions(ctx):
    """Configure le système de suggestions"""
    await setup_suggestion_prompt()
    await ctx.send("✅ Système de suggestions configuré!", delete_after=5)


@bot.command()
async def aide(ctx):
    """Affiche l'aide complète avec description de chaque commande"""
    embed = discord.Embed(
        title="📚 Aide complète - Liste des commandes disponibles",
        description="Voici toutes les commandes disponibles sur ce serveur :",
        color=discord.Color.blue()
    )

    # Section Minecraft
    embed.add_field(
        name="🟢 **Commandes Minecraft**",
        value=(
            "`!status` - Affiche le statut actuel du serveur Minecraft avec la liste des joueurs connectés\n"
            "`!setup_minecraft` - Configure le système de monitoring (Admin seulement)"
        ),
        inline=False
    )

    # Section Suggestions
    embed.add_field(
        name="💡 **Commandes Suggestions**",
        value=(
            "`!setup_suggestions` - Configure le système de suggestions (Admin seulement)\n"
            "`!force_eval [id_message]` - Force l'évaluation d'une suggestion (Admin seulement)"
        ),
        inline=False
    )

    # Section Protection
    embed.add_field(
        name="🔒 **Commandes Protection (Admin seulement)**",
        value=(
            "`!add_protected @membre` - Ajoute un membre à la liste protégée (ne peut pas être mentionné)\n"
            "`!remove_protected @membre` - Retire un membre de la liste protégée\n"
            "`!add_restricted_role @rôle` - Ajoute un rôle qui ne peut pas mentionner les membres protégés\n"
            "`!remove_restricted_role @rôle` - Retire un rôle des restrictions\n"
            "`!add_whitelist_role @rôle` - Ajoute un rôle qui peut mentionner tous les membres (même protégés)\n"
            "`!remove_whitelist_role @rôle` - Retire un rôle de la whitelist\n"
            "`!list_protected` - Affiche la liste complète des protections"
        ),
        inline=False
    )

    # Section Utilitaires
    embed.add_field(
        name="🔧 **Commandes Utilitaires**",
        value=(
            "`!aide` - Affiche ce message d'aide\n"
            "`!ping` - Vérifie si le bot est en ligne"
        ),
        inline=False
    )

    # Note sur les permissions
    embed.set_footer(
        text="ℹ️ Les commandes marquées '(Admin seulement)' nécessitent les permissions d'administrateur"
    )

    await ctx.send(embed=embed)


################################################################
### ÉVÉNEMENTS
################################################################

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté !')
    await bot.change_presence(activity=discord.Game(name="play.horizon-relax.org"))

    # Nettoyage des anciens messages
    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if channel:
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                await message.delete()

    # Lancement des tâches
    update_status.start()
    bot.add_view(SuggestionView())
    await setup_suggestion_prompt()
    check_expired_suggestions.start()


# Lancement du bot
bot.run(TOKEN)