from keep_alive import keep_alive

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import json
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)
TYPY_FILE = "typy.json"
DYREKTYWY_FILE = "dyrektywy.json"

wyslane_przypomnienia = {"48h": set(), "1h": set(), "ujawnione": set()}

def load_typy():
    if not os.path.exists(TYPY_FILE):
        with open(TYPY_FILE, 'w') as f:
            json.dump({}, f)
    with open(TYPY_FILE, "r") as f:
        return json.load(f)

def save_typy(data):
    with open(TYPY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_dyrektywy():
    if not os.path.exists(DYREKTYWY_FILE):
        with open(DYREKTYWY_FILE, "w") as f:
            json.dump({}, f)
    with open(DYREKTYWY_FILE, "r") as f:
        return json.load(f)

def save_dyrektywy(data):
    with open(DYREKTYWY_FILE, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Zalogowano jako {bot.user}")
    bot.loop.create_task(przypomnienia_task())

@bot.tree.command(name="typy", description="Wyślij swoje typy na daną sesję.")
@app_commands.describe(sesja="Np. MIAMI – KWALIFIKACJE", typy="Lista kierowców w kolejności")
async def typy(interaction: discord.Interaction, sesja: str, typy: str):
    dyrektywy = load_dyrektywy()
    teraz = datetime.utcnow().isoformat()
    sesja = sesja.upper().replace("_", " – ")

    if sesja not in dyrektywy:
        await interaction.response.send_message("❌ Dyrektywa dla tej sesji nie istnieje.", ephemeral=True)
        return

    data = load_typy()
    member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
    author = member.nick if member and member.nick else interaction.user.name

    if sesja not in data:
        data[sesja] = {}
    data[sesja][author] = {"czas": teraz, "typy": typy}
    save_typy(data)

    channel = discord.utils.get(bot.get_all_channels(), name="typy-2025")
    if channel:
        await channel.send(f"🏎️ Otrzymano typy od <@{interaction.user.id}> na `{sesja}`!")

    await interaction.response.send_message(f"✅ Typy zapisane dla sesji `{sesja}`.", ephemeral=True)

@bot.tree.command(name="ujawnij", description="Ujawni typy dla wybranej sesji natychmiast.")
@app_commands.describe(sesja="Np. MIAMI – KWALIFIKACJE")
async def ujawnij(interaction: discord.Interaction, sesja: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Komenda musi być użyta na serwerze.", ephemeral=True)
        return

    organizer_role = discord.utils.get(interaction.guild.roles, name="Organizator")
    member = interaction.guild.get_member(interaction.user.id)
    if not member or organizer_role not in member.roles:
        await interaction.response.send_message("❌ Tylko Organizator może użyć tej komendy.", ephemeral=True)
        return

    dyrektywy = load_dyrektywy()
    teraz = datetime.utcnow().isoformat()
    sesja = sesja.upper().replace("_", " – ")
    dyrektywy[sesja] = teraz
    save_dyrektywy(dyrektywy)

    await interaction.response.send_message(f"📢 Typy od uczestników na `{sesja}`:", ephemeral=False)
    await ujawnij_typy_dla_sesji(sesja)

@bot.tree.command(name="najblizsza_sesja", description="Pokaż najbliższą zaplanowaną sesję.")
async def najblizsza_sesja(interaction: discord.Interaction):
    dyrektywy = load_dyrektywy()
    teraz = datetime.utcnow()

    najblizsza = None
    najblizszy_czas = None

    for sesja, czas_str in dyrektywy.items():
        try:
            czas = datetime.fromisoformat(czas_str)
            if czas > teraz:
                if najblizszy_czas is None or czas < najblizszy_czas:
                    najblizsza = sesja
                    najblizszy_czas = czas
        except ValueError:
            continue

    if najblizszy_czas is not None:
        czas_polish = najblizszy_czas.strftime("%d.%m.%Y %H:%M UTC")
        await interaction.response.send_message(
            f"🗓 Najbliższa sesja to **{najblizsza}** typy wysyłamy: **{czas_polish}**.", ephemeral=True
        )
    else:
        await interaction.response.send_message("❌ Brak nadchodzących sesji.", ephemeral=True)

async def przypomnienia_task():
    await bot.wait_until_ready()
    kanal = discord.utils.get(bot.get_all_channels(), name="typy-2025")
    if not isinstance(kanal, discord.TextChannel):
        print("⚠️ Nie znaleziono kanału #typy-2025.")
        return

    while not bot.is_closed():
        teraz = datetime.utcnow()
        dyrektywy = load_dyrektywy()

        for sesja, czas_str in dyrektywy.items():
            try:
                czas = datetime.fromisoformat(czas_str)
                roznica = czas - teraz
                czas_format = czas.strftime("%d.%m.%Y %H:%M UTC")

                if timedelta(hours=47, minutes=55) < roznica < timedelta(hours=48, minutes=5) and sesja not in wyslane_przypomnienia["48h"]:
                    await kanal.send(f"📌 Typy na sesję **{sesja}** należy przesłać przed **{czas_format}**.")
                    wyslane_przypomnienia["48h"].add(sesja)

                elif timedelta(minutes=55) < roznica < timedelta(minutes=65) and sesja not in wyslane_przypomnienia["1h"]:
                    await kanal.send(f"⏰ Została **1 godzina** do terminu wysłania typów na **{sesja}**. Nie zapomnijcie!")
                    wyslane_przypomnienia["1h"].add(sesja)

                elif teraz >= czas and sesja not in wyslane_przypomnienia["ujawnione"]:
                    await kanal.send(f"📢 Czas na typy minął. Ujawniono zgłoszenia dla sesji **{sesja}**:")
                    await ujawnij_typy_dla_sesji(sesja)
                    wyslane_przypomnienia["ujawnione"].add(sesja)

            except Exception as e:
                print(f"Błąd przy sesji {sesja}: {e}")

        await asyncio.sleep(300)

async def ujawnij_typy_dla_sesji(sesja):
    kanal = discord.utils.get(bot.get_all_channels(), name="typy-2025")
    typy_data = load_typy()
    if sesja in typy_data:
        for autor, dane in typy_data[sesja].items():
            await kanal.send(f"🖋 Typy od **{autor}** na `{sesja}`:\n{dane['typy']}")

# Start
keep_alive()
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("TOKEN brak")
bot.run(token)
