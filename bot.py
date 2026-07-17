import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import asyncio
import os

# ==================== DEBUG PRINT ====================
print("=== BOT IS STARTING ===")
print(f"Python version: {os.sys.version}")
print(f"Token exists: {bool(os.getenv('DISCORD_TOKEN'))}")

# Database setup
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('middleman.db')
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                user_id INTEGER,
                middleman_id INTEGER,
                status TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS vouches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                vouch_count INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                hit_count INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS mercy_users (
                user_id INTEGER PRIMARY KEY,
                accepted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_warning(self, user_id, moderator_id, reason):
        self.cursor.execute(
            "INSERT INTO warnings (user_id, moderator_id, reason) VALUES (?, ?, ?)",
            (user_id, moderator_id, reason)
        )
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_warnings(self, user_id):
        self.cursor.execute(
            "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        )
        return self.cursor.fetchall()
    
    def clear_warnings(self, user_id):
        self.cursor.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    def delete_warning(self, warning_id):
        self.cursor.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        self.conn.commit()
    
    def add_vouch(self, user_id):
        self.cursor.execute(
            "INSERT INTO vouches (user_id, vouch_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET vouch_count = vouch_count + 1",
            (user_id,)
        )
        self.conn.commit()
    
    def get_vouch_count(self, user_id):
        self.cursor.execute("SELECT vouch_count FROM vouches WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def remove_vouches(self, user_id, count=0):
        if count > 0:
            self.cursor.execute(
                "UPDATE vouches SET vouch_count = vouch_count - ? WHERE user_id = ?",
                (count, user_id)
            )
        else:
            self.cursor.execute("DELETE FROM vouches WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    def add_hit(self, user_id):
        self.cursor.execute(
            "INSERT INTO hits (user_id, hit_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET hit_count = hit_count + 1",
            (user_id,)
        )
        self.conn.commit()
        return self.get_hit_count(user_id)
    
    def get_hit_count(self, user_id):
        self.cursor.execute("SELECT hit_count FROM hits WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

# Bot class
class MiddlemanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='+', intents=intents)
        self.db = Database()
        
        # Role IDs
        self.role_ids = {
            'Giveaway Pings': 1525886452729122836,
            'Middleman Team': 1525886452729122836,
            'Junior Middleman': 1526273044258095265,
            'Senior Middleman': 1526273380968435772,
            'Staff Manager': 1526273862101372959,
            'Coordinator': 1526274022445416599,
            'Administrator': 1526274129819602964,
            'Head of Coordination': 1526274462805266472,
            'Head of Staff': 1526274613196095631,
            'Head of Supervision': 1526274730514972764,
            'Head of Operations': 1526274865877749934,
            'Head of Development': 1526275269634035853,
            'Chief Management Officer': 1526275391210127420,
            'President': 1526275570235605195
        }
        
        # Role requirements (hits or price)
        self.role_requirements = {
            'Middleman Team': {'hits': 5, 'price': 5},
            'Junior Middleman': {'hits': 10, 'price': 10, 'discount': 5},
            'Senior Middleman': {'hits': 20, 'price': 15, 'discount': 7},
            'Staff Manager': {'hits': 30, 'price': 25, 'discount': 10},
            'Coordinator': {'hits': 50, 'price': 25, 'discount': 15},
            'Administrator': {'price': 30, 'discount': 20},
            'Head of Coordination': {'price': 40, 'discount': 25},
            'Head of Staff': {'price': 50, 'discount': 30},
            'Head of Supervision': {'price': 60, 'discount': 35},
            'Head of Operations': {'price': 75, 'discount': 45},
            'Head of Development': {'price': 100, 'discount': 60},
            'Chief Management Officer': {'price': 150, 'discount': 75},
            'President': {'price': 250, 'discount': 100}
        }
        
        # Permission levels
        self.permission_levels = {
            'Middleman Team': 1,
            'Junior Middleman': 2,
            'Senior Middleman': 3,
            'Staff Manager': 4,
            'Coordinator': 5,
            'Administrator': 6,
            'Head of Coordination': 7,
            'Head of Staff': 8,
            'Head of Supervision': 9,
            'Head of Operations': 10,
            'Head of Development': 11,
            'Chief Management Officer': 12,
            'President': 13
        }
        
        # Channel IDs
        self.support_channel = 1526591527244140554
        self.support_category = 1526668755130646670
        self.middleman_category = 1526668717025398804
        self.transcripts_channel = 1526706503632031906
        self.setup_role = 1526271680371232788

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

    def has_permission(self, user, required_roles):
        """Check if user has any of the required roles"""
        if not isinstance(user, discord.Member):
            return False
        for role in user.roles:
            for req_role in required_roles:
                if req_role in self.role_ids and role.id == self.role_ids[req_role]:
                    return True
        return False

    def has_setup_role(self, user):
        """Check if user has setup role"""
        if not isinstance(user, discord.Member):
            return False
        return any(role.id == self.setup_role for role in user.roles)

    def has_middleman_permission(self, user):
        """Check if user has middleman permissions"""
        if not isinstance(user, discord.Member):
            return False
        middleman_roles = [
            'Middleman Team', 'Junior Middleman', 'Senior Middleman',
            'Staff Manager', 'Coordinator', 'Administrator',
            'Head of Coordination', 'Head of Staff', 'Head of Supervision',
            'Head of Operations', 'Chief Management Officer', 'President'
        ]
        return self.has_permission(user, middleman_roles)

    def can_manage_role(self, user, role):
        """Check if user can manage a specific role based on hierarchy"""
        if not isinstance(user, discord.Member):
            return False
        
        user_highest = 0
        role_position = 0
        
        for r in user.roles:
            if r.id in self.role_ids.values():
                for name, rid in self.role_ids.items():
                    if rid == r.id and name in self.permission_levels:
                        if self.permission_levels[name] > user_highest:
                            user_highest = self.permission_levels[name]
        
        for name, rid in self.role_ids.items():
            if rid == role.id and name in self.permission_levels:
                role_position = self.permission_levels[name]
                break
        
        return user_highest > role_position

    def is_ticket_channel(self, channel):
        """Check if a channel is a ticket"""
        if not channel:
            return False
        self.db.cursor.execute(
            "SELECT id FROM tickets WHERE channel_id = ? AND status = 'open'",
            (channel.id,)
        )
        return self.db.cursor.fetchone() is not None

# Bot instance
bot = MiddlemanBot()

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user.name} (ID: {bot.user.id})")
    print(f"📊 Connected to {len(bot.guilds)} servers:")
    for guild in bot.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
    print("✅ Bot is ready to use!")
    
    # Sync slash commands
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced successfully!")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# ==================== PREFIX COMMANDS ====================

@bot.command(name='warn')
async def warn_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Warn a member - +warn @user reason"""
    if not bot.has_permission(ctx.author, ['Staff Manager', 'Coordinator', 'Administrator', 'Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    bot.db.add_warning(member.id, ctx.author.id, reason)
    warnings = bot.db.get_warnings(member.id)
    
    embed = discord.Embed(
        title="⚠️ User Warned",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Total Warnings", value=len(warnings), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='clearwarn')
async def clearwarn_command(ctx, member: discord.Member):
    """Clear all warnings from a member - +clearwarn @user"""
    if not bot.has_permission(ctx.author, ['Staff Manager', 'Coordinator', 'Administrator', 'Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    bot.db.clear_warnings(member.id)
    embed = discord.Embed(
        title="✅ Warnings Cleared",
        description=f"All warnings for {member.mention} have been cleared.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='delwarn')
async def delwarn_command(ctx, warning_id: int):
    """Delete a specific warning - +delwarn [id]"""
    if not bot.has_permission(ctx.author, ['Staff Manager', 'Coordinator', 'Administrator', 'Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    bot.db.delete_warning(warning_id)
    await ctx.send(f"✅ Warning {warning_id} deleted!")

@bot.command(name='info')
async def info_command(ctx):
    """Get role information - +info"""
    embed = discord.Embed(
        title="📋 ROLE REQUIREMENTS",
        color=discord.Color.blue()
    )
    
    requirements = ""
    role_list = list(bot.role_requirements.keys())
    for i, role in enumerate(role_list):
        req = bot.role_requirements[role]
        role_ping = f"@[{role}]"
        if 'hits' in req:
            if 'discount' in req:
                requirements += f"**{role_ping}**\n   • {req['hits']} hits OR ${req['price']} | ${req['discount']} if already @[{role_list[i-1]}]\n\n"
            else:
                requirements += f"**{role_ping}**\n   • {req['hits']} hits OR ${req['price']}\n\n"
        else:
            if 'discount' in req:
                requirements += f"**{role_ping}**\n   • ${req['price']} | ${req['discount']} if already @[{role_list[i-1]}]\n\n"
            else:
                requirements += f"**{role_ping}**\n   • ${req['price']}\n\n"
    
    embed.description = requirements
    await ctx.send(embed=embed)

@bot.command(name='perks')
async def perks_command(ctx):
    """Get role perks - +perks"""
    perks_text = """⭐ ROLE PERKS

**@[GP] Giveaway Pings** — Get this role after mercy is accepted, hitters only.

**@[MT] Middleman Team** — Claim tickets, handle tickets, use middleman commands, view transcripts.

**@[JM] Junior Middleman** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members.

**@[SM] Senior Middleman** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members.

**@[SMgr] Staff Manager** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members.

**@[Coord] Coordinator** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members.

**@[Admin] Administrator** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell Trial Middleman, promote Trial Middleman.

**@[HoC] Head of Coordination** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell Trial Middleman, promote Trial Middleman, promote Junior Middleman, promote Senior Middleman.

**@[HoS] Head of Staff** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Coordination and below.

**@[HoSup] Head of Supervision** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Staff and below.

**@[HoOp] Head of Operations** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Supervision and below.

**@[HoDev] Head of Development** — Develop bots, develop systems, configure bots, manage integrations.

**@[CMO] Chief Management Officer** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Operations and below.

**@[Pres] President** — Admin perms, can do all perms below, and sell all roles below."""
    
    # Split into chunks of 2000 characters (Discord limit)
    chunks = [perks_text[i:i+1900] for i in range(0, len(perks_text), 1900)]
    for chunk in chunks:
        await ctx.send(chunk)

# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="setup", description="Setup the middleman system")
async def setup(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("❌ You need the Setup role to use this!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🛠️ Middleman Setup Panel",
        description="Welcome to the Middleman Setup System!",
        color=discord.Color.blue()
    )
    embed.add_field(name="📌 Support", value="Configure support channels", inline=True)
    embed.add_field(name="📌 Middleman", value="Configure middleman system", inline=True)
    embed.add_field(name="📌 Transcripts", value="Configure transcripts", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="support", description="Setup support panel")
async def support(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("❌ You need the Setup role!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📞 Support Panel",
        description="Click the button below to create a support ticket",
        color=discord.Color.blue()
    )
    view = SupportView(bot)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="add", description="Add someone to a ticket")
@app_commands.describe(user="User to add to the ticket")
async def add_to_ticket(interaction: discord.Interaction, user: discord.Member):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return
    
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
    await interaction.response.send_message(f"✅ Added {user.mention} to the ticket!")

@bot.tree.command(name="transfer", description="Transfer a ticket to another middleman")
@app_commands.describe(middleman="The middleman to transfer to")
async def transfer(interaction: discord.Interaction, middleman: discord.Member):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return
    
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    bot.db.cursor.execute(
        "UPDATE tickets SET middleman_id = ? WHERE channel_id = ?",
        (middleman.id, interaction.channel.id)
    )
    bot.db.conn.commit()
    
    await interaction.response.send_message(f"✅ Ticket transferred to {middleman.mention}")

@bot.tree.command(name="close", description="Close the current ticket")
async def close_ticket(interaction: discord.Interaction):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return
    
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    bot.db.cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
        (datetime.now(), interaction.channel.id)
    )
    bot.db.conn.commit()
    
    await interaction.response.send_message("✅ Ticket will be closed in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

@bot.tree.command(name="mercy", description="Start the mercy program to become a middleman")
async def mercy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤝 Mercy Offer",
        description=f"@{interaction.user.name}\n\nWe regret to inform you that you have been scammed.\nWe sincerely apologize for this unfortunate situation.\n\nHowever, there is a way to recover your losses and potentially earn more.\n\n**What is the Mercy Program?**\nThe Mercy Program allows selected users to join our private system and start earning through our internal methods.\n\nIf you are active, you may recover your losses and potentially earn even more.\n\n**Choose below if you want to join.**\nYou have 60 seconds to respond.",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Trade Haven | Mercy System")
    
    view = MercyView(bot)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="confirm", description="Confirm a trade between two users")
@app_commands.describe(user1="First user", user2="Second user")
async def confirm(interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    hit1 = bot.db.add_hit(user1.id)
    hit2 = bot.db.add_hit(user2.id)
    
    embed = discord.Embed(
        title="✅ Trade Confirmed",
        description=f"Trade between {user1.mention} and {user2.mention} has been confirmed!",
        color=discord.Color.green()
    )
    embed.add_field(name="Middleman", value=interaction.user.mention, inline=True)
    embed.add_field(name="Time", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="📊 Stats", value=f"{user1.mention}: {hit1} hits\n{user2.mention}: {hit2} hits", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fee", description="View the middleman fee structure")
async def fee(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💰 Middleman Fee Structure",
        color=discord.Color.gold()
    )
    embed.add_field(name="Standard Fee", value="5% of trade value", inline=True)
    embed.add_field(name="Minimum Fee", value="$5 USD", inline=True)
    embed.add_field(name="Maximum Fee", value="$50 USD", inline=True)
    embed.add_field(name="💡 Tip", value="Fees are split 50/50 between middleman and the program", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="policy", description="View the middleman policy")
async def policy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Middleman Policy",
        color=discord.Color.blue()
    )
    embed.add_field(name="1. Safety First", value="Always ensure both parties are legitimate before proceeding", inline=False)
    embed.add_field(name="2. Confirmation", value="Both parties must confirm the trade before completion", inline=False)
    embed.add_field(name="3. Screenshots", value="Take screenshots of all trades for verification", inline=False)
    embed.add_field(name="4. Disputes", value="Report any disputes to management immediately", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="howmmworks", description="How the middleman system works")
async def howmmworks(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔄 How Middleman Works",
        color=discord.Color.green()
    )
    embed.add_field(name="Step 1: Find a Trade", value="Find a trade you want to complete", inline=False)
    embed.add_field(name="Step 2: Request Middleman", value="Request a middleman to facilitate the trade", inline=False)
    embed.add_field(name="Step 3: Confirm", value="Both parties confirm the trade", inline=False)
    embed.add_field(name="Step 4: Completion", value="Trade is completed and verified", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="about", description="About Levi's MM Services")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ℹ️ About Levi's MM Services",
        description="Professional middleman services for secure trading",
        color=discord.Color.blue()
    )
    embed.add_field(name="Founded", value="2024", inline=True)
    embed.add_field(name="Trust Score", value="⭐⭐⭐⭐⭐", inline=True)
    embed.add_field(name="Vouches", value="500+", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tos", description="Terms of Service")
async def tos(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Terms of Service",
        color=discord.Color.red()
    )
    embed.add_field(name="1. Acceptance", value="By using our service, you accept these terms", inline=False)
    embed.add_field(name="2. Liability", value="We are not responsible for scams outside our platform", inline=False)
    embed.add_field(name="3. Fees", value="Fees are non-refundable once service is provided", inline=False)
    embed.add_field(name="4. Disputes", value="All disputes will be handled by management", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="scamawareness", description="Learn how to avoid scams")
async def scamawareness(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚠️ Scam Awareness",
        color=discord.Color.red()
    )
    embed.add_field(name="🚫 Never Share Passwords", value="We will never ask for your password", inline=False)
    embed.add_field(name="🔍 Verify Everything", value="Always verify the identity of who you're trading with", inline=False)
    embed.add_field(name="📸 Screenshot Everything", value="Keep records of all trades", inline=False)
    embed.add_field(name="🤔 Trust Your Gut", value="If something seems too good to be true, it probably is", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="faq", description="Frequently Asked Questions")
async def faq(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❓ Frequently Asked Questions",
        color=discord.Color.blue()
    )
    embed.add_field(name="Q: How do I become a middleman?", value="A: Use /mercy command and complete the program", inline=False)
    embed.add_field(name="Q: How much does it cost?", value="A: There are no costs, but there are hit requirements", inline=False)
    embed.add_field(name="Q: What are the requirements?", value="A: 5 hits for Middleman Team, 10 for Junior, 20 for Senior", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouchadd", description="Add a vouch to a user")
@app_commands.describe(user="The user to vouch for")
async def vouchadd(interaction: discord.Interaction, user: discord.Member):
    bot.db.add_vouch(user.id)
    count = bot.db.get_vouch_count(user.id)
    embed = discord.Embed(
        title="⭐ Vouch Added",
        description=f"{user.mention} now has {count} vouches!",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouchcount", description="Check a user's vouches")
@app_commands.describe(user="The user to check")
async def vouchcount(interaction: discord.Interaction, user: discord.Member):
    count = bot.db.get_vouch_count(user.id)
    embed = discord.Embed(
        title="📊 Vouch Count",
        description=f"{user.mention} has **{count}** vouches",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="removevouches", description="Remove vouches from a user")
@app_commands.describe(user="The user", count="Number of vouches to remove (leave empty to delete all)")
async def removevouches(interaction: discord.Interaction, user: discord.Member, count: int = 0):
    if not bot.has_permission(interaction.user, ['Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    bot.db.remove_vouches(user.id, count)
    await interaction.response.send_message(f"✅ Removed {count if count > 0 else 'all'} vouches from {user.mention}", ephemeral=True)

@bot.tree.command(name="manageban", description="Ban/unban a user")
@app_commands.describe(action="ban or unban", user="The user to manage")
async def manageban(interaction: discord.Interaction, action: str, user: discord.User):
    if not bot.has_permission(interaction.user, ['Administrator', 'Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    if action.lower() == 'ban':
        await interaction.guild.ban(user)
        await interaction.response.send_message(f"✅ Banned {user.mention}", ephemeral=True)
    elif action.lower() == 'unban':
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"✅ Unbanned {user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Use 'ban' or 'unban'", ephemeral=True)

@bot.tree.command(name="managerole", description="Add or remove a role from someone")
@app_commands.describe(action="add or remove", user="The user", role="The role to manage")
async def managerole(interaction: discord.Interaction, action: str, user: discord.Member, role: discord.Role):
    if not bot.has_permission(interaction.user, ['Staff Manager', 'Coordinator', 'Administrator', 'Head of Coordination', 'Head of Staff', 'Head of Supervision', 'Head of Operations', 'Chief Management Officer', 'President']):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return
    
    if not bot.can_manage_role(interaction.user, role):
        await interaction.response.send_message("❌ You cannot manage a role higher than or equal to your highest role!", ephemeral=True)
        return
    
    try:
        if action.lower() == 'add':
            await user.add_roles(role)
            await interaction.response.send_message(f"✅ Added {role.name} to {user.mention}", ephemeral=True)
        elif action.lower() == 'remove':
            await user.remove_roles(role)
            await interaction.response.send_message(f"✅ Removed {role.name} from {user.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Use 'add' or 'remove'", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage that role!", ephemeral=True)

# ==================== VIEWS ====================

class SupportView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bot.db.cursor.execute(
            "SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open'",
            (interaction.user.id,)
        )
        existing = self.bot.db.cursor.fetchone()
        if existing:
            await interaction.response.send_message(f"⚠️ You already have an open ticket: <#{existing[0]}>", ephemeral=True)
            return
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=self.bot.support_category)
        
        if not category:
            await interaction.response.send_message("❌ Support category not found!", ephemeral=True)
            return
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for role_id in self.bot.role_ids.values():
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )
        
        self.bot.db.cursor.execute(
            "INSERT INTO tickets (channel_id, user_id) VALUES (?, ?)",
            (channel.id, interaction.user.id)
        )
        self.bot.db.conn.commit()
        
        embed = discord.Embed(
            title="🎫 Ticket Created",
            description=f"Welcome {interaction.user.mention}! A middleman will be with you shortly.",
            color=discord.Color.green()
        )
        embed.add_field(name="Instructions", value="Please describe your issue or trade request.", inline=False)
        
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

class MercyStepView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.step = 1
    
    @discord.ui.button(label="Got it", style=discord.ButtonStyle.success)
    async def got_it(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.step == 1:
            embed = discord.Embed(
                title="📝 Step 2: Convince to Use Middleman",
                description="Use things like:\n• Middlemans are safe\n• We have vouches\n• Secure trading\n\nOnce you confirm a trade, request the middleman.",
                color=discord.Color.purple()
            )
            self.step = 2
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.step == 2:
            embed = discord.Embed(
                title="🎉 Final Step: Spl
