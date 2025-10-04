import discord 
from discord.ext import commands
import os
from dotenv import load_dotenv

# Configuration des intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté et prêt!')
    print(f'ID: {bot.user.id}')
    print('-------------------')

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name='arrivage')
    if channel:
        await channel.send(f'Bienvenue sur le serveur, {member.mention}! 👋')
    else:
        print('Salon "arrivage" non trouvé.')

    role = discord.utils.get(member.guild.roles, name='LES BG')
    try:
        if role:
            await member.add_roles(role)
            print(f'Rôle "LES BG" ajouté à {member.name}')
        else:
            print('Rôle "LES BG" non trouvé.')
    except Exception as e:
        print(f"Erreur en ajoutant le rôle: {e}")       

@bot.command(name='info')
async def info(ctx):
    """Afficher les infos du serveur"""
    guild = ctx.guild
    embed = discord.Embed(
        title=f"📊 Informations sur {guild.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="👑 Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="👥 Membres", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    await ctx.send(embed=embed)
if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ TOKEN non trouvé! Vérifie ton fichier .env")