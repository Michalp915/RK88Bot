import json

with open("dyrektywy.json", "r", encoding="utf-8") as f:
    dane = json.load(f)

nowe_dane = {}
for klucz, wartosc in dane.items():
    if " – " in klucz:
        nowe_dane[klucz] = wartosc
    else:
        nowy_klucz = klucz.replace("_", " – ", 1)
        nowe_dane[nowy_klucz] = wartosc

with open("dyrektywy.json", "w", encoding="utf-8") as f:
    json.dump(nowe_dane, f, ensure_ascii=False, indent=4)