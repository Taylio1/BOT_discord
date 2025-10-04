import discord 
from discord.ext import commands
import os
from dotenv import load_dotenv
import json

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
    embed.add_field(name="Langue", value="Français", inline=True)
    embed.add_field(name="Rôles", value=" ".join([role.name for role in guild.roles if role != guild.default_role]), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='role')
async def role(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    
    if not role:
        await ctx.send(f"❌ Rôle '{role_name}' introuvable.")
        return
    
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"✅ Rôle retiré à {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"✅ Rôle donné à {member.mention}")

@bot.event
async def on_message(message):
    if not message.author.bot:
        user_id = str(message.author.id)
        if user_id not in user_data:
            user_data[user_id] = {"xp": 0, "level": 1}
        
        user_data[user_id]["xp"] += 10
        xp_needed = user_data[user_id]["level"] * 100
        if user_data[user_id]["xp"] >= xp_needed:
            user_data[user_id]["level"] += 1
            await message.channel.send(f"🎉 {message.author.mention} a atteint le niveau {user_data[user_id]['level']}!")
    
    await bot.process_commands(message)

user_data = {}

@bot.command(name='level')
async def level(ctx, member: discord.Member = None):
    """Voir son niveau ou celui d'un autre"""
    if not member:
        member = ctx.author
    
    user_id = str(member.id)
    if user_id in user_data:
        data = user_data[user_id]
        await ctx.send(f"📈 **{member.name}** - Niveau: {data['level']} | XP: {data['xp']}")
    else:
        await ctx.send(f"{member.name} n'a pas encore d'XP!")

if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ TOKEN non trouvé! Vérifie ton fichier .env")