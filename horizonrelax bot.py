import discord
from discord.ext import commands, tasks
from discord import ui
from mcstatus import JavaServer
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

# Configuration du serveur Minecraft et du bot Discord
MINECRAFT_SERVER = "play.horizon-relax.org:25567"
DISCORD_CHANNEL_ID = "1330452744946843670"
TOKEN = "MTMyOTA0NDA5MzkwMDI5MjExNg.GlYvaQ.agychPLt1lXQ049e84Azl7DTCg5ELUPsiVDV4Q"  # Remplacez par votre vrai token

# Configuration des canaux pour les tickets
TICKET_PANEL_CHANNEL_ID = 1304101527622778901
TICKET_CATEGORY_ID = 1313861176735563807
RATING_CHANNEL_ID = 1333175722940039189

# Configuration des intents du bot
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Variable globale pour stocker le dernier message de statut
last_status_message = None

async def check_minecraft_server():
    """Vérifie le statut du serveur Minecraft"""
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
    """Crée un embed Discord avec le statut du serveur"""
    if status['online']:
        embed = discord.Embed(
            title="État du serveur Minecraft",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Statut & IP",
            value=f"🟢 En ligne  |  `{MINECRAFT_SERVER}`",
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
            if status['player_count'] > 0:
                embed.add_field(
                    name="📋 Liste des joueurs connectés",
                    value="*Impossible d'obtenir la liste des joueurs*",
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
            value=f"🔴 Hors ligne  |  `{MINECRAFT_SERVER}`",
            inline=False
        )
    
    return embed

@tasks.loop(minutes=1)  # Actualisation toutes les 1 minute
async def update_status():
    """Mise à jour automatique du statut du serveur"""
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
    """Événement de démarrage du bot"""
    print(f'{bot.user} est connecté !')

    # Nettoyage des anciens messages
    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if channel:
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                await message.delete()
    
    # Démarrage de la mise à jour du statut
    update_status.start()

    # Configuration du panneau de tickets
    ticket_channel = bot.get_channel(TICKET_PANEL_CHANNEL_ID)
    
    # Suppression des anciens messages
    async for message in ticket_channel.history(limit=100):
        await message.delete()
    
    embed = discord.Embed(
        title="Système de Tickets",
        description="Cliquez sur le bouton ci-dessous pour créer un ticket de support.",
        color=discord.Color.blue()
    )
    
    await ticket_channel.send(embed=embed, view=TicketView())

@bot.command()
async def status(ctx):
    """Commande manuelle pour vérifier le statut du serveur"""
    status = await check_minecraft_server()
    
    if status['online']:
        message = f"🟢 En ligne  |  `{MINECRAFT_SERVER}`\n"
        message += f"**{status['player_count']}**/{status['max_players']} joueurs\n"
        if status['players']:
            message += "\n📋 **Joueurs connectés:**\n"
            message += "\n".join([f"👤 {player}" for player in status['players']])
        elif status['player_count'] > 0:
            message += "\n*Impossible d'obtenir la liste des joueurs*"
        else:
            message += "\n*Aucun joueur connecté*"
        await ctx.send(message)
    else:
        await ctx.send(f"🔴 Hors ligne  |  `{MINECRAFT_SERVER}`")

class RatingModal(ui.Modal, title="Notation du support"):
    """Modal pour évaluer le support après la fermeture d'un ticket"""
    rating = ui.TextInput(
        label="Note sur 5 étoiles (1-5)",
        placeholder="Entrez un nombre entre 1 et 5",
        min_length=1,
        max_length=1,
        required=True
    )
    comment = ui.TextInput(
        label="Commentaire (optionnel)",
        style=discord.TextStyle.paragraph,
        placeholder="Votre avis sur le support reçu",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Gestion de la soumission du formulaire de notation"""
        try:
            if not self.rating.value.isdigit():
                await interaction.response.send_message("Veuillez entrer un nombre valide entre 1 et 5.", ephemeral=True)
                return

            rating_value = int(self.rating.value)
            
            if rating_value < 1 or rating_value > 5:
                await interaction.response.send_message("La note doit être comprise entre 1 et 5.", ephemeral=True)
                return

        except Exception as e:
            await interaction.response.send_message("Une erreur est survenue lors de la validation de votre note.", ephemeral=True)
            return

        # Envoi de la note dans le salon dédié
        rating_channel = interaction.guild.get_channel(RATING_CHANNEL_ID)
        stars = "⭐" * rating_value
        
        embed = discord.Embed(
            title="Nouvelle évaluation de ticket",
            color=discord.Color.gold()
        )
        embed.add_field(name="Note", value=f"{stars} ({rating_value}/5)", inline=False)
        if self.comment.value:
            embed.add_field(name="Commentaire", value=self.comment.value, inline=False)
        embed.add_field(name="Ticket", value=f"#{interaction.channel.name}", inline=False)
        embed.set_footer(text=f"Évalué par {interaction.user.name}")
        
        await rating_channel.send(embed=embed)
        await interaction.response.send_message("Merci pour votre évaluation!", ephemeral=True)
        await interaction.channel.delete()

class TicketView(ui.View):
    """Vue pour créer un nouveau ticket"""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Créer un ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Création d'un nouveau ticket"""
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        existing_ticket = discord.utils.get(category.channels, name=f"ticket-{interaction.user.name.lower()}")
        
        if existing_ticket:
            await interaction.response.send_message("Vous avez déjà un ticket ouvert!", ephemeral=True)
            return

        # Créer le nouveau ticket
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await channel.send("<@&1305998594620260432>")

        embed = discord.Embed(
            title="Ticket de Support",
            description="🏠| Envoyer sa candidature Staff / developer \n 📞| Poser une question sur le serveur ou sur d'autres sujets ou demande pour faire un don",
            color=discord.Color.blue()
        )

        close_view = CloseTicketView()
        await channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"Votre ticket a été créé: {channel.mention}", ephemeral=True)

class CloseTicketView(ui.View):
    """Vue pour fermer un ticket"""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Fermer le ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Fermeture du ticket avec modal de notation"""
        # Vérifier si l'utilisateur est bien celui qui a créé le ticket ou un administrateur
        ticket_creator = interaction.channel.name.split('-')[1].capitalize()
        if interaction.user.name != ticket_creator and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Seul le créateur du ticket ou un administrateur peut le fermer.", ephemeral=True)
            return
        
        # Ouvrir le modal pour l'évaluation du support
        modal = RatingModal()
        await interaction.response.send_modal(modal)

# Lancer le bot
bot.run(TOKEN)