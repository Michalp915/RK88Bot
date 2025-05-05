from keep_alive import keep_alive

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
from datetime import datetime, timedelta
import pytz
import json
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)
TYPY_FILE = "typy.json"
DYREKTYWY_FILE = "dyrektywy.json"

wyslane_przypomnienia = {"48h": set(), "1h": set()}
ujawnione_sesje = set()
strefa_czasowa = pytz.timezone("Europe/Warsaw")

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

class TypyModal(Modal, title="Wyślij swoje typy"):
    sesja = TextInput(label="Nazwa sesji", placeholder="Np. MIAMI - WYŚCIG", required=True)
    typy = TextInput(label="Typy (lista kierowców)", style=discord.TextStyle.paragraph, placeholder="Np. 1. Verstappen 2. Leclerc 3. Alonso...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        dyrektywy = load_dyrektywy()
        teraz = datetime.utcnow().isoformat()
        sesja_nazwa = self.sesja.value.upper()

        if sesja_nazwa not in dyrektywy:
            await interaction.response.send_message("❌ Dyrektywa dla tej sesji nie istnieje.", ephemeral=True)
            return

        data = load_typy()
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        author = member.nick if member and member.nick else interaction.user.name

        if sesja_nazwa not in data:
            data[sesja_nazwa] = {}
        data[sesja_nazwa][author] = {"czas": teraz, "typy": self.typy.value}
        save_typy(data)

        channel = discord.utils.get(bot.get_all_channels(), name="typy-2025")
        if channel:
            await channel.send(f"🏁 Otrzymano typy od <@{interaction.user.id}> na `{sesja_nazwa}`!")

        await interaction.response.send_message(f"✅ Typy zapisane dla sesji `{sesja_nazwa}`.", ephemeral=True)

@bot.tree.command(name="typy", description="Otwórz formularz do wysyłki typów")
async def typy_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(TypyModal())

@bot.tree.command(name="ujawnij", description="Ujawni typy dla wybranej sesji natychmiast.")
@app_commands.describe(sesja="Np. MIAMI - KWALIFIKACJE")
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
    sesja = sesja.upper()
    dyrektywy[sesja] = teraz
    save_dyrektywy(dyrektywy)

    await interaction.response.send_message(f"📢 Czas na typy minął. Oto wszystkie przesłane typy na **{sesja}**:", ephemeral=False)

    typy_data = load_typy()
    if sesja in typy_data:
        channel = discord.utils.get(bot.get_all_channels(), name="typy-2025")
        if channel:
            for autor, dane in typy_data[sesja].items():
                await channel.send(f"📬 Typy od **{autor}** na `{sesja}`:\n{dane['typy']}")

@bot.tree.command(name="najblizsza_sesja", description="Pokaż najbliższą zaplanowaną sesję.")
async def najblizsza_sesja(interaction: discord.Interaction):
    dyrektywy = load_dyrektywy()
    teraz = datetime.utcnow()

    najblizsza = None
    najblizszy_czas = None

    for sesja, czas_str in dyrektywy.items():
        try:
            czas = datetime.fromisoformat(czas_str)
            if czas > teraz and (najblizszy_czas is None or czas < najblizszy_czas):
                najblizsza = sesja
                najblizszy_czas = czas
        except ValueError:
            continue

    if najblizszy_czas:
        czas_cest = pytz.utc.localize(najblizszy_czas).astimezone(strefa_czasowa)
        czas_polish = czas_cest.strftime("%d.%m.%Y %H:%M CEST")
        await interaction.response.send_message(f"🗓 Najbliższa sesja to **{najblizsza}**. Typy wysyłamy do **{czas_polish}**.", ephemeral=True)
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
                czas_cest = pytz.utc.localize(czas).astimezone(strefa_czasowa)
                czas_format = czas_cest.strftime("%d.%m.%Y %H:%M CEST")

                if timedelta(hours=47, minutes=55) < roznica < timedelta(hours=48, minutes=5) and sesja not in wyslane_przypomnienia["48h"]:
                    await kanal.send(f"📌 Typy na sesję **{sesja}** należy przesłać przed **{czas_format}**.")
                    wyslane_przypomnienia["48h"].add(sesja)

                elif timedelta(minutes=55) < roznica < timedelta(minutes=65) and sesja not in wyslane_przypomnienia["1h"]:
                    await kanal.send(f"⏰ Została **1 godzina** do terminu wysłania typów na **{sesja}**. Nie zapomnijcie!")
                    wyslane_przypomnienia["1h"].add(sesja)

                elif teraz > czas and sesja not in ujawnione_sesje:
                    typy_data = load_typy()
                    if sesja in typy_data:
                        await kanal.send(f"🔔 Czas na typy minął. Oto wszystkie przesłane typy na **{sesja}**:")
                        for autor, dane in typy_data[sesja].items():
                            await kanal.send(f"📬 Typy od **{autor}** na `{sesja}`:\n{dane['typy']}")
                    else:
                        await kanal.send(f"🔔 Czas na typy minął. Brak typów dla **{sesja}**.")
                    ujawnione_sesje.add(sesja)

            except Exception as e:
                print(f"Błąd przy sesji {sesja}: {e}")

        await asyncio.sleep(300)

# Start
keep_alive()

@bot.event
async def setup_hook():
    # To wymusza wyczyszczenie starych komend
    bot.tree.clear_commands(guild=None)

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("TOKEN brak")
bot.run(token)
