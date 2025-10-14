import asyncio
import discord
import os
import asyncpg
from discord.ext import commands
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime, timedelta
load_dotenv()

# Pool de connexions PostgreSQL
db_pool = None

# Initialisation de la base de données PostgreSQL
async def init_db():
    global db_pool
    # Récupère les informations de connexion depuis .env
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if not DATABASE_URL:
        # Si DATABASE_URL n'existe pas, construire depuis les composants
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        db_name = os.getenv('DB_NAME', 'discord_bot')
        db_user = os.getenv('DB_USER', 'postgres')
        db_pass = os.getenv('DB_PASSWORD', 'postgres')
        DATABASE_URL = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
    
    # Créer le pool de connexions
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
    
    # Créer la table si elle n'existe pas
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    print('✅ Base de données PostgreSQL connectée!')

# Fonctions pour gérer la base de données
async def get_user_data(user_id, username=None):
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow('SELECT xp, level, username FROM users WHERE user_id = $1', user_id)
        
        if result:
            # Mettre à jour le pseudo s'il a changé
            if username and result['username'] != username:
                await conn.execute('UPDATE users SET username = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2', username, user_id)
            return {"xp": result['xp'], "level": result['level'], "username": result['username']}
        else:
            # Créer un nouveau utilisateur avec son pseudo
            await conn.execute(
                'INSERT INTO users (user_id, username, xp, level) VALUES ($1, $2, 0, 1)',
                user_id, username or "Unknown"
            )
            return {"xp": 0, "level": 1, "username": username or "Unknown"}

async def update_user_data(user_id, xp, level):
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET xp = $1, level = $2, updated_at = CURRENT_TIMESTAMP WHERE user_id = $3',
            xp, level, user_id
        )

async def get_leaderboard(limit=10):
    async with db_pool.acquire() as conn:
        results = await conn.fetch(
            'SELECT user_id, username, xp, level FROM users ORDER BY level DESC, xp DESC LIMIT $1',
            limit
        )
        return results

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  # Nécessaire pour détecter les activités

groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionnaire pour stocker l'historique des conversations
# Format: {user_id: [{"role": "user/assistant", "content": "message"}]}
conversation_history = {}

# Dictionnaire pour tracker les sessions de jeu
# Format: {user_id: {'game': 'nom_jeu', 'start_time': datetime}}
game_sessions = {}

# Dictionnaire pour tracker les statistiques de jeu
# Format: {game_name: {'current_players': [user_ids], 'total_time': timedelta}}
game_stats = {}

@bot.event
async def on_ready():
    await init_db()
    print(f'{bot.user} est en ligne! Ready to go!')
    print(f'Groq API Key: {"Configurée" if groq_client.api_key else "Manquante"}')
    print('-------------------')


@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name='arrivage')
    if channel:
        await channel.send(f'Yooo {member.mention}, bienvenue dans la team!')
    
    role = discord.utils.get(member.guild.roles, name='LES BG')
    if role:
        await member.add_roles(role)


@bot.event
async def on_message(message):
    if not message.author.bot:
        user_id = str(message.author.id)
        username = message.author.name
        data = await get_user_data(user_id, username)
        
        data["xp"] += 10
        xp_needed = data["level"] * 100
        if data["xp"] >= xp_needed:
            data["level"] += 1
            await update_user_data(user_id, data["xp"], data["level"])
            await message.channel.send(f"GG {message.author.mention}! Level {data['level']}")
        else:
            await update_user_data(user_id, data["xp"], data["level"])
    
    await bot.process_commands(message)


@bot.event
async def on_presence_update(before, after):
    """Détecte quand un membre commence ou arrête de jouer à un jeu"""
    if after.bot:
        return
    
    user_id = str(after.id)
    
    # Récupérer l'activité de jeu (si elle existe)
    before_game = None
    after_game = None
    
    # Chercher une activité de type "Playing" (jeu)
    if before.activities:
        for activity in before.activities:
            if activity.type == discord.ActivityType.playing:
                before_game = activity.name
                break
    
    if after.activities:
        for activity in after.activities:
            if activity.type == discord.ActivityType.playing:
                after_game = activity.name
                break
    
    # Si l'utilisateur commence à jouer à un nouveau jeu
    if after_game and after_game != before_game:
        await handle_game_start(after, after_game)
    
    # Si l'utilisateur arrête de jouer
    elif before_game and not after_game:
        await handle_game_stop(after, before_game)
    
    # Si l'utilisateur change de jeu
    elif before_game and after_game and before_game != after_game:
        await handle_game_stop(after, before_game)
        await handle_game_start(after, after_game)


async def handle_game_start(member, game_name):
    """Gère le début d'une session de jeu"""
    user_id = str(member.id)
    game_sessions[user_id] = {
        'game': game_name,
        'start_time': datetime.now()
    }
    if game_name not in game_stats:
        game_stats[game_name] = {
            'current_players': [],
            'total_time': timedelta()
        }
    if user_id not in game_stats[game_name]['current_players']:
        game_stats[game_name]['current_players'].append(user_id)
    player_count = len(game_stats[game_name]['current_players'])
    channel = discord.utils.get(member.guild.text_channels, name='gaming')
    if not channel:
        channel = discord.utils.get(member.guild.text_channels, name='général')
    if not channel:
        channel = member.guild.text_channels[0]
    embed = discord.Embed(
        title="🎮 Session de Jeu Démarrée",
        description=f"{member.mention} joue à **{game_name}** !",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    if player_count > 1:
        other_players = []
        for uid in game_stats[game_name]['current_players']:
            if uid != user_id:
                try:
                    other_member = member.guild.get_member(int(uid))
                    if other_member:
                        other_players.append(other_member.mention)
                except:
                    pass
        
        if other_players:
            others_text = ", ".join(other_players[:3]) 
            if len(other_players) > 3:
                others_text += f" et {len(other_players) - 3} autre(s)"
            embed.add_field(
                name="🔥 Joueurs en ligne",
                value=f"{player_count} personne(s) jouent actuellement :\n{others_text}",
                inline=False
            )
    embed.set_footer(text=f"Lancé à {datetime.now().strftime('%H:%M')}")
    await channel.send(embed=embed)


async def handle_game_stop(member, game_name):
    """Gère la fin d'une session de jeu"""
    user_id = str(member.id)
    if user_id not in game_sessions:
        return
    session = game_sessions[user_id]
    play_duration = datetime.now() - session['start_time']
    if game_name in game_stats:
        game_stats[game_name]['total_time'] += play_duration
        if user_id in game_stats[game_name]['current_players']:
            game_stats[game_name]['current_players'].remove(user_id)
    del game_sessions[user_id]
    if play_duration > timedelta(hours=1):
        channel = discord.utils.get(member.guild.text_channels, name='gaming')
        if channel:
            hours = play_duration.total_seconds() / 3600
            await channel.send(
                f"👋 {member.mention} a fini de jouer à **{game_name}** "
                f"après {hours:.1f}h de jeu ! 🎮"
            )


@bot.command(name='info')
async def info(ctx):
    guild = ctx.guild
    await ctx.send(f"""
**{guild.name}**
Boss: {guild.owner.mention}
On est {guild.member_count} bg ici!
Créé le {guild.created_at.strftime("%d/%m/%Y")}
Serveur perso pour traîner entre potes
    """)


@bot.command(name='level')
async def level(ctx, member: discord.Member = None):
    if not member:
        member = ctx.author
    
    user_id = str(member.id)
    data = await get_user_data(user_id, member.name)
    await ctx.send(f"**{member.name}** - Level {data['level']} | {data['xp']} XP")


@bot.command(name='leaderboard', aliases=['top', 'classement'])
async def leaderboard(ctx, limit: int = 10):
    if limit > 20:
        limit = 20
    
    results = await get_leaderboard(limit)
    
    if not results:
        await ctx.send("Aucun utilisateur enregistré!")
        return
    
    embed = discord.Embed(
        title="🏆 Classement des niveaux",
        color=discord.Color.gold()
    )
    
    leaderboard_text = ""
    for idx, record in enumerate(results, 1):
        try:
            # Utiliser le pseudo stocké dans la DB
            username = record['username'] or "Unknown"
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
            leaderboard_text += f"{medal} {username} - Level {record['level']} | {record['xp']} XP\n"
        except:
            continue
    
    embed.description = leaderboard_text
    await ctx.send(embed=embed)


@bot.command(name='role')
async def role(ctx, member: discord.Member, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    
    if not role:
        await ctx.send(f"J'ai pas trouvé le rôle '{role_name}'")
        return
    
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"Rôle **{role.name}** retiré à {member.mention}")
    else:
        await member.add_roles(role)
        await ctx.send(f"Rôle **{role.name}** donné à {member.mention}!")


@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        await ctx.send("Tu veux te kick toi-même? Malin!")
        return
    
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member.name} a pris la porte!")
        if reason:
            await ctx.send(f"Raison: {reason}")
    except:
        await ctx.send("J'ai pas pu le virer, désolé!")


@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        await ctx.send("Tu veux te ban toi-même? Bizarre...")
        return
    
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member.name} a été banni!")
        if reason:
            await ctx.send(f"Raison: {reason}")
    except:
        await ctx.send("Impossible de le ban!")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_name):
    try:
        if '#' not in member_name:
            await ctx.send("Écris comme ça: `!unban nom#1234`")
            return
        
        member_name_part, member_discriminator = member_name.split('#')
        
        async for ban_entry in ctx.guild.bans():
            user = ban_entry.user
            if user.name == member_name_part and user.discriminator == member_discriminator:
                await ctx.guild.unban(user)
                await ctx.send(f"{user.name} est de retour!")
                return
        
        await ctx.send(f"J'ai pas trouvé {member_name} dans les bannis")
    except:
        await ctx.send("Une erreur bizarre s'est produite...")

@bot.command(name='avatar')
async def avatar(ctx, member: discord.Member = None):
    if not member:
        member = ctx.author
    
    embed = discord.Embed(title=f"Avatar de {member.name}", color=discord.Color.blue())
    embed.set_image(url=member.avatar.url)
    await ctx.send(embed=embed)

@bot.command(name='giveXP')
@commands.has_permissions(manage_roles=True)
async def give_xp(ctx, member: discord.Member, amount: int):
    # Limite pour éviter les abus et les boucles infinies
    if amount > 10000:
        await ctx.send(f"❌ Maximum 10 000 XP par commande ! (demandé : {amount:,})")
        return
    
    if amount < 0:
        await ctx.send("❌ On peut pas donner d'XP négatif !")
        return
    
    user_id = str(member.id)
    data = await get_user_data(user_id, member.name)
    
    data["xp"] += amount
    xp_needed = data["level"] * 100
    leveled_up = False
    levels_gained = 0
    
    # Limiter aussi le nombre de level ups en une fois (sécurité supplémentaire)
    max_iterations = 100
    iterations = 0
    
    while data["xp"] >= xp_needed and iterations < max_iterations:
        data["xp"] -= xp_needed 
        data["level"] += 1
        leveled_up = True
        levels_gained += 1
        xp_needed = data["level"] * 100
        iterations += 1
    
    await update_user_data(user_id, data["xp"], data["level"])
    
    # Message avec plus d'infos
    if leveled_up:
        await ctx.send(
            f"🎉 {member.mention} a reçu {amount:,} XP et a monté **{levels_gained} niveau(x)** !\n"
            f"**Nouveau niveau : {data['level']}** | XP restant : {data['xp']}"
        )
    else:
        await ctx.send(f"✅ {member.mention} a reçu {amount:,} XP!")

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    if amount > 50:
        await ctx.send("Max 50 messages!")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Hop! {len(deleted)-1} messages supprimés", delete_after=3)
    except:
        await ctx.send("J'ai foiré, désolé!")


@bot.command(name='banlist')
@commands.has_permissions(ban_members=True)
async def banlist(ctx):
    try:
        bans = []
        async for ban_entry in ctx.guild.bans():
            bans.append(ban_entry)
        
        if not bans:
            await ctx.send("Aucun membre banni.")
            return
        
        ban_list = "\n".join([f"{ban_entry.user.name}#{ban_entry.user.discriminator}" for ban_entry in bans])
        embed = discord.Embed(
            title="Liste des bannis",
            description=ban_list,
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Erreur: {e}")

@bot.command(name='message')
async def message(ctx, *, content, channel: discord.TextChannel = None):
    if channel is None:
        channel = ctx.channel
    await channel.send(content)
    await ctx.message.delete()

@bot.command(name='ask', aliases=['ia', 'groq'])
async def ask_ai(ctx, *, question):
    user_id = str(ctx.author.id)
    
    # Initialiser l'historique si l'utilisateur est nouveau
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    # Ajouter le message de l'utilisateur à l'historique
    conversation_history[user_id].append({
        "role": "user",
        "content": question
    })
    
    # Limiter l'historique à 20 messages (10 échanges) pour éviter de dépasser la limite
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    
    async with ctx.typing():
        # Construire les messages avec le contexte système + historique
        messages = [
            {"role": "system", "content": "Tu es un assistant sur Discord. Réponds de manière concise avec un air décontracté et jeune. Tu te souviens de la conversation précédente avec l'utilisateur."}
        ] + conversation_history[user_id]
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        
        # Ajouter la réponse du bot à l'historique
        conversation_history[user_id].append({
            "role": "assistant",
            "content": answer
        })
        
        await ctx.send(answer)


@bot.command(name='clearconvo', aliases=['resetconvo', 'oublie'])
async def clear_conversation(ctx):
    """Efface l'historique de conversation avec le bot"""
    user_id = str(ctx.author.id)
    if user_id in conversation_history:
        conversation_history[user_id] = []
        await ctx.send("✅ J'ai oublié notre conversation, on repart de zéro!")
    else:
        await ctx.send("On n'avait pas encore parlé ensemble!")
        
        
@bot.command(name='poll')
@commands.has_permissions(manage_messages=True)
async def poll(ctx, *, question):
    embed = discord.Embed(title="Nouveau sondage!", description=question, color=discord.Color.purple())
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction('👍')
    await poll_message.add_reaction('👎')
    await ctx.message.delete()
    
@bot.command(name='joke')
async def joke(ctx):
    async with ctx.typing():
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=[
                {"role": "system", "content": "Tu es une assistante sur Discord. Réponds de manière drôle et décontractée avec un air jeune."},
                {"role": "user", "content": "Raconte-moi une blague."}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        joke_text = response.choices[0].message.content.strip()
        await ctx.send(joke_text)
        
@bot.command(name='resetxp')
@commands.has_permissions(manage_roles=True)
async def reset_xp(ctx, member: discord.Member):
    user_id = str(member.id)
    await update_user_data(user_id, 0, 1)
    await ctx.send(f"XP et niveau de {member.mention} réinitialisés!")


# ========== COMMANDES SYSTÈME DE JEU ==========

@bot.command(name='games', aliases=['gaming', 'whoplays'])
async def current_games(ctx):
    """Affiche qui joue à quoi actuellement"""
    if not game_stats:
        await ctx.send("❌ Personne ne joue actuellement!")
        return
    
    # Filtrer uniquement les jeux avec des joueurs actifs
    active_games = {game: data for game, data in game_stats.items() 
                    if data['current_players']}
    
    if not active_games:
        await ctx.send("❌ Personne ne joue actuellement!")
        return
    
    embed = discord.Embed(
        title="🎮 Sessions de Jeu Actives",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    
    for game_name, data in active_games.items():
        player_mentions = []
        for user_id in data['current_players']:
            try:
                member = ctx.guild.get_member(int(user_id))
                if member:
                    # Calculer le temps de jeu actuel
                    if user_id in game_sessions:
                        duration = datetime.now() - game_sessions[user_id]['start_time']
                        hours = duration.total_seconds() / 3600
                        if hours >= 1:
                            time_str = f" ({hours:.1f}h)"
                        else:
                            minutes = duration.total_seconds() / 60
                            time_str = f" ({minutes:.0f}min)"
                        player_mentions.append(f"{member.mention}{time_str}")
                    else:
                        player_mentions.append(member.mention)
            except:
                pass
        
        if player_mentions:
            players_text = "\n".join(player_mentions)
            embed.add_field(
                name=f"🎯 {game_name}",
                value=players_text,
                inline=False
            )
    
    embed.set_footer(text=f"Total: {sum(len(d['current_players']) for d in active_games.values())} joueur(s)")
    await ctx.send(embed=embed)


@bot.command(name='playtime', aliases=['gametime', 'stats'])
async def playtime_stats(ctx, member: discord.Member = None):
    """Affiche le temps de jeu d'un utilisateur"""
    if member is None:
        member = ctx.author
    
    user_id = str(member.id)
    
    # Vérifier si l'utilisateur joue actuellement
    if user_id in game_sessions:
        session = game_sessions[user_id]
        current_duration = datetime.now() - session['start_time']
        hours = current_duration.total_seconds() / 3600
        
        embed = discord.Embed(
            title=f"🎮 Session de {member.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        if hours >= 1:
            time_text = f"{hours:.1f} heure(s)"
        else:
            minutes = current_duration.total_seconds() / 60
            time_text = f"{minutes:.0f} minute(s)"
        
        embed.add_field(
            name="Jeu actuel",
            value=f"**{session['game']}**",
            inline=True
        )
        embed.add_field(
            name="Temps de jeu",
            value=time_text,
            inline=True
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"😴 {member.mention} ne joue à rien actuellement!")


@bot.command(name='topgames', aliases=['populargames', 'gametop'])
async def top_games(ctx, limit: int = 10):
    """Affiche les jeux les plus populaires du serveur"""
    if limit > 20:
        limit = 20
    
    if not game_stats:
        await ctx.send("❌ Aucune statistique de jeu disponible!")
        return
    
    # Trier les jeux par temps total de jeu
    sorted_games = sorted(
        game_stats.items(),
        key=lambda x: x[1]['total_time'],
        reverse=True
    )[:limit]
    
    if not sorted_games:
        await ctx.send("❌ Aucune statistique de jeu disponible!")
        return
    
    embed = discord.Embed(
        title="🏆 Top des Jeux les Plus Joués",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    description = ""
    for idx, (game_name, data) in enumerate(sorted_games, 1):
        total_hours = data['total_time'].total_seconds() / 3600
        
        # Ajouter médailles pour le top 3
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
        
        # Afficher différemment selon le temps
        if total_hours >= 1:
            time_str = f"{total_hours:.1f}h"
        else:
            minutes = data['total_time'].total_seconds() / 60
            time_str = f"{minutes:.0f}min"
        
        # Nombre de joueurs actuels
        current = len(data['current_players'])
        current_str = f" • 🟢 {current} en ligne" if current > 0 else ""
        
        description += f"{medal} **{game_name}** - {time_str}{current_str}\n"
    
    embed.description = description
    embed.set_footer(text=f"Statistiques de {ctx.guild.name}")
    await ctx.send(embed=embed)


@bot.command(name='gamestats', aliases=['gameinfo'])
async def game_stats_cmd(ctx, *, game_name: str):
    """Affiche les statistiques détaillées d'un jeu spécifique"""
    # Rechercher le jeu (insensible à la casse)
    found_game = None
    for game in game_stats.keys():
        if game.lower() == game_name.lower():
            found_game = game
            break
    
    if not found_game:
        await ctx.send(f"❌ Aucune statistique trouvée pour **{game_name}**")
        return
    
    data = game_stats[found_game]
    total_hours = data['total_time'].total_seconds() / 3600
    current_players = len(data['current_players'])
    
    embed = discord.Embed(
        title=f"📊 Statistiques de {found_game}",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    
    if total_hours >= 1:
        time_str = f"{total_hours:.1f} heures"
    else:
        minutes = data['total_time'].total_seconds() / 60
        time_str = f"{minutes:.0f} minutes"
    
    embed.add_field(
        name="⏱️ Temps total de jeu",
        value=time_str,
        inline=True
    )
    embed.add_field(
        name="👥 Joueurs actuels",
        value=str(current_players),
        inline=True
    )
    
    # Lister les joueurs actuels
    if current_players > 0:
        player_list = []
        for user_id in data['current_players']:
            try:
                member = ctx.guild.get_member(int(user_id))
                if member:
                    player_list.append(member.mention)
            except:
                pass
        
        if player_list:
            embed.add_field(
                name="🎮 En train de jouer",
                value="\n".join(player_list[:10]),
                inline=False
            )
    
    await ctx.send(embed=embed)

@bot.command(name='clearchannel')
@commands.has_permissions(manage_channels=True)
async def clear_channel(ctx, channel: discord.TextChannel = None):
    """Supprime tous les messages d'un canal spécifique"""
    if channel is None:
        channel = ctx.channel
    
    try:
        await channel.purge()
        await ctx.send(f"✅ Tous les messages dans {channel.mention} ont été supprimés!", delete_after=5)
    except Exception as e:
        await ctx.send(f"Erreur lors de la suppression des messages: {e}")

if __name__ == '__main__':
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("TOKEN non trouvé! Vérifie ton fichier .env")