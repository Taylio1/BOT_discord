import asyncio
import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
user_data = {}


@bot.event
async def on_ready():
    print(f'🚀 {bot.user} est en ligne! Ready to go!')
    print('-------------------')


@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name='arrivage')
    if channel:
        await channel.send(f'Yooo {member.mention}, bienvenue dans la team! 🔥')
    
    role = discord.utils.get(member.guild.roles, name='LES BG')
    if role:
        await member.add_roles(role)


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
            await message.channel.send(f"🚀 GG {message.author.mention}! Level {user_data[user_id]['level']} 🎯")
    
    await bot.process_commands(message)


@bot.command(name='info')
async def info(ctx):
    guild = ctx.guild
    await ctx.send(f"""
🏠 **{guild.name}**
👑 Boss: {guild.owner.mention}
👥 On est {guild.member_count} bg ici!
📅 Créé le {guild.created_at.strftime("%d/%m/%Y")}
🎮 Serveur perso pour traîner entre potes
    """)


@bot.command(name='level')
async def level(ctx, member: discord.Member = None):
    if not member:
        member = ctx.author
    
    user_id = str(member.id)
    if user_id in user_data:
        data = user_data[user_id]
        await ctx.send(f"🎮 **{member.name}** - Level {data['level']} | {data['xp']} XP")
    else:
        await ctx.send(f"😴 {member.name} n'a pas encore parlé ici!")


@bot.command(name='role')
async def role(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    
    if not role:
        await ctx.send(f"🤷‍♂️ J'ai pas trouvé le rôle '{role_name}'")
        return
    
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"🗑️ Rôle **{role.name}** retiré à {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"🎉 Rôle **{role.name}** donné à {member.mention}!")


@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        await ctx.send("😂 Tu veux te kick toi-même? Malin!")
        return
    
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.name} a pris la porte!")
        if reason:
            await ctx.send(f"Raison: {reason}")
    except:
        await ctx.send("😅 J'ai pas pu le virer, désolé!")


@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        await ctx.send("🙃 Tu veux te ban toi-même? Bizarre...")
        return
    
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.name} a été banni!")
        if reason:
            await ctx.send(f"Raison: {reason}")
    except:
        await ctx.send("😬 Impossible de le ban!")


@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_name):
    try:
        if '#' not in member_name:
            await ctx.send("🤔 Écris comme ça: `!unban nom#1234`")
            return
        
        member_name_part, member_discriminator = member_name.split('#')
        
        async for ban_entry in ctx.guild.bans():
            user = ban_entry.user
            if user.name == member_name_part and user.discriminator == member_discriminator:
                await ctx.guild.unban(user)
                await ctx.send(f"🎉 {user.name} est de retour!")
                return
        
        await ctx.send(f"🤷‍♂️ J'ai pas trouvé {member_name} dans les bannis")
    except:
        await ctx.send("😵 Une erreur bizarre s'est produite...")


@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    if amount > 50:
        await ctx.send("🤔 Max 50 messages!")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 Hop! {len(deleted)-1} messages supprimés", delete_after=3)
    except:
        await ctx.send("😵 J'ai foiré, désolé!")


@bot.command(name='mute')
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 300):
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te muter toi-même!")
        return

    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)

    try:
        await member.add_roles(mute_role)
        embed = discord.Embed(
            title="� Membre muté",
            description=f"{member.mention} a été muté pendant {duration} secondes",
            color=discord.Color.orange()
        )
        embed.add_field(name="👮 Modérateur", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        
        await asyncio.sleep(duration)
        await member.remove_roles(mute_role)
        
        embed = discord.Embed(
            title="🔊 Membre démuté",
            description=f"{member.mention} peut de nouveau parler",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command(name='banlist')
@commands.has_permissions(ban_members=True)
async def banlist(ctx):
    try:
        bans = []
        async for ban_entry in ctx.guild.bans():
            bans.append(ban_entry)
        
        if not bans:
            await ctx.send("😌 Aucun membre banni.")
            return
        
        ban_list = "\n".join([f"{ban_entry.user.name}#{ban_entry.user.discriminator}" for ban_entry in bans])
        embed = discord.Embed(
            title="📜 Liste des bannis",
            description=ban_list,
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ TOKEN non trouvé! Vérifie ton fichier .env")