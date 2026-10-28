#!/usr/bin/env python3
"""
birding_report.py
=================

Builds one interactive HTML birding report from eBird and/or Roberts Bird app CSV exports:

  Sightings  every sighting on a map (points or heatmap), species search, and public
             distribution overlays (iNaturalist range maps, GBIF / SABAP2 / eBird records)
  Lifers     the first sighting of each species, by year, as points or a heatmap
  Hotspots   the regional target sites with their specials (seen or still needed), plus a
             heatmap of species you haven't seen yet from public GBIF records
  Stats      Big Year pace by year, life list growth, activity by month (total sightings,
             unique species or lifers), top places for species and for new lifers

Bird names can be shown in Afrikaans or English (switch in the page). Names are matched
through BirdReference.csv, which links Afrikaans, English, Roberts VI and scientific names.

How to run (Mac, in VS Code's terminal or Terminal):
    python3 birding_report.py                      # opens a dialog to choose the CSV(s)
    python3 birding_report.py eBirds2026-09-09_20-01.csv
    python3 birding_report.py "My Lists.csv"       # a Roberts app export
    python3 birding_report.py eBirds.csv "My Lists.csv"   # both, merged (duplicates counted once)
    python3 birding_report.py my.csv --names en -o report.html --save-cleaned
    python3 birding_report.py other.csv --column date="Date Seen" --column species="Bird"

The Run button in VS Code also works: it opens the file dialog, where you can pick
one file or several (hold Cmd to select more than one).

Files from apps other than eBird are recognised by their column headings (species or
bird name in English or Afrikaans, date, place, latitude/longitude or one GPS column).
The script prints which columns it used for each file; if it picks the wrong one,
or can't find one, name it with --column.

Only Python's standard library is used, so there's nothing to pip install (Python 3.8+).
The finished page loads its map and chart libraries from the internet when opened.

Put BirdReference.csv in the same folder as this script (or next to the CSV), or point
to it with --reference.
"""

import argparse
import csv
import datetime
import io
import json
import math
import random
import re
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path

# Column names recognised in eBird, Roberts app and similar CSV exports (case doesn't matter).
# If your file uses other headings, add them here or use --column on the command line.
ALIASES = {
    "sci":  ["sciname", "scientific name", "scientificname", "scientific_name", "scientific", "latin name", "latin", "taxon",
             "wetenskaplike naam"],
    "com":  ["comname", "common name", "commonname", "common_name", "species", "species name", "bird", "bird name", "name",
             "english name", "afrikaans name", "english", "afrikaans", "naam", "voël", "voel"],
    "loc":  ["location", "location name", "locality", "place", "place name", "site", "area", "plek", "lokaliteit"],
    "date": ["date", "observation date", "obs date", "date seen", "sighting date", "date of sighting", "eventdate", "event date",
             "date observed", "datetime", "date/time", "date time", "datum"],
    "lat":  ["latitude", "lat", "decimallatitude", "gps latitude", "gps lat", "breedtegraad"],
    "lon":  ["longitude", "lon", "lng", "long", "decimallongitude", "gps longitude", "gps long", "lengtegraad"],
    "gps":  ["gps", "gps coordinates", "gps co-ordinates", "coordinates", "co-ordinates", "gps location", "position",
             "koördinate", "koordinate"],
    "note": ["comments", "comment", "notes", "note", "observation details", "species comments", "remarks", "checklist comments",
             "notas", "opmerkings"],
}
# Extra headings for the Roberts Bird app export, added on top of ALIASES (which stays unchanged)
EXTRA_ALIASES = {
    "com":  ["bird_name", "english ioc"],
    "date": ["sighting_date_time"],
    "lat":  ["gps_latitude"],
    "lon":  ["gps_longitude"],
}
# Extra name columns that are linked to the species too (a list can show English and Afrikaans side by side)
NAME_COLUMNS = ["english name", "afrikaans name", "english", "afrikaans", "common name", "comname"]

# ==============================================================================
# 0. YOUR CURATED DATA (from Consolidated_Birding_Stats_Most_Correct.py)
# ==============================================================================
# Sightings without coordinates get a point near the first of these names found in
# their Location field.
MISSING_LOCATION_CENTERS = {
    "Satara": (-24.3931, 31.7778),
    "Punda Maria": (-22.6933, 31.0161),
    "Pretoriuskop": (-25.1681, 31.2689),
    "Lower Sabie": (-25.1203, 31.9161),
    "Sabie": (-25.1, 31.9),
    "Skukuza": (-24.9948, 31.5969),
    "Olifants": (-24.0347, 31.7408),
    "Berg en dal": (-25.4194, 31.4514),
    "Berg-en-Dal": (-25.4194, 31.4514),
    "Shingwedzi": (-23.1167, 31.4333),
    "Mopani": (-23.5303, 31.5236),
    "Letaba": (-23.8525, 31.5772),
    "Crocodile Bridge": (-25.3583, 31.8928),
    "Kruger": (-24.9948, 31.5969),
    "Sasolburg": (-26.8144, 27.8286),
    "Vlaardingen": (-26.822, 27.835),
    "Ekopark": (-26.811, 27.842),
    "Natref": (-26.83, 27.8481),
    "Sasol": (-26.83, 27.8481),
    "Brenton": (-34.0722, 23.0244),
    "Rondevlei": (-33.5903, 22.4275),
    "Diepwalle": (-33.9481, 23.1558),
    "Kirstenbosch": (-33.9875, 18.4325),
    "Buffelsbaai": (-34.0844, 22.9739),
    "Buffelsnek": (-33.8825, 23.1561),
    "Knysna": (-34.0356, 23.0488),
    "Avontuur": (-33.7258, 23.1603),
    "Jubelee": (-33.8869, 22.9642),
    "Jubilee": (-33.8869, 22.9642),
    "George": (-33.9608, 22.4617),
    "Oudtshoorn": (-33.5908, 22.2014),
    "Outshoorn": (-33.5908, 22.2014),
    "Boulders": (-34.1972, 18.4514),
    "Fish Hoek": (-34.1361, 18.4286),
    "Vishoek": (-34.1361, 18.4286),
    "Marievale": (-26.3533, 28.5133),
    "Kestell": (-28.3108, 28.7011),
    "Parys": (-26.9031, 27.4561),
    "Heidelberg": (-26.5028, 28.3592),
    "Golden Gate": (-28.5086, 28.6186),
    "Suid Vrystaat": (-30.0, 26.0),
    "Bloemfontein": (-29.1181, 26.2244),
    "Fouriesburg": (-28.6142, 28.2094),
    "Kroonstad": (-27.6508, 27.2344),
    "Oranjeville": (-26.9933, 28.2008),
    "Heilbron": (-27.2808, 27.9719),
    "Clarens": (-28.5156, 28.4186),
    "Winburg": (-28.5175, 27.0089),
    "Karoo": (-32.2, 22.5),
    "Aberdeen": (-32.4753, 24.0653),
    "Graaff": (-32.2522, 24.5406),
    "Venterstad": (-30.7781, 25.7986),
    "Colesberg": (-30.7208, 25.0972),
    "Upington": (-28.4478, 21.2561),
    "Nieu Betestha": (-31.8667, 24.55),
    "Nieu Bethesda": (-31.8667, 24.55),
    "Three Sisters": (-31.9058, 23.1042),
    "Kuruman": (-27.4528, 23.4322),
    "Hanover": (-30.9419, 24.5369),
    "Kimberley": (-28.7282, 24.7499),
    "Rooiputs": (-26.1322, 20.6725),
    "Polentswa": (-25.0883, 20.4183),
    "Kgalagadi": (-25.75, 20.0),
    "Kalahari Gemsbok": (-25.75, 20.0),
    "Kalahari 2026": (-26.95, 20.69),
    "Kiepersol": (-25.0333, 31.0667),
    "Wolmaransstad": (-27.2008, 25.9819),
    "Wolmeranstad": (-27.2008, 25.9819),
    "Vryburg": (-26.9567, 24.7283),
    "Baltimore": (-23.275, 28.435),
    "Alberton": (-26.2625, 28.1222),
    "Wits": (-26.1928, 28.0306),
    "Roedtan": (-24.5986, 29.0817),
    "Waterval Boven": (-25.6442, 30.34),
    "Waterval": (-25.6442, 30.34),
    "Secunda": (-26.5503, 29.1706),
    "Etosha": (-18.8556, 16.3293),
    "Savute": (-18.52, 24.06),
    "Central Kalahari": (-21.85, 23.75),
    "Khwai": (-19.1667, 23.75),
    "Moremi": (-19.2, 23.3333),
    "Maun": (-19.9833, 23.4167),
    "Mopipi": (-21.1833, 24.8833),
    "Orapa": (-21.3, 25.3667),
    "Botswana": (-19.9833, 23.4167),
    "Hwange": (-18.90, 26.50),
    "KNP": (-24.9948, 31.5969),
    "Kosi baai": (-26.90, 32.88),
    "Hermanus": (-34.4187, 19.2345),
    "Kalahari": (-25.75, 20.0),
    "Drakensberge": (-29.0, 29.3),
    "Selati": (-23.95, 30.70),
    "Badplaas": (-25.7869, 30.6978),
    "Scottburgh": (-30.2872, 30.7536),
    "Dinokeng": (-25.37, 28.30),
}

# Location names grouped for the stats charts (regular expression -> group name)
LOCATION_GROUPS = {
    r".*Sabie.*|.*Satara.*|.*Pretoriuskop.*|.*Punda Maria.*|.*Olifants.*|.*Berg en dal.*|.*Skukuza.*|.*Shingwedzi.*|.*Mopani.*|.*KNP.*|.*Letaba.*|.*Kruger.*": "Kruger National Park",
    r".*Vlaardingen.*|.*Ekopark.*|.*Sasol.*|.*Natref.*": "Sasolburg",
    r".*Kgalagadi.*|.*Kalahari.*|.*Rooiputs.*|.*Polentswa.*": "Kgalagadi Transfrontier Park",
    r".*West Coast.*": "West Coast National Park",
    r".*Botswana.*|.*Moremi.*|.*Savute.*": "Botswana",
}

# Regional birding hotspots and their target specials
HOTSPOTS = [
    {
        "name": "Rooiels & Betty's Bay",
        "coords": [-34.302, 18.825],
        "biome": "Coastal Fynbos & Rocky Shore",
        "season": "Year-round (Best: Aug–Nov for fynbos activity)",
        "key_sites": "Rooiels coastal track, Harold Porter Botanical Garden",
        "access": "Public access, walking shoes recommended",
        "specials": [
            {"eng": "Cape Rockjumper", "afr": "Kaapse berglyster", "sci": "Chaetops frenatus"},
            {"eng": "Victorin's Warbler", "afr": "Rooiborsruigtesanger", "sci": "Cryptillas victorini"},
            {"eng": "Cape Siskin", "afr": "Kaapse pietjiekanarie", "sci": "Crithagra totta"},
            {"eng": "Protea Canary", "afr": "Witvlerkkanarie", "sci": "Crithagra leucoptera"},
            {"eng": "Bank Cormorant", "afr": "Bankduiker", "sci": "Phalacrocorax neglectus"},
        ],
    },
    {
        "name": "West Coast National Park & Langebaan",
        "coords": [-33.158, 18.118],
        "biome": "Strandveld & Salt Marsh Estuary",
        "season": "Sep–Apr (Peak waders & summer migrants)",
        "key_sites": "Geelbek Hide, Seeberg Hide, Postberg Reserve (Aug-Sep)",
        "access": "SANParks entry fee; sedan accessible",
        "specials": [
            {"eng": "Black Harrier", "afr": "Witkruisvleivalk", "sci": "Circus maurus"},
            {"eng": "Southern Black Korhaan", "afr": "Swartvlerkkorhaan", "sci": "Afrotis afra"},
            {"eng": "Chestnut-banded Plover", "afr": "Rooibandstrandkiewiet", "sci": "Charadrius pallidus"},
            {"eng": "Grey Tit", "afr": "Piet-tjou-tjougrysmees", "sci": "Melaniparus afer"},
            {"eng": "Cape Long-billed Lark", "afr": "Weskuslangbeklewerik", "sci": "Certhilauda curvirostris"},
        ],
    },
    {
        "name": "De Hoop Nature Reserve & Agulhas",
        "coords": [-34.46, 20.53],
        "biome": "Coastal Fynbos, Dunes & Vlei",
        "season": "Aug–Nov (Pairing with whale season)",
        "key_sites": "De Hoop Vlei shoreline, Potberg Vulture Colony, Agulhas Plains",
        "access": "CapeNature day fee; gravel roads inside park",
        "specials": [
            {"eng": "Cape Rockjumper", "afr": "Kaapse berglyster", "sci": "Chaetops frenatus"},
            {"eng": "Agulhas Long-billed Lark", "afr": "Overberglangbeklewerik", "sci": "Certhilauda brevirostris"},
            {"eng": "Cape Sugarbird", "afr": "Kaapse suikervoël", "sci": "Promerops cafer"},
            {"eng": "Orange-breasted Sunbird", "afr": "Oranjeborssuikerbekkie", "sci": "Anthobaphes violacea"},
            {"eng": "Southern Tchagra", "afr": "Grysborstjagra", "sci": "Tchagra tchagra"},
        ],
    },
    {
        "name": "Wilderness & Knysna Forests",
        "coords": [-33.95, 22.6],
        "biome": "Indigenous Afromontane Forest & Lakes",
        "season": "Oct–Mar (Best for forest calls)",
        "key_sites": "Half-collared Kingfisher Trail, Diepwalle Big Tree, Malachite Hide",
        "access": "Permits via SANParks; well-maintained walking trails",
        "specials": [
            {"eng": "Knysna Turaco", "afr": "Knysnaloerie", "sci": "Tauraco corythaix"},
            {"eng": "Knysna Warbler", "afr": "Knysnaruigtesanger", "sci": "Bradypterus sylvaticus"},
            {"eng": "Knysna Woodpecker", "afr": "Knysnaspeg", "sci": "Campethera notata"},
            {"eng": "Olive Bush-Shrike", "afr": "Olyfboslaksman", "sci": "Chlorophoneus olivaceus"},
            {"eng": "Narina Trogon", "afr": "Bosloerie", "sci": "Apaloderma narina"},
        ],
    },
    {
        "name": "Tankwa Karoo National Park",
        "coords": [-32.242, 19.824],
        "biome": "Succulent & Arid Karoo Shrubland",
        "season": "Sep–Nov (Spring peak) & Mar–May",
        "key_sites": "P2250 Road, Oudebaaskraal Dam, Elandskloof Pass",
        "access": "High-clearance vehicle advised; gravel roads",
        "specials": [
            {"eng": "Cinnamon-breasted Warbler", "afr": "Kaneelborssanger", "sci": "Euryptila subcinnamomea"},
            {"eng": "Karoo Eremomela", "afr": "Groenbossanger", "sci": "Eremomela gregalis"},
            {"eng": "Burchell's Courser", "afr": "BloukopDrawwertjie", "sci": "Cursorius rufus"},
            {"eng": "Tractrac Chat", "afr": "Woestynspekvreter", "sci": "Emarginata tractrac"},
            {"eng": "Karoo Lark", "afr": "Karoolewerik", "sci": "Calendulauda albescens"},
            {"eng": "Black-headed Canary", "afr": "swartkopkanarie", "sci": "Serinus alario"},
            {"eng": "Ludwig's Bustard", "afr": "Ludwigse pou", "sci": "Neotis ludwigii"},
        ],
    },
    {
        "name": "Brandvlei & Bushmanland Plains",
        "coords": [-30.466, 20.483],
        "biome": "Arid Gravel Plains & Salt Pans",
        "season": "Aug–Nov (Rain dependent)",
        "key_sites": "R27 roadside stops, Sak River floodplains",
        "access": "Public gravel roads; remote area (carry water/spare tires)",
        "specials": [
            {"eng": "Sclater's Lark", "afr": "Namakwalewerik", "sci": "Spizocorys sclateri"},
            {"eng": "Stark's Lark", "afr": "Woestynlewerik", "sci": "Spizocorys starki"},
            {"eng": "Red Lark", "afr": "Roolewerik", "sci": "Calendulauda burra"},
            {"eng": "Karoo Long-billed Lark", "afr": "Karoolangbeklewerik", "sci": "Certhilauda subcoronata"},
            {"eng": "Bradfield's Swift", "afr": "Muiskleurwindswael", "sci": "Apus bradfieldi"},
        ],
    },
    {
        "name": "Kgalagadi Transfrontier Park",
        "coords": [-25.75, 20.0],
        "biome": "Arid Kalahari Savannah & Red Dunes",
        "season": "Nov–Apr (Migrants & raptors) / May–Sep (Pleasant cold)",
        "key_sites": "Nossob Riverbed, Mata-Mata Loop, Auob River",
        "access": "High clearance / 4x4 recommended; advance SANParks booking",
        "specials": [
            {"eng": "Pygmy Falcon", "afr": "Dwergvalk", "sci": "Polihierax semitorquatus"},
            {"eng": "Burchell's Sandgrouse", "afr": "Gevlekte sandpatrys", "sci": "Pterocles burchelli"},
            {"eng": "Kori Bustard", "afr": "Gompou", "sci": "Ardeotis kori"},
            {"eng": "Fawn-colored Lark", "afr": "Vaalbruinlewerik", "sci": "Calendulauda africanoides"},
            {"eng": "Red-necked Falcon", "afr": "Rooinekvalk", "sci": "Falco chicquera"},
            {"eng": "Sociable Weaver", "afr": "Versamelvoël", "sci": "Philetairus socius"},
        ],
    },
    {
        "name": "Wakkerstroom Grasslands",
        "coords": [-27.35, 30.133],
        "biome": "Highveld Moist High-Altitude Grassland",
        "season": "Oct–Feb (Peak breeding season for larks & pipits)",
        "key_sites": "Vlei Hide, Amersfoort Road, Ossewakop loop",
        "access": "Public roads; local Wakkerstroom Bird Club guide recommended",
        "specials": [
            {"eng": "Rudd's Lark", "afr": "Drakensberglewerik", "sci": "Heteromirafra ruddi"},
            {"eng": "Botha's Lark", "afr": "Vaalrivierlewerik", "sci": "Spizocorys fringillaris"},
            {"eng": "Yellow-breasted Pipit", "afr": "Geelborskoester", "sci": "Anthus chloris"},
            {"eng": "Southern Bald Ibis", "afr": "Kalkoenibis", "sci": "Geronticus calvus"},
            {"eng": "Blue Korhaan", "afr": "Bloukorhaan", "sci": "Eupodotis caerulescens"},
            {"eng": "White-winged Flufftail", "afr": "Witvlerkvleikuiken", "sci": "Sarothrura ayresi"},
        ],
    },
    {
        "name": "Dullstroom & Steenkampsberg",
        "coords": [-25.416, 30.1],
        "biome": "High-altitude Grasslands & Wetlands",
        "season": "Nov–Feb (Breeding season)",
        "key_sites": "Verloren Valei Nature Reserve, Dullstroom Dam",
        "access": "Permit required for Verloren Valei (MTPA)",
        "specials": [
            {"eng": "Wattled Crane", "afr": "Lelkraanvoël", "sci": "Grus carunculata"},
            {"eng": "Grey Crowned Crane", "afr": "Mahem", "sci": "Balearica regulorum"},
            {"eng": "Blue Crane", "afr": "Bloukraanvoël", "sci": "Grus paradisea"},
            {"eng": "Gurney's Sugarbird", "afr": "Rooiborssuikervoël", "sci": "Promerops gurneyi"},
            {"eng": "Buff-streaked Chat", "afr": "Bergklipwagter", "sci": "Campicoloides bifasciatus"},
        ],
    },
    {
        "name": "Sani Pass & Drakensberg",
        "coords": [-29.584, 29.286],
        "biome": "High Afro-alpine Summit Tundra (>2800m)",
        "season": "Nov–Feb (Avoid snow blocking pass in mid-winter)",
        "key_sites": "Kotisephola Pass (Black Mountain), Sani Top plateau",
        "access": "Strictly 4x4 required for Sani Pass; valid passport needed",
        "specials": [
            {"eng": "Drakensberg Rockjumper", "afr": "Oranjeborsberglyster", "sci": "Chaetops aurantius"},
            {"eng": "Drakensberg Siskin", "afr": "Bergpietjiekanarie", "sci": "Crithagra symonsi"},
            {"eng": "Mountain Pipit", "afr": "Bergkoester", "sci": "Anthus hoeschi"},
            {"eng": "Bearded Vulture", "afr": "Baardaasvoël", "sci": "Gypaetus barbatus"},
            {"eng": "Southern Bald Ibis", "afr": "Kalkoenibis", "sci": "Geronticus calvus"},
        ],
    },
    {
        "name": "Mkuze & iSimangaliso (Zululand)",
        "coords": [-27.633, 32.25],
        "biome": "Subtropical Coastal / Sand Forest & Fever Trees",
        "season": "Nov–Feb (Migrants & display) / May–Aug (Pleasant weather)",
        "key_sites": "KuMasinga Hide, Fig Forest Walk, Nsumo Pan",
        "access": "Ezemvelo KZN Wildlife entry; guided walking required for Fig Forest",
        "specials": [
            {"eng": "African Broadbill", "afr": "Breëbek", "sci": "Smithornis capensis"},
            {"eng": "Pink-throated Twinspot", "afr": "Rooskeelkolpensie", "sci": "Hypargos margaritatus"},
            {"eng": "Green Twinspot", "afr": "Groenkolpensie", "sci": "Mandingoa nitidula"},
            {"eng": "Rudd's Apalis", "afr": "Ruddkleinjantjie", "sci": "Apalis ruddi"},
            {"eng": "Neergaard's Sunbird", "afr": "Bloukruissuikerbekkie", "sci": "Cinnyris neergaardi"},
            {"eng": "Woodward's Batis", "afr": "Woodwardbosbontrokkie", "sci": "Batis fratrum"},
            {"eng": "Southern Banded Snake Eagle", "afr": "dubbelbandslangarend", "sci": "Circaetus fasciolatus"},
            {"eng": "Pel's Fishing-Owl", "afr": "visuil", "sci": "Scotopelia peli"},
        ],
    },
    {
        "name": "St Lucia Estuary & Eastern Shores",
        "coords": [-28.383, 32.416],
        "biome": "Coastal Wetland & Dune Forest",
        "season": "Nov–Mar (Wader concentrations & forest birds)",
        "key_sites": "Igwalagwala Trail, Catalina Bay, Cape Vidal road",
        "access": "iSimangaliso Park gate fees; easy sedan access",
        "specials": [
            {"eng": "Livingstone's Turaco", "afr": "Mosambiekloerie", "sci": "Tauraco livingstonii"},
            {"eng": "Mangrove Kingfisher", "afr": "Manglietvisvanger", "sci": "Halcyon senegaloides"},
            {"eng": "Swamp Nightjar", "afr": "Natalse naguil", "sci": "Caprimulgus natalensis"},
            {"eng": "Southern Brown Throated Weaver", "afr": "Bruinkeelwewer", "sci": "Ploceus xanthopterus"},
        ],
    },
    {
        "name": "Punda Maria & Pafuri (Northern Kruger)",
        "coords": [-22.416, 31.316],
        "biome": "Broad-leaved Woodland & Riparian Forest",
        "season": "Nov–Mar (Incredible regional and intra-African migrants)",
        "key_sites": "Luvuvhu River Bridge, Crooks' Corner, Mahonie Loop",
        "access": "SANParks booking; standard vehicle fine on main roads",
        "specials": [
            {"eng": "Pel's Fishing-Owl", "afr": "Pel se visuil", "sci": "Scotopelia peli"},
            {"eng": "Three-banded Courser", "afr": "Driebanddrawwertjie", "sci": "Rhinoptilus cinctus"},
            {"eng": "Crested Guineafowl", "afr": "Kuifkoptarentaal", "sci": "Guttera pucherani"},
            {"eng": "Arnot's Chat", "afr": "Bontpiek", "sci": "Myrmecocichla arnoti"},
            {"eng": "Racket-tailed Roller", "afr": "Knopsterttroupant", "sci": "Coracias spatulatus"},
            {"eng": "Böhm's Bee-eater", "afr": "roeskopbyvreter", "sci": "Merops boehmi"},
        ],
    },
    {
        "name": "Magoebaskloof & Woodbush Forest",
        "coords": [-23.816, 30.0],
        "biome": "Mistbelt Montane Forest",
        "season": "Oct–Feb (Best vocal activity)",
        "key_sites": "Woodbush Drive (Gravel), Swartbos Trail, Debengeni Falls",
        "access": "High clearance recommended for Woodbush Drive after rains",
        "specials": [
            {"eng": "Cape Parrot", "afr": "Woudpapegaai", "sci": "Poicephalus robustus"},
            {"eng": "Black-fronted Bush-Shrike", "afr": "Swartoogboslaksman", "sci": "Chlorophoneus nigrifrons"},
            {"eng": "Orange Ground Thrush", "afr": "Oranjelyster", "sci": "Geokichla gurneyi"},
            {"eng": "Chorister Robin-Chat", "afr": "Lawaaimakerjanfrederik", "sci": "Cossypha dichroa"},
        ],
    },
    {
        "name": "Nylsvley Nature Reserve",
        "coords": [-24.65, 28.666],
        "biome": "Floodplain Wetland & Broadleaf Acacia",
        "season": "Jan–Apr (Post-rain flood events are spectacular)",
        "key_sites": "Vogelfontein embankment, Kingfisher Hide, Dabchick Hide",
        "access": "Day entry fee at reserve gate; walking friendly",
        "specials": [
            {"eng": "Striped Crake", "afr": "Gestreepte riethaan", "sci": "Aenigmatolimnas marginalis"},
            {"eng": "Lesser Moorhen", "afr": "Kleinwaterhoender", "sci": "Paragallinula angulata"},
            {"eng": "Dwarf Bittern", "afr": "Dwergrietreier", "sci": "Botaurus sturmii"},
            {"eng": "Rufous-bellied Heron", "afr": "Rooipensreier", "sci": "Ardeola rufiventris"},
        ],
    },
    {
        "name": "Marievale Bird Sanctuary (Nigel)",
        "coords": [-26.353, 28.514],
        "biome": "Highveld Wetland & Marsh",
        "season": "Oct–Mar (Best for rails & crakes)",
        "key_sites": "Hadeda Hide, Flamingo Hide, Causeway Road",
        "access": "Free public access; easy sedan access",
        "specials": [
            {"eng": "African Rail", "afr": "Grootriethaan", "sci": "Rallus caerulescens"},
            {"eng": "Red-chested Flufftail", "afr": "Rooiborsvleikuiken", "sci": "Sarothrura rufa"},
            {"eng": "Baillon's Crake", "afr": "Kleinriethaan", "sci": "Zapornia pusilla"},
            {"eng": "Marsh Owl", "afr": "Vlei-uil", "sci": "Asio capensis"},
            {"eng": "Greater Painted-snipe", "afr": "Goudsnip", "sci": "Rostratula benghalensis"},
        ],
    },
    {
        "name": "Suikerbosrand Nature Reserve",
        "coords": [-26.502, 28.232],
        "biome": "Highveld Ridge & Protea Woodland",
        "season": "Sep–Feb (Spring/Summer displays)",
        "key_sites": "Cheetah Trail, Diepkloof Farmstead, Tourist Drive",
        "access": "Gauteng Provincial Reserve fee; paved circular drive",
        "specials": [
            {"eng": "Sentinel Rock Thrush", "afr": "Langtoonkliplyster", "sci": "Monticola explorator"},
            {"eng": "Blue Korhaan", "afr": "Bloukorhaan", "sci": "Eupodotis caerulescens"},
            {"eng": "Fairy Flycatcher", "afr": "Fee-vlieëvanger", "sci": "Stenostira scita"},
            {"eng": "Cape Grassbird", "afr": "Grasvoël", "sci": "Sphenoeacus afer"},
        ],
    },
    {
        "name": "Barberspan Bird Sanctuary",
        "coords": [-26.55, 25.583],
        "biome": "Perennial Alkaline Lake & Kalahari Thornveld",
        "season": "Year-round (Waterfowl non-breeding peak in winter)",
        "key_sites": "Main Lake Shoreline, Angling Club Area",
        "access": "North West Parks entry fee",
        "specials": [
            {"eng": "Great White Pelican", "afr": "Witpelikaan", "sci": "Pelecanus onocrotalus"},
            {"eng": "South African Shelduck", "afr": "Kopereend", "sci": "Tadorna cana"},
            {"eng": "Goliath Heron", "afr": "Reusereier", "sci": "Ardea goliath"},
            {"eng": "Pink-backed Pelican", "afr": "Kleinpelikaan", "sci": "Pelecanus rufescens"},
        ],
    },
    {
        "name": "Kamfers Dam (Kimberley)",
        "coords": [-28.675, 24.764],
        "biome": "Endorheic Salt Pan",
        "season": "Sep–Mar (Flamingo breeding activity)",
        "key_sites": "Railroad embankment view, Northern Pan shore",
        "access": "Roadside viewing; optics/spotting scope required",
        "specials": [
            {"eng": "Lesser Flamingo", "afr": "Kleinflamink", "sci": "Phoeniconaias minor"},
            {"eng": "Greater Flamingo", "afr": "Grootflamink", "sci": "Phoenicopterus roseus"},
            {"eng": "Chestnut-banded Plover", "afr": "Rooibandstrandkiewiet", "sci": "Charadrius pallidus"},
            {"eng": "Burchell's Courser", "afr": "Bloukopdrawwertjie", "sci": "Cursorius rufus"},
        ],
    },
    {
        "name": "Ndumo Game Reserve",
        "coords": [-26.915, 32.25],
        "biome": "Subtropical Floodplain & Fever Tree Forest",
        "season": "Nov–Mar (Peak bird activity & migrants)",
        "key_sites": "Nyamithi Pan, Pongola Riverine Forest",
        "access": "Ezemvelo KZN Wildlife entry; guided walking/drives mandatory",
        "specials": [
            {"eng": "Pel's Fishing-Owl", "afr": "visuil", "sci": "Scotopelia peli"},
            {"eng": "Southern Banded Snake Eagle", "afr": "dubbelbandslangarend", "sci": "Circaetus fasciolatus"},
            {"eng": "African Broadbill", "afr": "Breëbek", "sci": "Smithornis capensis"},
            {"eng": "Gorgeous Bush-Shrike", "afr": "Konkoit", "sci": "Telophorus viridis"},
            {"eng": "Pink-throated Twinspot", "afr": "Rooskeelkolpensie", "sci": "Hypargos margaritatus"},
        ],
    },
    {
        "name": "Giant's Castle (Drakensberg)",
        "coords": [-29.268, 29.488],
        "biome": "High Escarpment & Montane Grassland",
        "season": "May–Sep (Vulture Hide peak) & Nov–Feb (Songbirds)",
        "key_sites": "Vulture Restaurant Hide, Main Camp Contour Loop",
        "access": "Advance booking needed for Vulture Hide via KZN Wildlife",
        "specials": [
            {"eng": "Bearded Vulture", "afr": "Baardaasvoël", "sci": "Gypaetus barbatus"},
            {"eng": "Cape Vulture", "afr": "Kransaasvoël", "sci": "Gyps coprotheres"},
            {"eng": "Drakensberg Rockjumper", "afr": "Oranjeborsberglyster", "sci": "Chaetops aurantius"},
            {"eng": "Drakensberg Siskin", "afr": "Bergpietjiekanarie", "sci": "Crithagra symonsi"},
        ],
    },
    {
        "name": "Mapungubwe National Park",
        "coords": [-22.246, 29.341],
        "biome": "Limpopo Riverine Forest & Baobab Woodland",
        "season": "Nov–Mar (Migrants & display)",
        "key_sites": "Limpopo Tree Top Boardwalk, Maloutswa Hide",
        "access": "SANParks booking; high-clearance useful for secondary loops",
        "specials": [
            {"eng": "Meyer's Parrot", "afr": "Bosveldpapegaai", "sci": "Poicephalus meyeri"},
            {"eng": "Meves's Starling", "afr": "langstertglansspreeu", "sci": "Lamprotornis mevesii"},
            {"eng": "Tropical Boubou", "afr": "Tropiese waterfiskaal", "sci": "Laniarius major"},
            {"eng": "Three-banded Courser", "afr": "Driebanddrawwertjie", "sci": "Rhinoptilus cinctus"},
        ],
    },
    {
        "name": "Baviaanskloof Mega-Reserve",
        "coords": [-33.68, 24.24],
        "biome": "Valley Thicket & Mountain Fynbos",
        "season": "Sep–Dec (Spring breeding peak)",
        "key_sites": "Grootrivier Poort, Cambria Glen, Grasnek Pass",
        "access": "High clearance / 4x4 mandatory through central wilderness corridor",
        "specials": [
            {"eng": "Knysna Woodpecker", "afr": "Knysnaspeg", "sci": "Campethera notata"},
            {"eng": "Victorin's Warbler", "afr": "Rooiborsruigtesanger", "sci": "Cryptillas victorini"},
            {"eng": "Cape Clapper Lark", "afr": "Kaapse klappertjie", "sci": "Certhilauda apiata"},
            {"eng": "Protea Canary", "afr": "Witvlerkkanarie", "sci": "Crithagra leucoptera"},
        ],
    },
    {
        "name": "Sani Pass & Maloti Highlands",
        "coords": [-29.585, 29.286],
        "biome": "Alpine Grassland & High Scree Slope",
        "season": "Summer (Oct–Mar for breeding activity & migrants)",
        "key_sites": "Sani Pass Summit, Mokhotlong Road, Black Mountain Pass",
        "access": "4x4 required for pass; high-altitude conditions",
        "specials": [
            {"eng": "Drakensberg Rockjumper", "afr": "Oranjeborsberglyster", "sci": "Chaetops aurantius"},
            {"eng": "Drakensberg Siskin", "afr": "Bergpietjiekanarie", "sci": "Crithagra symonsi"},
            {"eng": "Mountain Pipit", "afr": "Bergkoester", "sci": "Anthus hoeschi"},
            {"eng": "Bearded Vulture", "afr": "Baardaasvoël", "sci": "Gypaetus barbatus"},
            {"eng": "Southern Bald Ibis", "afr": "Kalkoenibis", "sci": "Geronticus calvus"},
        ],
    },
    {
        "name": "Rooibank & Namib Gravel Plains",
        "coords": [-23.183, 14.65],
        "biome": "Namib Sand Dunes & Desert Gravel Plains",
        "season": "Year-round (Best early morning before wind/heat)",
        "key_sites": "Kuiseb Riverbed at Rooibank, Swakopmund Gravel Plains",
        "access": "2WD/4WD tracks; gravel road permit required for central Namib plains",
        "specials": [
            {"eng": "Dune Lark", "afr": "Duinlewerik", "sci": "Calendulauda erythrochlamys"},
            {"eng": "Rüppell's Korhaan", "afr": "Woestynkorhaan", "sci": "Eupodotis rueppellii"},
            {"eng": "Gray's Lark", "afr": "Namiblewerik", "sci": "Ammomanopsis grayi"},
            {"eng": "Tractrac Chat", "afr": "Woestynspekvreter", "sci": "Emarginata tractrac"},
        ],
    },
    {
        "name": "Spitzkoppe & Erongo Mountains",
        "coords": [-21.825, 15.201],
        "biome": "Arid Granite Inselberg & Commiphora Scrub",
        "season": "Year-round (Best: May–Sep for cooler hiking)",
        "key_sites": "Spitzkoppe Rest Camp, Erongo Wilderness Lodge trails",
        "access": "Public / Day fee for nature reserves; easy walking",
        "specials": [
            {"eng": "Herero Chat", "afr": "Hererospekvreter", "sci": "Namibornis herero"},
            {"eng": "Rockrunner", "afr": "Rotsvoël", "sci": "Achaetops pycnopygius"},
            {"eng": "Hartlaub's Spurfowl", "afr": "Klipfisant", "sci": "Pternistis hartlaubi"},
            {"eng": "Monteiro's Hornbill", "afr": "Monteirosneushoornvoël", "sci": "Tockus monteiri"},
        ],
    },
    {
        "name": "Etosha National Park (Okaukuejo & Halali)",
        "coords": [-19.18, 15.92],
        "biome": "Arid Acacia Thornveld & Salt Pan Margin",
        "season": "Dry season (May–Oct for waterhole activity)",
        "key_sites": "Okaukuejo waterhole, Halali camp thickets, Nebrownii",
        "access": "Public National Park; standard sedan accessible on main gravel loops",
        "specials": [
            {"eng": "White-tailed Shrike", "afr": "kortstertlaksman", "sci": "Lanioturdus torquatus"},
            {"eng": "Bare-cheeked Babbler", "afr": "Kaalwangkatlagter", "sci": "Turdoides gymnogenys"},
            {"eng": "Rüppell's Parrot", "afr": "Bloupenspapegaai", "sci": "Poicephalus rueppellii"},
            {"eng": "Violet-backed Starling", "afr": "Witborsspreeu", "sci": "Cinnyricinclus leucogaster"},
        ],
    },
    {
        "name": "Okavango Panhandle (Shakawe)",
        "coords": [-18.367, 21.85],
        "biome": "Perennial Riverine Forest & Deep Channels",
        "season": "Year-round (Best: Aug–Dec for breeding/nesting activity)",
        "key_sites": "Drotsky's Cabins, Shakawe River Lodge trails",
        "access": "Private lodge access; boat trips required for river forest targets",
        "specials": [
            {"eng": "Pel's Fishing Owl", "afr": "Visuil", "sci": "Scotopelia peli"},
            {"eng": "African Skimmer", "afr": "Waterploeër", "sci": "Rynchops flavirostris"},
            {"eng": "White-backed Night Heron", "afr": "Witrugnagreier", "sci": "Gorsachius leuconotus"},
            {"eng": "African Pygmy Goose", "afr": "Dwerggans", "sci": "Nettapus auritus"},
        ],
    },
    {
        "name": "Moremi Game Reserve & Central Okavango",
        "coords": [-19.2, 23.35],
        "biome": "Seasonal Floodplain & Riparian Woodland",
        "season": "May–Oct (Flood season for wetland birds)",
        "key_sites": "Xakanaxa Lagoon, Third Bridge, Mboma Island",
        "access": "High-clearance 4x4 mandatory; deep sand and water crossings",
        "specials": [
            {"eng": "Slaty Egret", "afr": "Rooikeelreier", "sci": "Egretta vinaceigula"},
            {"eng": "Wattled Crane", "afr": "Lelkraanvoël", "sci": "Grus carunculata"},
            {"eng": "Lesser Jacana", "afr": "Dwerglangtoon", "sci": "Microparra capensis"},
            {"eng": "Chirping Cisticola", "afr": "Piepende tinktinkie", "sci": "Cisticola pipiens"},
        ],
    },
    {
        "name": "Chobe Riverfront (Kasane)",
        "coords": [-17.817, 25.15],
        "biome": "Major River Sandbars & Floodplain Grassland",
        "season": "Aug–Nov (Exposed sandbars for nesting skimmers)",
        "key_sites": "Chobe National Park Riverboat Loop, Sedudu Island",
        "access": "Boat cruises highly recommended; 4x4 for river track",
        "specials": [
            {"eng": "African Skimmer", "afr": "Waterploeër", "sci": "Rynchops flavirostris"},
            {"eng": "Long-toed Lapwing", "afr": "Witvlerkkiewiet", "sci": "Vanellus crassirostris"},
            {"eng": "Luapula Cisticola", "afr": "Luapulatinktinkie", "sci": "Cisticola luapula"},
            {"eng": "Southern Carmine Bee-eater", "afr": "Rooiborsbyvreter", "sci": "Merops nubicoides"},
        ],
    },
]

# ==============================================================================
# HELPERS
# ==============================================================================
def norm(text):
    """Lower-case, strip accents and punctuation: 'Hoëveld-klappertjie' -> 'hoeveldklappertjie'."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_text(path):
    """Read a CSV, trying the encodings spreadsheet exports commonly use."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    # Some Excel exports end lines with \r\r\n
    return text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def read_csv_rows(path):
    text = read_text(path)
    first_line = text.split("\n", 1)[0]
    delimiter = max([",", ";", "\t"], key=first_line.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    return reader.fieldnames, list(reader)


def find_column(headers, keys):
    lowered = [h.strip().lower() for h in headers]
    for key in keys:
        if key in lowered:
            return headers[lowered.index(key)]
    return None


MONTH_NAMES = {"jan": 1, "feb": 2, "mar": 3, "mrt": 3, "maa": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12}


def parse_date(value):
    """Return the date as an integer YYYYMMDD. Accepts 2023-05-14, 14/05/2023 (day first, as in
    South Africa, unless that's impossible), 14 May 2023, 14-Mei-2023 and May 14, 2023, with or
    without a time after it."""
    s = re.sub(r"^[A-Za-z]+,\s*", "", (value or "").strip())  # drop a leading weekday ("Sun, ...")
    if not s:
        return None
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b", s)
        if m:
            a, b, y = int(m[1]), int(m[2]), int(m[3])
            y += 2000 if y < 100 else 0
            d, mo = (a, b) if a > 12 or b <= 12 else (b, a)
        else:
            m = re.match(r"^(\d{1,2})[\s\-/.]+([A-Za-z]{3,})\.?[\s\-/.,]+(\d{4})", s)
            if m and m[2][:3].lower() in MONTH_NAMES:
                d, mo, y = int(m[1]), MONTH_NAMES[m[2][:3].lower()], int(m[3])
            else:
                m = re.match(r"^([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
                if not (m and m[1][:3].lower() in MONTH_NAMES):
                    return None
                mo, d, y = MONTH_NAMES[m[1][:3].lower()], int(m[2]), int(m[3])
    try:
        datetime.date(y, mo, d)
    except ValueError:
        return None
    return y * 10000 + mo * 100 + d


def parse_number(value):
    s = (value or "").strip()
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def parse_coordinate(value):
    """One coordinate as decimal degrees: -25.1234, S25.1234, S 25° 07.404', 25°07'24.2"S and so on."""
    s = (value or "").strip()
    if not s:
        return None
    n = parse_number(s)
    if n is not None:
        return n
    up = s.upper().replace(",", ".")
    nums = re.findall(r"\d+(?:\.\d+)?", up)
    if not nums or len(nums) > 3:
        return None
    v = float(nums[0]) + (float(nums[1]) / 60 if len(nums) > 1 else 0) + (float(nums[2]) / 3600 if len(nums) > 2 else 0)
    hemi = re.findall(r"[NSEW]", re.sub(r"DEG|SEC|MIN", "", up))
    negative = up.lstrip().startswith("-") or (hemi and hemi[-1] in "SW")
    return -v if negative else v


def parse_gps(value):
    """A latitude/longitude pair from one GPS column, in decimal or degrees-minutes form."""
    s = (value or "").strip()
    if not s:
        return None, None
    m = re.match(r"^\s*(-?\d+\.\d+)\s*[,;\s]\s*(-?\d+\.\d+)\s*$", s)
    if m:
        return float(m[1]), float(m[2])
    up = s.upper()
    m = re.match(r"^\s*([NS][^EW]*?)\s*[,;]?\s*([EW].*)$", up) or re.match(r"^(.*?[NS])\s*[,;]?\s*(.*?[EW])\s*$", up)
    if m:
        return parse_coordinate(m[1]), parse_coordinate(m[2])
    parts = re.split(r"[;]|,(?=\s)", s)
    if len(parts) == 2:
        return parse_coordinate(parts[0]), parse_coordinate(parts[1])
    return None, None


# ==============================================================================
# 1. CHOOSE AND LOAD THE SIGHTINGS FILES (eBird, Roberts or any similar CSV)
# ==============================================================================
def choose_files():
    """Open a file picker (several files can be selected): the native macOS dialog, or tkinter elsewhere."""
    if sys.platform == "darwin":
        script = [
            'set picked to (choose file with prompt "Select your sightings CSV file(s): eBird and/or Roberts" with multiple selections allowed)',
            'set out to ""',
            'repeat with f in picked',
            'set out to out & POSIX path of f & linefeed',
            'end repeat',
            'return out',
        ]
        cmd = ["osascript"]
        for line in script:
            cmd += ["-e", line]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return [p for p in proc.stdout.splitlines() if p.strip()] if proc.returncode == 0 else []
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        paths = filedialog.askopenfilenames(title="Select your sightings CSV file(s)", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        root.destroy()
        return list(paths)
    except Exception:
        return []


def read_table(path):
    """Read a CSV, skipping any title lines an app puts above the column names."""
    if Path(path).suffix.lower() in (".xlsx", ".xls", ".numbers"):
        raise ValueError(f"{Path(path).name} is a spreadsheet file. Open it and save or export it as CSV first.")
    lines = read_text(path).split("\n")
    start = 0
    for i, line in enumerate(lines[:15]):
        delim = max([",", ";", "\t"], key=line.count)
        cells = [c.strip() for c in next(csv.reader([line], delimiter=delim), [])]
        if find_column(cells, ALIASES["date"]) and (find_column(cells, ALIASES["sci"]) or find_column(cells, ALIASES["com"])):
            start = i
            break
    delimiter = max([",", ";", "\t"], key=lines[start].count)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    return reader.fieldnames, list(reader)


def load_sightings(path, src=0, overrides=None):
    headers, rows = read_table(path)
    col = {k: find_column(headers, v + EXTRA_ALIASES.get(k, [])) for k, v in ALIASES.items()}
    for key, name in (overrides or {}).items():
        match = next((h for h in headers if h.lower() == name.strip().lower()), None)
        if not match:
            raise ValueError(f"--column {key}={name}: there's no column called '{name}' in {Path(path).name}. Columns found: {', '.join(headers)}")
        col[key] = match
    # Any other name columns (a Roberts list can carry English and Afrikaans side by side)
    extra_cols = [h for h in headers if h.lower() in NAME_COLUMNS and h not in (col["com"], col["sci"])]

    missing = []
    if not col["sci"] and not col["com"]:
        missing.append("a species name column (for example SciName, ComName, Species, English Name or Afrikaans Name)")
    if not col["date"]:
        missing.append("a date column (for example Date or Date Seen)")
    if missing:
        raise ValueError(f"{Path(path).name} is missing {' and '.join(missing)}. Columns found: {', '.join(headers) or 'none'}. "
                         "If the columns are there under other names, use --column, e.g. --column date=\"When\".")

    sightings, skipped = [], 0
    for i, row in enumerate(rows):
        get = lambda k: (row.get(col[k]) or "").strip() if col[k] else ""
        sci, com = get("sci"), get("com")
        extra = [(row.get(h) or "").strip() for h in extra_cols if (row.get(h) or "").strip()]
        if not com and extra:
            com, extra = extra[0], extra[1:]
        day = parse_date(get("date"))
        if not (sci or com) or day is None:
            skipped += 1
            continue
        lat = parse_coordinate(get("lat")) if col["lat"] else None
        lon = parse_coordinate(get("lon")) if col["lon"] else None
        if (lat is None or lon is None) and col["gps"]:
            lat, lon = parse_gps(get("gps"))
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
            lat = lon = None
        sightings.append({
            "row": i, "src": src, "raw": row, "sci": sci, "com": com, "extra": extra, "day": day,
            "loc": get("loc") or "Unnamed location", "note": get("note"),
            "lat": lat, "lon": lon, "filled": False,
        })
    if not sightings:
        raise ValueError(f"No usable rows were found in {Path(path).name}. Check that species names and dates are filled in.")
    used = {"species": col["com"], "scientific": col["sci"], "other names": ", ".join(extra_cols) or None, "date": col["date"],
            "place": col["loc"], "coordinates": " / ".join(c for c in (col["lat"], col["lon"]) if c) or col["gps"], "notes": col["note"]}
    return headers, sightings, skipped, used


# ==============================================================================
# 2. COORDINATES AND LOCATION GROUPS
# ==============================================================================
def fill_missing_coordinates(sightings, radius_deg=0.035):
    """Give sightings without coordinates a point near a known location named in the Location field.
    The scatter is seeded from the row, so the same CSV always gives the same map."""
    filled = 0
    for s in sightings:
        if s["lat"] is not None:
            continue
        for name, (lat, lon) in MISSING_LOCATION_CENTERS.items():
            if name.lower() in s["loc"].lower():
                rnd = random.Random(f"{s['loc']}|{s['row']}")
                s["lat"] = round(lat + rnd.uniform(-radius_deg, radius_deg), 5)
                s["lon"] = round(lon + rnd.uniform(-radius_deg, radius_deg), 5)
                s["filled"] = True
                filled += 1
                break
    return filled


def group_location(name):
    for pattern, group in LOCATION_GROUPS.items():
        if re.search(pattern, name, re.IGNORECASE):
            return group
    return name


# ==============================================================================
# 3. BIRD NAMES: AFRIKAANS, ENGLISH AND SCIENTIFIC
# ==============================================================================
class NameBook:
    """Links every name a species goes by (Afrikaans, English, Roberts VI English, scientific,
    and the names in your own CSV) into one group per species, so names and taxonomy changes
    don't break matching. A name shared by different species in BirdReference.csv is never
    used to link, which stops two species being merged by mistake."""

    def __init__(self):
        self.parent = {}
        self.ambiguous = set()
        self.ref_rows = []          # (afr, eng, sci)
        self.ref_by_group = {}
        self.names_in_group = {}

    def _find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def _union(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self.parent[rb] = ra

    def known(self, key):
        return bool(key) and key in self.parent and key not in self.ambiguous

    def group(self, key):
        return self._find(key)

    def load_reference(self, path):
        headers, rows = read_csv_rows(path)
        c_afr = find_column(headers, ["afrikaans", "afrikaans name"])
        c_eng = find_column(headers, ["english names", "english name", "english"])
        c_rob = next((h for h in headers if h.lower().startswith("roberts")), None)
        c_sci = find_column(headers, ["scientific name", "sciname", "scientific"])
        if not c_sci or not (c_afr or c_eng):
            raise ValueError(f"BirdReference.csv needs Afrikaans, English Names and Scientific Name columns. Found: {', '.join(headers)}")
        entries = []
        seen = set()
        for r in rows:
            afr, eng = (r.get(c_afr) or "").strip(), (r.get(c_eng) or "").strip()
            rob, sci = ((r.get(c_rob) or "").strip() if c_rob else ""), (r.get(c_sci) or "").strip()
            if not (afr or eng):
                continue
            sig = (afr, eng, rob, sci)
            if sig in seen:
                continue
            seen.add(sig)
            entries.append(sig)
        # A name is ambiguous when the rows that use it describe different species: rows that share
        # no other name with each other. Spelling variants of one species (Ludwigpou / Ludwigse Pou)
        # still share a scientific or English name, so they stay linked; old lumped names such as
        # Roberts' "Yellow-nosed Albatross" join two species with nothing else in common, so they don't.
        rows_by_key = {}
        for i, (afr, eng, rob, sci) in enumerate(entries):
            for k in {norm(afr), norm(eng), norm(rob), norm(sci)} - {""}:
                rows_by_key.setdefault(k, []).append(i)
        self.ambiguous = set()
        for k, idxs in rows_by_key.items():
            if len(idxs) < 2:
                continue
            comp = {i: i for i in idxs}
            def root(i):
                while comp[i] != i:
                    comp[i] = comp[comp[i]]
                    i = comp[i]
                return i
            other = {i: {norm(x) for x in (entries[i][0], entries[i][1], entries[i][3])} - {"", k} for i in idxs}
            for x in range(len(idxs)):
                for y in range(x + 1, len(idxs)):
                    if other[idxs[x]] & other[idxs[y]]:
                        comp[root(idxs[y])] = root(idxs[x])
            if len({root(i) for i in idxs}) > 1:
                self.ambiguous.add(k)
        for afr, eng, rob, sci in entries:
            keys = [k for k in (norm(afr), norm(eng), norm(rob), norm(sci)) if k and k not in self.ambiguous]
            for k in keys:
                self._find(k)
            for a, b in zip(keys, keys[1:]):
                self._union(a, b)
            self.ref_rows.append((afr, eng, sci, keys))
        return len(entries)

    def add_own_species(self, *names):
        """Your own rows tie your common name(s) to your scientific name, which bridges eBird's
        current taxonomy to the older names in BirdReference.csv."""
        keys = [k for k in (norm(n) for n in names) if k]
        for k in keys:
            self._find(k)
        for a, b in zip(keys, keys[1:]):
            self._union(a, b)

    def finish(self):
        """Pick display names per species: the first Afrikaans name, and the first English name
        without a bracketed alternative (Hadeda Ibis rather than Hadeda (Hadada) Ibis)."""
        rows_by_group = {}
        for afr, eng, sci, keys in self.ref_rows:
            if keys:
                rows_by_group.setdefault(self._find(keys[0]), []).append((afr, eng, sci))
        self.ref_by_group = {}
        self.names_in_group = {}
        for g, rows in rows_by_group.items():
            afr = next((r[0] for r in rows if r[0]), "")
            eng = next((r[1] for r in rows if r[1] and "(" not in r[1]), "") or next((r[1] for r in rows if r[1]), "")
            sci = next((r[2] for r in rows if r[2]), "")
            self.ref_by_group[g] = (afr, eng, sci)
            self.names_in_group[g] = ({norm(r[0]) for r in rows}, {norm(r[1]) for r in rows})

    def lookup(self, *names):
        """Group for the first name that's known and unambiguous, trying names in order."""
        for n in names:
            k = norm(n)
            if self.known(k):
                return self._find(k)
        return None

    def names_for(self, group):
        return self.ref_by_group.get(group)

    def display_fallback(self, com, sci):
        c, s = norm(com), norm(sci)
        for afr, eng, rsci, keys in self.ref_rows:
            if c and c in (norm(afr), norm(eng)):
                return (afr, eng, rsci)
        for afr, eng, rsci, keys in self.ref_rows:
            if s and s == norm(rsci):
                return (afr, eng, rsci)
        return None

    def sci_lookup(self):
        """Scientific name -> (Afrikaans, English) for naming GBIF species in the page."""
        out = {}
        for afr, eng, sci, keys in self.ref_rows:
            k = norm(sci)
            if k and k not in self.ambiguous and k not in out:
                out[k] = [afr, eng]
        return out


# ==============================================================================
# 4. BUILD THE DATA THE PAGE NEEDS
# ==============================================================================
def km_between(a, b):
    to_r = math.radians
    h = (math.sin(to_r(b["lat"] - a["lat"]) / 2) ** 2
         + math.cos(to_r(a["lat"])) * math.cos(to_r(b["lat"])) * math.sin(to_r(b["lon"] - a["lon"]) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def build_data(sightings, book, have_reference):
    # Link every name each sighting carries, then make one species per name group, so the same
    # bird from an eBird file (scientific name) and a Roberts file (common name only) counts once
    for names in {tuple(n for n in (s["com"], s["sci"], *s["extra"]) if n) for s in sightings}:
        book.add_own_species(*names)
    book.finish()
    species, sp_index = [], {}
    for s in sightings:
        g = book.lookup(s["sci"], s["com"], *s["extra"])
        key = g or ("own:" + (norm(s["sci"]) or norm(s["com"])))
        if key not in sp_index:
            sp_index[key] = len(species)
            species.append({"sci": s["sci"], "com": s["com"] or s["sci"], "group": g})
        sp = species[sp_index[key]]
        if not sp["sci"] and s["sci"]:
            sp["sci"] = s["sci"]
        s["sp"] = sp_index[key]

    # The same sighting logged in two apps: same species, same day, within 10 km (or no coordinates)
    kept, by_key, duplicates = [], {}, 0
    for s in sightings:
        twins = by_key.setdefault((s["sp"], s["day"]), [])
        if any(t["src"] != s["src"] and (t["lat"] is None or s["lat"] is None or km_between(t, s) < 10) for t in twins):
            duplicates += 1
            continue
        twins.append(s)
        kept.append(s)
    sightings[:] = kept

    unresolved = []
    for sp in species:
        names = book.names_for(sp["group"]) if sp["group"] else None
        if not names and have_reference:
            # Names too ambiguous to link on are still fine for display: take the first exact row
            names = book.display_fallback(sp["com"], sp["sci"])
        if names:
            sp["afr"], sp["eng"] = names[0] or sp["com"], names[1] or sp["com"]
            # Keep your own spelling when your CSV already uses one of this species' names
            afr_set, eng_set = book.names_in_group.get(sp["group"], (set(), set()))
            if norm(sp["com"]) in afr_set:
                sp["afr"] = sp["com"]
            elif norm(sp["com"]) in eng_set:
                sp["eng"] = sp["com"]
        else:
            sp["afr"] = sp["eng"] = sp["com"]
            if have_reference:
                unresolved.append(sp)
        if not sp["sci"]:
            sp["sci"] = (names[2] if names and names[2] else "") or sp["com"]

    # First sighting date per species group, for the hotspot specials
    first_seen = {}
    for s in sightings:
        g = species[s["sp"]]["group"] or ("own:" + norm(species[s["sp"]]["sci"]))
        if g not in first_seen or s["day"] < first_seen[g]:
            first_seen[g] = s["day"]
    own_keys = {norm(sp["sci"]) for sp in species} | {norm(sp["com"]) for sp in species}

    # Hotspot target sites with each special marked seen or not
    sites, unresolved_specials = [], []
    for site in HOTSPOTS:
        specials, done = [], set()
        for b in site["specials"]:
            g = book.lookup(b.get("sci", ""), b.get("eng", ""), b.get("afr", ""))
            gid = g or ("special:" + norm(b.get("sci") or b.get("eng")))
            if gid in done:
                continue
            done.add(gid)
            when = first_seen.get(g) if g else None
            if not g:
                # Not in BirdReference.csv: fall back to an exact name match against your own list
                hit = next((n for n in (b.get("sci"), b.get("eng"), b.get("afr")) if norm(n) in own_keys), None)
                when = min((s["day"] for s in sightings if hit and norm(hit) in (norm(s["sci"]), norm(s["com"]))), default=None)
                unresolved_specials.append(b)
            names = book.names_for(g) if g else None
            afr = (names[0] if names and names[0] else b.get("afr", "")) or b.get("eng", "")
            eng = (names[1] if names and names[1] else b.get("eng", "")) or b.get("afr", "")
            specials.append([afr, eng, b.get("sci", ""), when or 0, gid])
        sites.append({
            "n": site["name"], "lat": site["coords"][0], "lng": site["coords"][1],
            "b": site.get("biome", ""), "s": site.get("season", ""), "k": site.get("key_sites", ""),
            "a": site.get("access", ""), "t": specials,
        })
    gids = sorted({x[4] for site in sites for x in site["t"]})
    gid_index = {g: i for i, g in enumerate(gids)}
    for site in sites:
        for x in site["t"]:
            x[4] = gid_index[x[4]]

    # Compact arrays for the page
    order = sorted(range(len(species)), key=lambda i: (species[i]["afr"] or "").lower())
    remap = {old: new for new, old in enumerate(order)}
    places, loc_index, notes, note_index, records = [], {}, [], {}, []
    for s in sightings:
        if s["loc"] not in loc_index:
            loc_index[s["loc"]] = len(places)
            places.append(s["loc"])
        ni = -1
        if s["note"]:
            if s["note"] not in note_index:
                note_index[s["note"]] = len(notes)
                notes.append(s["note"])
            ni = note_index[s["note"]]
        records.append([remap[s["sp"]], loc_index[s["loc"]], s["day"], s["lat"], s["lon"], ni])

    ref = book.sci_lookup()
    for sp in species:  # your own scientific names too, so GBIF names line up with your list
        k = norm(sp["sci"])
        if k and k not in ref:
            ref[k] = [sp["afr"], sp["eng"]]
    # Other scientific names the reference book gives each of your species, so the GBIF heatmap
    # can recognise a bird you've seen when GBIF files it under an older or newer name
    sci_by_group = {sp["group"]: sp["sci"] for sp in species if sp["group"]}
    alt = {}
    for _afr, _eng, rsci, keys in book.ref_rows:
        mine = sci_by_group.get(book.group(keys[0])) if keys else None
        if mine and rsci and norm(rsci) != norm(mine) and rsci not in alt.setdefault(mine, []):
            alt[mine].append(rsci)
    data = {
        "sp": [[species[i]["sci"], species[i]["afr"], species[i]["eng"]] for i in order],
        "loc": places,
        "lg": [group_location(p) for p in places],
        "com": notes,
        "rec": records,
        "sites": sites,
        "ref": ref,
        "alt": alt,
    }
    return data, species, unresolved, unresolved_specials, duplicates


# The page itself. __DATA__ is replaced with your data as JSON.
TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird log map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
:root{
  --ink:#13201A; --paper:#F2F4EF; --sheet:#FFFFFF; --rule:#CBD3C8; --muted:#56655C;
  --bush:#2E5E4E; --weaver:#E3A91B; --weaver-soft:#FBEFCF;
  --need:#C0392B; --part:#D9822B; --done:#2E8B57;
  --serif:"Literata", Georgia, "Times New Roman", serif;
  --sans:"Public Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans)}
button,input,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--weaver);outline-offset:2px}
.app{display:grid;grid-template-columns:390px 1fr;height:100vh}
.panel{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--rule);background:var(--paper)}
.masthead{padding:20px 22px 0}
.masthead h1{font:600 26px/1.15 var(--serif);margin:0;letter-spacing:-0.01em}
.masthead p{margin:4px 0 14px;color:var(--muted);font-size:13.5px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--rule)}
.tabs a{padding:9px 10px 10px;text-decoration:none;color:var(--muted);font-weight:500;border-bottom:3px solid transparent;margin-bottom:-1px}
.tabs a[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--weaver)}
.page{flex:1;overflow-y:auto;padding:18px 22px 28px}
.page[hidden]{display:none}
.block{margin-bottom:22px}
.block h2{font:600 13px/1.3 var(--sans);color:var(--muted);margin:0 0 8px}
.search{position:relative}
.search input{width:100%;height:44px;padding:0 14px;border:1px solid var(--rule);border-radius:10px;background:var(--sheet);font-size:15.5px}
.search input:focus{border-color:var(--bush)}
.suggest{position:absolute;z-index:1000;left:0;right:0;top:48px;margin:0;padding:4px;list-style:none;background:var(--sheet);border:1px solid var(--rule);border-radius:10px;max-height:340px;overflow-y:auto;box-shadow:0 10px 30px rgba(19,32,26,.14)}
.suggest[hidden]{display:none}
.suggest li{display:flex;justify-content:space-between;gap:12px;padding:8px 10px;border-radius:7px;cursor:pointer}
.suggest li[aria-selected="true"],.suggest li:hover{background:var(--weaver-soft)}
.suggest .nm{font-family:var(--serif)}
.suggest .sc{display:block;font:italic 13px/1.3 var(--serif);color:var(--muted)}
.suggest .ct{font-size:12.5px;color:var(--muted);white-space:nowrap;align-self:center}
.species{background:var(--sheet);border:1px solid var(--rule);border-radius:12px;padding:16px 16px 14px}
.species h3{font:600 24px/1.15 var(--serif);margin:0}
.species .sci{font:italic 15px/1.3 var(--serif);color:var(--muted);margin:2px 0 14px}
.facts{display:grid;grid-template-columns:repeat(2,1fr);gap:10px 14px;margin:0 0 14px}
.facts dt{font-size:12px;color:var(--muted)}
.facts dd{margin:0;font-weight:600;font-variant-numeric:tabular-nums}
.months{display:grid;grid-template-columns:repeat(12,1fr);gap:3px}
.months span{height:22px;border-radius:3px;background:var(--paper);position:relative}
.months span i{position:absolute;inset:0;border-radius:3px;background:var(--weaver)}
.mlabels{display:grid;grid-template-columns:repeat(12,1fr);gap:3px;font-size:10.5px;color:var(--muted);text-align:center;margin-top:3px}
.linkbtn{background:none;border:0;padding:0;color:var(--bush);text-decoration:underline;cursor:pointer;font-size:13.5px;margin-top:12px}
.hint{color:var(--muted);font-size:13.5px;margin:0}
.toggle{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--rule)}
.toggle:first-of-type{border-top:0}
.toggle input[type=checkbox]{width:18px;height:18px;margin:2px 0 0;accent-color:var(--bush)}
.toggle b{font-weight:500;display:block}
.toggle small{color:var(--muted);font-size:12.5px;display:block}
select{height:36px;border:1px solid var(--rule);border-radius:8px;background:var(--sheet);padding:0 8px;width:100%;margin-top:6px}
.row{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--muted);margin-top:10px}
.row input[type=range]{flex:1;accent-color:var(--bush)}
.status{margin:10px 0 0;padding:0;list-style:none;font-size:12.5px;color:var(--muted)}
.status li{padding:2px 0}
.status.warn{background:var(--weaver-soft);color:var(--ink);border-radius:8px;padding:8px 10px}
.ramp{height:8px;border-radius:4px;background:linear-gradient(90deg,#FFE600,#FFA200,#F04A00,#B10000);margin-top:6px}
.ramp-l{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
.list{list-style:none;margin:0;padding:0}
.list li button{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;width:100%;text-align:left;background:none;border:0;border-top:1px solid var(--rule);padding:9px 2px;cursor:pointer}
.list li:first-child button{border-top:0}
.list li button:hover{background:var(--sheet)}
.list .dt{font-variant-numeric:tabular-nums;color:var(--muted);font-size:13px;white-space:nowrap}
.list .pl{font-size:14px}
.list .cm{grid-column:2;font-size:12.5px;color:var(--muted);font-style:italic}
.lifenum{font:600 56px/1 var(--serif);margin:0;font-variant-numeric:lining-nums tabular-nums}
.lifecap{color:var(--muted);margin:4px 0 12px;font-size:13.5px}
#cum{width:100%;height:auto;display:block}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips button{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--rule);background:var(--sheet);border-radius:999px;padding:4px 10px;font-size:13px;cursor:pointer;font-variant-numeric:tabular-nums}
.chips button[aria-pressed="true"]{border-color:var(--ink);background:var(--ink);color:#fff}
.chips i{width:10px;height:10px;border-radius:50%;border:1px solid rgba(19,32,26,.5)}
.llist button{grid-template-columns:44px 1fr !important}
.llist .no{font:600 15px/1.4 var(--serif);color:var(--muted);font-variant-numeric:tabular-nums}
.llist .nm{font-family:var(--serif)}
.llist .sub{grid-column:2;font-size:12.5px;color:var(--muted)}
.llist .sub em{font-family:var(--serif)}
.keyrow{display:flex;gap:8px}
.keyrow input{flex:1;min-width:0;height:40px;padding:0 12px;border:1px solid var(--rule);border-radius:10px;background:var(--sheet)}
.keyrow button,.actions button{height:40px;padding:0 14px;border:1px solid var(--rule);border-radius:10px;background:var(--sheet);cursor:pointer;font-weight:500}
.actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.actions .primary{background:var(--ink);color:#fff;border-color:var(--ink)}
.actions button:disabled{opacity:.55;cursor:progress}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px}
.fields label{font-size:12.5px;color:var(--muted)}
.fields label:last-child{grid-column:1 / -1}
.hotlist{list-style:none;margin:0;padding:0}
.hotlist>li{border-top:1px solid var(--rule);padding:10px 0}
.hotlist>li:first-child{border-top:0}
.hotlist .hbtn{display:grid;grid-template-columns:52px 1fr;gap:0 12px;align-items:center;width:100%;text-align:left;background:none;border:0;padding:0;cursor:pointer}
.hotlist .hn{font:600 30px/1 var(--serif);font-variant-numeric:lining-nums tabular-nums;text-align:right}
.hotlist .hname{font:600 15.5px/1.3 var(--serif)}
.hotlist .hsub{grid-column:2;font-size:12.5px;color:var(--muted)}
.hotlist details{margin:6px 0 0 64px;font-size:13.5px}
.hotlist summary{cursor:pointer;color:var(--bush)}
.hotlist details ul{margin:6px 0 6px;padding-left:16px}
.hotlist details li em{font-family:var(--serif);color:var(--muted)}
.hotlist details a{color:var(--bush)}
.hotpin{display:grid;place-items:center;border-radius:50%;background:var(--ink);color:var(--weaver);border:2px solid #fff;font:600 13px/1 var(--sans);box-shadow:0 2px 8px rgba(19,32,26,.35)}
.hotpin.dim{opacity:.35}
.crosshair{position:absolute;left:50%;top:50%;width:26px;height:26px;margin:-13px 0 0 -13px;z-index:450;pointer-events:none}
.crosshair::before,.crosshair::after{content:"";position:absolute;background:var(--ink);box-shadow:0 0 0 1.5px #fff}
.crosshair::before{left:12px;top:0;width:2px;height:26px}
.crosshair::after{top:12px;left:0;height:2px;width:26px}
.crosshair[hidden]{display:none}
.bar{height:4px;background:var(--rule);border-radius:2px;margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:var(--bush);transition:width .2s}
.bar[hidden]{display:none}
.splist li button{grid-template-columns:1fr auto !important}
.splist .nm{font-family:var(--serif)}
.splist .sc{grid-column:1;font:italic 12.5px var(--serif);color:var(--muted)}
.splist .ct{grid-row:1 / span 2;grid-column:2;align-self:center;font-size:12.5px;color:var(--muted);text-align:right;white-space:nowrap}
.langrow{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-6px 0 12px}
.seg{display:inline-flex;border:1px solid var(--rule);border-radius:999px;padding:2px;background:var(--sheet)}
.seg button{border:0;background:none;border-radius:999px;padding:4px 12px;font-size:13px;cursor:pointer;color:var(--muted)}
.seg button[aria-pressed="true"]{background:var(--ink);color:#fff}
.species .alt{font:15px/1.3 var(--serif);margin:2px 0 0;color:var(--ink)}
.species .alt + .sci{margin-top:0}
.dash{background:var(--sheet);border:1px solid var(--rule);border-radius:12px;padding:14px 16px}
.dash .nums{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 10px}
.dash .nums b{display:block;font:600 26px/1.1 var(--serif);font-variant-numeric:lining-nums tabular-nums}
.dash .nums span{font-size:12px;color:var(--muted)}
.dash .prog{height:8px;border-radius:4px;background:#F6D9D5;overflow:hidden}
.dash .prog i{display:block;height:100%;background:var(--done)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:var(--muted);margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.sitelist{list-style:none;margin:0;padding:0}
.sitelist li button{display:grid;grid-template-columns:30px 1fr;gap:1px 10px;width:100%;text-align:left;background:none;border:0;border-top:1px solid var(--rule);padding:10px 2px;cursor:pointer}
.sitelist li:first-child button{border-top:0}
.sitelist li button:hover{background:var(--sheet)}
.sitelist .dot{grid-row:1 / span 2;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;color:#fff;font:600 12.5px/1 var(--sans)}
.sitelist .nm{font:600 15px/1.3 var(--serif)}
.sitelist .sub{grid-column:2;font-size:12.5px;color:var(--muted)}
.sitelist li.dim{opacity:.4}
.sitepin{display:grid;place-items:center;border-radius:50%;color:#fff;border:2px solid #fff;font:600 13px/1 var(--sans);box-shadow:0 2px 8px rgba(19,32,26,.35)}
.sitepin.dim{opacity:.3}
.pop .need li{color:var(--need)}
.pop .got li{color:var(--done)}
.pop .grid2{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;font-size:12.5px;margin:6px 0}
.pop .grid2 b{color:var(--muted);font-weight:500}
.pop small{color:var(--muted)}
.tlist button .ct{white-space:nowrap}
#statsMain{position:absolute;inset:0;overflow:auto;background:var(--paper);padding:18px;z-index:1100}
#statsMain[hidden]{display:none}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:16px}
.chart{background:var(--sheet);border:1px solid var(--rule);border-radius:12px;padding:10px 12px;min-height:380px}
.chart.wide{grid-column:1 / -1;min-height:460px}
.chart .plot{width:100%;height:360px}
.chartbar{display:flex;justify-content:flex-end;margin:2px 0 -4px;position:relative;z-index:2}
.chartbar .seg button{font-size:12.5px;padding:4px 10px}
.chart.wide .plot{height:440px}
.chartnote{color:var(--muted);font-size:13.5px;padding:40px 10px;text-align:center}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 14px}
.kpis div{background:var(--sheet);border:1px solid var(--rule);border-radius:10px;padding:10px 12px}
.kpis b{display:block;font:600 24px/1.15 var(--serif);font-variant-numeric:lining-nums tabular-nums}
.kpis span{font-size:12px;color:var(--muted)}
.ytable{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
.ytable th{font-weight:500;color:var(--muted);text-align:right;padding:4px 6px;border-bottom:1px solid var(--rule)}
.ytable td{text-align:right;padding:5px 6px;border-bottom:1px solid var(--rule)}
.ytable th:first-child,.ytable td:first-child{text-align:left}
@media (max-width:820px){.charts{grid-template-columns:1fr}.chart{min-height:320px}}
#map{height:100%;background:#dfe5dc}
.leaflet-container{font:13px/1.45 var(--sans)}
.leaflet-popup-content{margin:12px 14px;min-width:200px;max-width:280px}
.pop h4{font:600 16px/1.2 var(--serif);margin:0}
.pop .sci{font:italic 13px var(--serif);color:var(--muted)}
.pop .meta{color:var(--muted);font-size:12.5px;margin:6px 0 4px}
.pop ul{margin:4px 0 0;padding-left:16px;max-height:160px;overflow:auto}
.pop .tag{display:inline-block;background:var(--weaver-soft);border-radius:4px;padding:1px 6px;font-size:12px;margin-bottom:4px}
.basemap{position:absolute;z-index:500;left:12px;top:12px;background:var(--sheet);border:1px solid var(--rule);border-radius:10px;padding:6px 8px;box-shadow:0 4px 14px rgba(19,32,26,.15)}
.basemap select{margin:0;width:auto;height:30px;border:0;background:transparent}
.mapwrap{position:relative;min-height:0}
@media (max-width:820px){
  .app{grid-template-columns:1fr;grid-template-rows:56vh auto;height:auto}
  .mapwrap{grid-row:1;height:56vh}
  .panel{grid-row:2;border-right:0;border-top:1px solid var(--rule)}
  .page{overflow:visible}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style>
</head>
<body>
<div class="app">
  <aside class="panel">
    <div class="masthead">
      <h1>Bird log</h1>
      <p id="summary"></p>
      <div class="langrow"><span class="hint">Bird names</span><div class="seg" id="langSeg" role="group" aria-label="Bird names"><button type="button" data-v="af">Afrikaans</button><button type="button" data-v="en">English</button></div></div>
      <nav class="tabs" role="tablist" aria-label="Pages">
        <a href="#sightings" id="tab-sightings" role="tab" aria-controls="page-sightings">Sightings</a>
        <a href="#lifers" id="tab-lifers" role="tab" aria-controls="page-lifers">Lifers</a>
        <a href="#hotspots" id="tab-hotspots" role="tab" aria-controls="page-hotspots">Hotspots</a>
        <a href="#stats" id="tab-stats" role="tab" aria-controls="page-stats">Stats</a>
      </nav>
    </div>

    <section class="page" id="page-sightings" role="tabpanel" aria-labelledby="tab-sightings">
      <div class="block">
        <h2><label for="q">Find a species</label></h2>
        <div class="search">
          <input id="q" type="search" autocomplete="off" placeholder="Afrikaans, English or scientific name" role="combobox" aria-expanded="false" aria-controls="suggest" aria-autocomplete="list">
          <ul class="suggest" id="suggest" role="listbox" hidden></ul>
        </div>
      </div>

      <div class="block" id="speciesBlock" hidden>
        <div class="species">
          <h3 id="spName"></h3>
          <p class="alt" id="spAlt"></p>
          <p class="sci" id="spSci"></p>
          <dl class="facts">
            <div><dt>Sightings</dt><dd id="fN"></dd></div>
            <div><dt>Map points</dt><dd id="fP"></dd></div>
            <div><dt>First seen</dt><dd id="fF"></dd></div>
            <div><dt>Last seen</dt><dd id="fL"></dd></div>
          </dl>
          <div class="months" id="months" role="img"></div>
          <div class="mlabels"><span>J</span><span>F</span><span>M</span><span>A</span><span>M</span><span>J</span><span>J</span><span>A</span><span>S</span><span>O</span><span>N</span><span>D</span></div>
          <button class="linkbtn" id="clear" type="button">Show all species again</button>
        </div>
      </div>

      <div class="block" id="allBlock">
        <p class="hint">The map shows every sighting in your log. Search for a species to see only its locations and compare them with public distribution data.</p>
      </div>

      <div class="block">
        <h2>Show sightings as</h2>
        <div class="seg" id="sDisp" role="group" aria-label="Show sightings as"><button type="button" data-v="points">Points</button><button type="button" data-v="heat">Heatmap</button></div>
      </div>

      <div class="block">
        <h2>Distribution overlays</h2>
        <label class="toggle">
          <input type="checkbox" id="ovRange">
          <span><b>Range map</b><small>Expert range polygon from iNaturalist, where one exists</small></span>
        </label>
        <label class="toggle">
          <input type="checkbox" id="ovRecords">
          <span><b>Public records</b><small>Density of other observers' records, served by GBIF</small></span>
        </label>
        <label for="ovSource" class="hint" style="display:block;margin-top:2px">Records source</label>
        <select id="ovSource">
          <option value="abap">SABAP2 / African Bird Atlas</option>
          <option value="ebird">eBird</option>
          <option value="inat">iNaturalist research grade</option>
          <option value="all">All GBIF datasets</option>
        </select>
        <div id="recLegend" hidden>
          <div class="ramp"></div>
          <div class="ramp-l"><span>Fewer records</span><span>More records</span></div>
        </div>
        <div class="row"><label for="ovOpacity">Overlay opacity</label><input type="range" id="ovOpacity" min="10" max="100" step="5" value="65"><span id="ovOpacityOut">65%</span></div>
        <ul class="status" id="ovStatus" aria-live="polite"><li>Pick a species to load distribution overlays.</li></ul>
      </div>

      <div class="block" id="whereBlock" hidden>
        <h2 id="whereTitle">Where you saw it</h2>
        <ul class="list" id="sightList"></ul>
      </div>
    </section>

    <section class="page" id="page-lifers" role="tabpanel" aria-labelledby="tab-lifers" hidden>
      <div class="block">
        <p class="lifenum" id="lifeTotal"></p>
        <p class="lifecap" id="lifeCap"></p>
        <svg id="cum" viewBox="0 0 340 130" role="img" aria-labelledby="cumTitle"><title id="cumTitle">New lifers per year with the cumulative life list</title></svg>
      </div>
      <div class="block">
        <h2>Show lifers as</h2>
        <div class="seg" id="lDisp" role="group" aria-label="Show lifers as"><button type="button" data-v="points">Points</button><button type="button" data-v="heat">Heatmap</button></div>
      </div>
      <div class="block">
        <h2>Filter by year</h2>
        <div class="chips" id="yearChips"></div>
      </div>
      <div class="block">
        <h2 id="lifeListTitle">Life list in order</h2>
        <ol class="list llist" id="lifeList"></ol>
      </div>
    </section>
    <section class="page" id="page-hotspots" role="tabpanel" aria-labelledby="tab-hotspots" hidden>
      <div class="block">
        <div class="seg" id="hsMode" role="group" aria-label="Hotspot view"><button type="button" data-v="sites">Target sites</button><button type="button" data-v="heat">Unseen species heatmap</button></div>
      </div>

      <div id="hsSites">
        <div class="block">
          <div class="dash">
            <h2 style="margin-bottom:10px">Regional target dashboard</h2>
            <div class="nums"><div><b id="dTotal"></b><span>specials tracked</span></div><div><b id="dSeen" style="color:var(--done)"></b><span id="dPct">seen</span></div><div><b id="dNeed" style="color:var(--need)"></b><span>still needed</span></div></div>
            <div class="prog" role="img" id="dBar"><i id="dBarFill"></i></div>
            <div class="legend"><span><i style="background:var(--need)"></i>None seen yet</span><span><i style="background:var(--part)"></i>Some seen</span><span><i style="background:var(--done)"></i>All seen</span></div>
          </div>
        </div>
        <div class="block">
          <h2>Show</h2>
          <div class="seg" id="siteFilter" role="group" aria-label="Which sites"><button type="button" data-v="all">All sites</button><button type="button" data-v="todo">Still to do</button><button type="button" data-v="done">Completed</button></div>
        </div>
        <div class="block" id="siteTargetBlock" hidden>
          <div class="species">
            <h3 id="stName"></h3>
            <p class="alt" id="stAlt"></p>
            <p class="sci" id="stSci"></p>
            <p class="hint" id="stInfo"></p>
            <button class="linkbtn" id="stClear" type="button">Show all sites again</button>
          </div>
        </div>
        <div class="block">
          <h2 id="siteListTitle">Sites, most targets first</h2>
          <ul class="sitelist" id="siteList"></ul>
        </div>
        <div class="block">
          <h2 id="needTitle">Specials you still need</h2>
          <ul class="list splist tlist" id="needList"></ul>
        </div>
      </div>

      <div id="hsHeat" hidden>
      <div class="block">
        <p class="hint" style="color:var(--ink)">Shades the map by how many bird species have been recorded there that aren't in your log yet, using public records on GBIF: SABAP2 atlas cards, eBird and iNaturalist. Start with all of southern Africa, then zoom in and switch the area to what the map shows for finer squares.</p>
      </div>

      <div class="block">
        <div class="fields">
          <label>Area<select id="hsArea"><option value="sa" selected>All of southern Africa</option><option value="view">What the map shows</option></select></label>
          <label>Grid<select id="hsGrid"><option value="1" selected>1 degree squares</option><option value="0.5">Half-degree squares</option><option value="0.25">Quarter-degree squares</option><option value="0.0833333333">Pentads (zoom in first)</option></select></label>
          <label>Records from<select id="hsSource"><option value="all">All public records</option><option value="abap">SABAP2 atlas only</option><option value="ebird">eBird only</option><option value="inat">iNaturalist only</option></select></label>
          <label>Years<select id="hsYears"><option value="5">Last 5 years</option><option value="10" selected>Last 10 years</option><option value="0">All years</option></select></label>
          <label>Season<select id="hsSeason"><option value="all">All year</option><option value="now">Around this month</option></select></label>
        </div>
        <div class="actions">
          <button type="button" class="primary" id="hsGo">Map species I haven't seen</button>
        </div>
        <p class="hint" id="hsStatus" aria-live="polite" style="margin-top:10px"></p>
        <div class="bar" id="hsBar" hidden><i id="hsBarFill"></i></div>
        <div id="hsLegend" hidden style="margin-top:10px">
          <div class="ramp" style="background:linear-gradient(90deg,#FBEFCF,#E3A91B,#B5651D,#6B2E1A)"></div>
          <div class="ramp-l"><span id="hsLegLo">Few</span><span id="hsLegHi">Many species you haven't seen</span></div>
        </div>
      </div>

      <div class="block" id="hsTargetBlock" hidden>
        <div class="species">
          <h3 id="hsTName"></h3>
          <p class="sci" id="hsTSci"></p>
          <p class="hint" id="hsTInfo"></p>
          <button class="linkbtn" id="hsTClear" type="button">Back to all unseen species</button>
        </div>
      </div>

      <div class="block" id="hsResultsBlock" hidden>
        <h2>Richest areas for you</h2>
        <ol class="hotlist" id="hsList"></ol>
      </div>

      <div class="block" id="hsSpeciesBlock" hidden>
        <h2 id="hsSpTitle">Species you haven't seen in this area</h2>
        <div class="search" style="margin-bottom:8px"><input id="hsFilter" type="search" autocomplete="off" placeholder="Filter by name" aria-label="Filter unseen species"></div>
        <p class="hint" id="hsSpNote" style="margin-bottom:6px"></p>
        <ul class="list splist" id="hsSpList"></ul>
      </div>
      </div>
    </section>

    <section class="page" id="page-stats" role="tabpanel" aria-labelledby="tab-stats" hidden>
      <div class="block"><div class="kpis" id="kpis"></div></div>
      <div class="block">
        <h2>Year by year</h2>
        <table class="ytable"><thead><tr><th>Year</th><th>Species</th><th>Lifers</th><th>Sightings</th></tr></thead><tbody id="ytable"></tbody></table>
      </div>
      <p class="hint">Charts are interactive: hover for details, click legend entries to hide or show years, drag to zoom and double-click to reset.</p>
    </section>
  </aside>

  <div class="mapwrap">
    <div id="map" role="region" aria-label="Map"></div>
    <div id="statsMain" hidden>
      <div class="charts">
        <div class="chart wide"><div class="plot" id="cBigYear"></div></div>
        <div class="chart"><div class="plot" id="cGrowth"></div></div>
        <div class="chart">
          <div class="chartbar"><div class="seg" id="monthMode" role="group" aria-label="Monthly chart shows"><button type="button" data-v="all">Total sightings</button><button type="button" data-v="species">Unique species</button><button type="button" data-v="lifers">Lifers</button></div></div>
          <div class="plot" id="cMonths"></div>
        </div>
        <div class="chart"><div class="plot" id="cTopLoc"></div></div>
        <div class="chart"><div class="plot" id="cTopLifer"></div></div>
      </div>
    </div>
    <div class="basemap"><label for="basemap" class="hint" style="font-size:12px">Basemap</label>
      <select id="basemap">
        <option value="topo">Esri topographic</option>
        <option value="imagery">Esri imagery</option>
        <option value="streets">Esri streets</option>
        <option value="gray">Esri light grey</option>
        <option value="natgeo">Esri National Geographic</option>
      </select>
    </div>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js"></script>
<script>
const D = __DATA__;

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const pretty = d => { const s = String(d); return `${+s.slice(6,8)} ${MONTHS[+s.slice(4,6)-1]} ${s.slice(0,4)}`; };
const yearOf = d => Math.floor(d/10000);
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const recs = D.rec.map(r => ({s:r[0], l:r[1], d:r[2], lat:r[3], lon:r[4], c:r[5]}));
const bySp = D.sp.map(() => []);
recs.forEach((r,i) => bySp[r.s].push(i));
const keyOf = r => r.lat.toFixed(4)+','+r.lon.toFixed(4);
function groupByCoord(idxs){
  const m = new Map();
  for (const i of idxs){ if (recs[i].lat === null) continue; const k = keyOf(recs[i]); if(!m.has(k)) m.set(k, []); m.get(k).push(i); }
  return m;
}
const PAGES = ['sightings', 'lifers', 'hotspots', 'stats'];
const pageNow = () => PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'sightings';
const prefs = (() => { try { return JSON.parse(localStorage.getItem('birdlog.prefs') || '{}'); } catch (e) { return {}; } })();
function savePref(k, v){ prefs[k] = v; try { localStorage.setItem('birdlog.prefs', JSON.stringify(prefs)); } catch (e) {} }

/* Bird names: every species carries its scientific, Afrikaans and English name; the toggle picks which leads */
let LANG = prefs.lang === 'en' || prefs.lang === 'af' ? prefs.lang : (D.meta.lang || 'af');
const other = l => l === 'en' ? 'af' : 'en';
const pick = (afr, eng, lang) => (lang === 'en' ? (eng || afr) : (afr || eng)) || '';
const spName = s => pick(D.sp[s][1], D.sp[s][2], LANG) || D.sp[s][0];
const spAlt = s => { const a = pick(D.sp[s][1], D.sp[s][2], other(LANG)); return a && a !== spName(s) ? a : ''; };
const spSci = s => D.sp[s][0];
const keyN = s => norm(s).replace(/[^a-z0-9]/g, '');
const HEAT_OK = typeof L.heatLayer === 'function';

const years = recs.map(r => yearOf(r.d));
$('summary').textContent = `${recs.length.toLocaleString('en-ZA')} sightings of ${D.sp.length} species, ${Math.min(...years)} to ${Math.max(...years)}`;

/* ---------- map ---------- */
const SA_VIEW = [[-35.2, 11.5], [-16.5, 36.5]];
const map = L.map('map', {preferCanvas:true, zoomControl:false, worldCopyJump:true});
map.fitBounds(SA_VIEW);
L.control.zoom({position:'topright'}).addTo(map);
L.control.scale({position:'bottomright', imperial:false}).addTo(map);
map.createPane('dist'); map.getPane('dist').style.zIndex = 350;
map.createPane('labels'); map.getPane('labels').style.zIndex = 380; map.getPane('labels').style.pointerEvents = 'none';

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const ESRI_ATTR = 'Basemap &copy; <a href="https://www.esri.com">Esri</a> and its data providers';
const BASEMAPS = {
  topo:    {url:'World_Topo_Map', max:19},
  imagery: {url:'World_Imagery', max:19, labels:'Reference/World_Boundaries_and_Places'},
  streets: {url:'World_Street_Map', max:19},
  gray:    {url:'Canvas/World_Light_Gray_Base', max:16, labels:'Canvas/World_Light_Gray_Reference'},
  natgeo:  {url:'NatGeo_World_Map', max:16}
};
let baseLayers = [];
function setBasemap(id){
  baseLayers.forEach(l => map.removeLayer(l)); baseLayers = [];
  const b = BASEMAPS[id];
  baseLayers.push(L.tileLayer(`${ESRI}${b.url}/MapServer/tile/{z}/{y}/{x}`, {maxNativeZoom:b.max, maxZoom:19, attribution:ESRI_ATTR}).addTo(map));
  if (b.labels) baseLayers.push(L.tileLayer(`${ESRI}${b.labels}/MapServer/tile/{z}/{y}/{x}`, {pane:'labels', maxNativeZoom:b.max, maxZoom:19}).addTo(map));
}
$('basemap').addEventListener('change', e => setBasemap(e.target.value));
setBasemap('topo');

function go(latlng, zoom){
  if (reduceMotion) map.setView(latlng, zoom); else map.flyTo(latlng, zoom, {duration:0.8});
}
function fit(bounds){
  if (!bounds.isValid()) return;
  if (bounds.getNorthEast().equals(bounds.getSouthWest())) return go(bounds.getCenter(), 12);
  map.fitBounds(bounds, {padding:[40,40], maxZoom:12, animate:!reduceMotion});
}

/* ---------- sightings page ---------- */
const allLayer = L.layerGroup();
const spLayer = L.layerGroup();
let current = null;
let markerByKey = new Map();

(function buildAll(){
  const groups = groupByCoord(recs.map((_,i)=>i));
  for (const [, idxs] of groups){
    const r = recs[idxs[0]];
    L.circleMarker([r.lat, r.lon], {radius:3.5, weight:1, color:'#13201A', fillColor:'#E3A91B', fillOpacity:0.9})
      .bindPopup(() => {
        const names = [...new Set(idxs.map(i => recs[i].s))];
        const items = names.slice(0, 12).map(s => `<li>${esc(spName(s))}</li>`).join('');
        const more = names.length > 12 ? `<li>and ${names.length-12} more</li>` : '';
        return `<div class="pop"><h4>${esc(D.loc[r.l])}</h4><div class="meta">${idxs.length} sighting${idxs.length>1?'s':''}, ${pretty(r.d)}</div><ul>${items}${more}</ul></div>`;
      })
      .addTo(allLayer);
  }
})();

/* Points or a heatmap, as in the old folium maps */
let sDisp = prefs.sDisp === 'heat' ? 'heat' : 'points', lDisp = prefs.lDisp === 'heat' ? 'heat' : 'points';
let allHeat = null, spHeat = null;
const xy = idxs => idxs.filter(i => recs[i].lat !== null).map(i => [recs[i].lat, recs[i].lon]);
function showSightings(){
  [allLayer, spLayer, allHeat, spHeat].forEach(l => l && map.removeLayer(l));
  if (pageNow() !== 'sightings') return;
  if (sDisp === 'heat' && HEAT_OK){
    if (current === null){ if (!allHeat) allHeat = L.heatLayer(xy(recs.map((_, i) => i)), {radius: 16, blur: 11, minOpacity: 0.4}); allHeat.addTo(map); }
    else if (spHeat) spHeat.addTo(map);
  } else (current === null ? allLayer : spLayer).addTo(map);
}

/* search */
const q = $('q'), sugg = $('suggest');
const spIndex = D.sp.map((p,i) => ({i, key:norm(p.join(' ')), names:p.map(x => norm(x))}));
let active = -1, results = [];
function renderSuggest(){
  const v = norm(q.value.trim());
  if (!v){ sugg.hidden = true; q.setAttribute('aria-expanded','false'); return; }
  const words = v.split(/\s+/);
  results = spIndex.filter(x => words.every(w => x.key.includes(w)))
    .sort((a,b) => b.names.some(n => n.startsWith(v)) - a.names.some(n => n.startsWith(v)) || bySp[b.i].length - bySp[a.i].length)
    .slice(0, 12);
  active = results.length ? 0 : -1;
  sugg.innerHTML = results.length
    ? results.map((x,k) => `<li role="option" id="opt${k}" data-i="${x.i}" aria-selected="${k===active}"><span><span class="nm">${esc(spName(x.i))}</span><span class="sc">${spAlt(x.i) ? `<span style="font-style:normal">${esc(spAlt(x.i))}</span>, ` : ''}${esc(spSci(x.i))}</span></span><span class="ct">${bySp[x.i].length}</span></li>`).join('')
    : `<li role="option" aria-disabled="true"><span class="sc" style="font-style:normal">No species in your log matches "${esc(q.value.trim())}". Try the name in the other language or the scientific name.</span></li>`;
  sugg.hidden = false; q.setAttribute('aria-expanded','true');
  q.setAttribute('aria-activedescendant', active >= 0 ? 'opt'+active : '');
}
function moveActive(d){
  if (!results.length) return;
  active = (active + d + results.length) % results.length;
  [...sugg.children].forEach((li,k) => li.setAttribute('aria-selected', k===active));
  q.setAttribute('aria-activedescendant', 'opt'+active);
  sugg.children[active].scrollIntoView({block:'nearest'});
}
q.addEventListener('input', renderSuggest);
q.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown'){ e.preventDefault(); if (sugg.hidden) renderSuggest(); else moveActive(1); }
  else if (e.key === 'ArrowUp'){ e.preventDefault(); moveActive(-1); }
  else if (e.key === 'Enter'){ if (active >= 0 && results[active]) { e.preventDefault(); selectSpecies(results[active].i); } }
  else if (e.key === 'Escape'){ sugg.hidden = true; q.setAttribute('aria-expanded','false'); }
});
sugg.addEventListener('mousedown', e => {
  const li = e.target.closest('li[data-i]'); if (!li) return;
  e.preventDefault(); selectSpecies(+li.dataset.i);
});
q.addEventListener('blur', () => setTimeout(() => { sugg.hidden = true; q.setAttribute('aria-expanded','false'); }, 120));

function selectSpecies(s, opts = {}){
  current = s;
  q.value = spName(s);
  sugg.hidden = true; q.setAttribute('aria-expanded','false');
  const idxs = bySp[s].slice().sort((a,b) => recs[b].d - recs[a].d);
  const dates = idxs.map(i => recs[i].d);

  $('spName').textContent = spName(s);
  $('spAlt').textContent = spAlt(s); $('spAlt').hidden = !spAlt(s);
  $('spSci').textContent = spSci(s);
  $('fN').textContent = idxs.length;
  $('fF').textContent = pretty(Math.min(...dates));
  $('fL').textContent = pretty(Math.max(...dates));

  const mc = Array(12).fill(0);
  dates.forEach(d => mc[Math.floor(d/100)%100 - 1]++);
  const mmax = Math.max(...mc);
  $('months').innerHTML = mc.map((c,k) => `<span title="${MONTHS[k]}: ${c}"><i style="opacity:${c ? 0.2 + 0.8*c/mmax : 0}"></i></span>`).join('');
  $('months').setAttribute('aria-label', 'Sightings by month: ' + mc.map((c,k) => `${MONTHS[k]} ${c}`).join(', '));

  spLayer.clearLayers(); markerByKey = new Map();
  const groups = groupByCoord(idxs);
  $('fP').textContent = groups.size;
  for (const [k, g] of groups){
    const r = recs[g[0]];
    const m = L.circleMarker([r.lat, r.lon], {radius: Math.min(5 + 2*Math.sqrt(g.length-1), 13), weight:2, color:'#13201A', fillColor:'#FFFFFF', fillOpacity:1})
      .bindPopup(() => {
        const rows = g.map(i => {
          const x = recs[i];
          return `<li>${pretty(x.d)}, ${esc(D.loc[x.l])}${x.c >= 0 ? `<br><em>${esc(D.com[x.c])}</em>` : ''}</li>`;
        }).join('');
        return `<div class="pop"><h4>${esc(spName(s))}</h4><div class="sci">${esc(spSci(s))}</div><div class="meta">${g.length} sighting${g.length>1?'s':''} at ${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}</div><ul>${rows}</ul></div>`;
      });
    m.addTo(spLayer); markerByKey.set(k, m);
  }

  $('sightList').innerHTML = idxs.map(i => {
    const r = recs[i];
    return `<li><button type="button" ${r.lat === null ? 'disabled' : `data-k="${keyOf(r)}"`}><span class="dt">${pretty(r.d)}</span><span class="pl">${esc(D.loc[r.l])}${r.lat === null ? ' (no coordinates)' : ''}</span>${r.c >= 0 ? `<span class="cm">${esc(D.com[r.c])}</span>` : ''}</button></li>`;
  }).join('');
  $('whereTitle').textContent = `Where you saw it (${idxs.length})`;

  $('speciesBlock').hidden = false; $('whereBlock').hidden = false; $('allBlock').hidden = true;
  if (spHeat) map.removeLayer(spHeat);
  spHeat = HEAT_OK ? L.heatLayer(xy(idxs), {radius: 16, blur: 11, minOpacity: 0.4}) : null;
  showSightings();
  if (opts.keep) return;
  const pts = xy(idxs);
  if (pts.length) fit(L.latLngBounds(pts));
  refreshOverlays();
}
$('sightList').addEventListener('click', e => {
  const b = e.target.closest('button[data-k]'); if (!b) return;
  const m = markerByKey.get(b.dataset.k); if (!m) return;
  go(m.getLatLng(), Math.max(map.getZoom(), 12));
  setTimeout(() => m.openPopup(), reduceMotion ? 0 : 850);
});
$('clear').addEventListener('click', () => {
  current = null; q.value = '';
  spLayer.clearLayers(); if (spHeat) map.removeLayer(spHeat); spHeat = null; showSightings();
  $('speciesBlock').hidden = true; $('whereBlock').hidden = true; $('allBlock').hidden = false;
  map.fitBounds(SA_VIEW); refreshOverlays(); q.focus();
});

/* overlays */
const SOURCES = {
  abap:  {label:'SABAP2 / African Bird Atlas', ds:'285550d0-3988-4346-81fe-02df62ee29dc'},
  ebird: {label:'eBird', ds:'4fa7b334-ce0d-4e88-aaae-2e0c138d049e'},
  inat:  {label:'iNaturalist research-grade', ds:'50c9509d-22c7-4a22-a47d-8c48425ef4a7'},
  all:   {label:'GBIF (all datasets)', ds:null}
};
const gbifCache = new Map(), inatCache = new Map();
let recLayer = null, rangeLayer = null, ovToken = 0;
const lines = {range:null, rec:null, tiles:null};

async function getJSON(url){
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
async function gbifMatch(sci){
  if (gbifCache.has(sci)) return gbifCache.get(sci);
  let out = null;
  try {
    const j = await getJSON('https://api.gbif.org/v1/species/match?class=Aves&name=' + encodeURIComponent(sci));
    if (j.matchType && j.matchType !== 'NONE' && (j.usageKey || j.acceptedUsageKey))
      out = {key: j.acceptedUsageKey || j.usageKey, name: j.species || j.canonicalName || sci};
  } catch (e) { return {error: e.message}; }
  gbifCache.set(sci, out);
  return out;
}
async function inatMatch(sci){
  if (inatCache.has(sci)) return inatCache.get(sci);
  let out = null;
  try {
    const j = await getJSON('https://api.inaturalist.org/v1/taxa?rank=species&per_page=10&q=' + encodeURIComponent(sci));
    const res = (j.results || []).filter(t => t.iconic_taxon_name === 'Aves');
    const hit = res.find(t => t.name.toLowerCase() === sci.toLowerCase())
      || res.find(t => (t.matched_term || '').toLowerCase() === sci.toLowerCase()) || res[0];
    if (hit) out = {id: hit.id, name: hit.name};
  } catch (e) { return {error: e.message}; }
  inatCache.set(sci, out);
  return out;
}
/* iNaturalist returns an empty transparent tile when a taxon has no range,
   so check the world tile for any drawn pixels before claiming a range exists */
async function inatHasRange(id){
  try {
    const r = await fetch(`https://api.inaturalist.org/v1/taxon_ranges/${id}/0/0/0.png`);
    if (!r.ok) return false;
    const bmp = await createImageBitmap(await r.blob());
    const c = document.createElement('canvas'); c.width = bmp.width; c.height = bmp.height;
    const ctx = c.getContext('2d'); ctx.drawImage(bmp, 0, 0);
    const px = ctx.getImageData(0, 0, c.width, c.height).data;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 0) return true;
    return false;
  } catch (e) { return null; }
}

function renderStatus(warn){
  const el = $('ovStatus');
  el.classList.toggle('warn', !!warn);
  const items = [lines.range, lines.rec, lines.tiles].filter(Boolean);
  el.innerHTML = items.map(l => `<li>${l}</li>`).join('');
}
function say(msg, warn){ lines.range = msg; lines.rec = null; lines.tiles = null; renderStatus(warn); }
function clearOverlays(){
  if (recLayer){ map.removeLayer(recLayer); recLayer = null; }
  if (rangeLayer){ map.removeLayer(rangeLayer); rangeLayer = null; }
}
const opacity = () => +$('ovOpacity').value / 100;
const onSightingsPage = () => pageNow() === 'sightings';

function watchTiles(layer, name, t){
  let ok = 0, bad = 0;
  layer.on('tileload', () => ok++);
  layer.on('tileerror', () => bad++);
  layer.on('load', () => {
    if (t !== ovToken) return;
    if (bad && !ok) { lines.tiles = `${name} tiles didn\u2019t load. Open the file directly in Chrome, Edge, Firefox or Safari while online; previews inside other apps block outside map data.`; renderStatus(true); }
  });
}

async function refreshOverlays(){
  const t = ++ovToken;
  clearOverlays();
  lines.range = lines.rec = lines.tiles = null;
  const wantRange = $('ovRange').checked, wantRec = $('ovRecords').checked;
  $('recLegend').hidden = !(wantRec && current !== null);
  if (current === null){
    if (wantRange || wantRec) say('Search for a species first. Overlays are drawn for one species at a time.', true);
    else say('Pick a species to load distribution overlays.');
    return;
  }
  if (!wantRange && !wantRec){ say('Turn on an overlay to compare your sightings with public data.'); return; }
  const sci = spSci(current);
  if (wantRange) lines.range = 'Loading range map\u2026';
  if (wantRec) lines.rec = 'Loading public records\u2026';
  renderStatus();

  const jobs = [];
  if (wantRange) jobs.push((async () => {
    const n = await inatMatch(sci);
    if (t !== ovToken) return;
    if (!n) { lines.range = `iNaturalist has no bird species matching <em>${esc(sci)}</em>.`; return renderStatus(); }
    if (n.error) { lines.range = `Couldn\u2019t reach iNaturalist (${esc(n.error)}).`; return renderStatus(true); }
    const has = await inatHasRange(n.id);
    if (t !== ovToken) return;
    if (has === false) { lines.range = `iNaturalist has no range map for <em>${esc(n.name)}</em>. Try public records instead.`; return renderStatus(); }
    rangeLayer = L.tileLayer(`https://api.inaturalist.org/v1/taxon_ranges/${n.id}/{z}/{x}/{y}.png`,
      {pane:'dist', zIndex:1, opacity:opacity(), attribution:'Range &copy; <a href="https://www.inaturalist.org">iNaturalist</a>'});
    watchTiles(rangeLayer, 'Range map', t);
    if (onSightingsPage()) rangeLayer.addTo(map);
    lines.range = `Range map from iNaturalist${n.name.toLowerCase() !== sci.toLowerCase() ? `, listed there as <em>${esc(n.name)}</em>` : ''}.`;
    renderStatus();
  })());

  if (wantRec) jobs.push((async () => {
    const g = await gbifMatch(sci);
    if (t !== ovToken) return;
    if (!g) { lines.rec = `GBIF has no taxon matching <em>${esc(sci)}</em>.`; return renderStatus(); }
    if (g.error) { lines.rec = `Couldn\u2019t reach GBIF (${esc(g.error)}).`; return renderStatus(true); }
    const src = SOURCES[$('ovSource').value];
    /* GBIF's precalculated density tiles accept only one filter, so taxon plus dataset needs the ad hoc endpoint */
    const endpoint = src.ds ? 'adhoc' : 'density';
    const ds = src.ds ? `&datasetKey=${src.ds}` : '';
    recLayer = L.tileLayer(`https://api.gbif.org/v2/map/occurrence/${endpoint}/{z}/{x}/{y}@1x.png?srs=EPSG:3857&taxonKey=${g.key}${ds}&bin=hex&hexPerTile=60&style=classic-noborder.poly`,
      {pane:'dist', zIndex:2, tileSize:512, zoomOffset:-1, opacity:opacity(), attribution:'Records &copy; <a href="https://www.gbif.org">GBIF.org</a>'});
    watchTiles(recLayer, 'GBIF', t);
    if (onSightingsPage()) recLayer.addTo(map);
    let count = null;
    try {
      const c = await getJSON(`https://api.gbif.org/v1/occurrence/search?limit=0&taxonKey=${g.key}${ds}&decimalLatitude=-35,-8&decimalLongitude=10,41`);
      if (typeof c.count === 'number') count = c.count;
    } catch (e) {}
    if (t !== ovToken) return;
    const nameNote = g.name.toLowerCase() !== sci.toLowerCase() ? ` GBIF lists it as <em>${esc(g.name)}</em>.` : '';
    lines.rec = count === 0
      ? `${esc(src.label)} has no records of this species in southern Africa. Try another source.${nameNote}`
      : `${count === null ? '' : count.toLocaleString('en-ZA') + ' '}${esc(src.label)} records in southern Africa.${nameNote}`;
    renderStatus();
  })());
  await Promise.all(jobs);
}
['ovRange','ovRecords','ovSource'].forEach(id => $(id).addEventListener('change', refreshOverlays));
$('ovOpacity').addEventListener('input', e => {
  $('ovOpacityOut').textContent = e.target.value + '%';
  [recLayer, rangeLayer].forEach(l => l && l.setOpacity(opacity()));
});

/* ---------- lifers page ---------- */
const order = recs.map((_,i) => i).sort((a,b) => recs[a].d - recs[b].d || a - b);
const seen = new Set(), lifers = [];
for (const i of order){ if (!seen.has(recs[i].s)){ seen.add(recs[i].s); lifers.push(i); } }
const lifeNo = new Map(lifers.map((i,k) => [i, k+1]));
const lYears = [...new Set(lifers.map(i => yearOf(recs[i].d)))].sort();
const y0 = lYears[0], y1 = lYears[lYears.length-1];

const RAMP = ['#1F4E5F','#2E7D5B','#8DB33A','#E3A91B'];
function hex2rgb(h){ return [1,3,5].map(k => parseInt(h.slice(k,k+2),16)); }
function yearColor(y){
  const t = y1 === y0 ? 1 : (y - y0) / (y1 - y0);
  const p = t * (RAMP.length - 1), k = Math.min(Math.floor(p), RAMP.length - 2), f = p - k;
  const a = hex2rgb(RAMP[k]), b = hex2rgb(RAMP[k+1]);
  return '#' + a.map((v,j) => Math.round(v + (b[j]-v)*f).toString(16).padStart(2,'0')).join('');
}

const liferLayer = L.layerGroup();
let liferMarkers = new Map(), yearFilter = null, liferHeat = null;
function showLifers(){
  [liferLayer, liferHeat].forEach(l => l && map.removeLayer(l));
  if (pageNow() !== 'lifers') return;
  (lDisp === 'heat' && liferHeat ? liferHeat : liferLayer).addTo(map);
}

function drawLifers(){
  liferLayer.clearLayers(); liferMarkers = new Map();
  const sel = lifers.filter(i => yearFilter === null || yearOf(recs[i].d) === yearFilter);
  const groups = groupByCoord(sel);
  for (const [k, g] of groups){
    const r = recs[g[0]];
    const m = L.circleMarker([r.lat, r.lon], {radius: Math.min(6 + 1.6*Math.sqrt(g.length-1), 14), weight:1.5, color:'#13201A', fillColor: yearColor(yearOf(r.d)), fillOpacity:0.95})
      .bindPopup(() => {
        const rows = g.map(i => {
          const x = recs[i];
          return `<li><b>#${lifeNo.get(i)}</b> ${esc(spName(x.s))} <span class="sci">${esc(spSci(x.s))}</span><br>${pretty(x.d)}${x.c >= 0 ? `, <em>${esc(D.com[x.c])}</em>` : ''}</li>`;
        }).join('');
        return `<div class="pop"><span class="tag">${g.length} lifer${g.length>1?'s':''}</span><h4>${esc(D.loc[r.l])}</h4><ul>${rows}</ul></div>`;
      });
    m.addTo(liferLayer); liferMarkers.set(k, m);
  }
  $('lifeList').innerHTML = sel.map(i => {
    const r = recs[i];
    return `<li><button type="button" ${r.lat === null ? 'disabled' : `data-k="${keyOf(r)}"`}><span class="no">${lifeNo.get(i)}</span><span class="nm">${esc(spName(r.s))}</span><span class="sub">${spAlt(r.s) ? esc(spAlt(r.s)) + ', ' : ''}<em>${esc(spSci(r.s))}</em><br>${pretty(r.d)}, ${esc(D.loc[r.l])}</span></button></li>`;
  }).join('');
  $('lifeList').setAttribute('start', 1);
  $('lifeListTitle').textContent = yearFilter === null ? 'Life list in order' : `Lifers added in ${yearFilter} (${sel.length})`;
  if (liferHeat) map.removeLayer(liferHeat);
  liferHeat = HEAT_OK ? L.heatLayer(xy(sel), {radius: 18, blur: 12, minOpacity: 0.4}) : null;
  showLifers();
  return sel;
}

function renderChips(){
  const counts = {}; lifers.forEach(i => { const y = yearOf(recs[i].d); counts[y] = (counts[y]||0) + 1; });
  $('yearChips').innerHTML = `<button type="button" data-y="" aria-pressed="${yearFilter===null}">All years</button>` +
    lYears.map(y => `<button type="button" data-y="${y}" aria-pressed="${yearFilter===y}"><i style="background:${yearColor(y)}"></i>${y}<span style="opacity:.7">${counts[y]}</span></button>`).join('');
}
$('yearChips').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  yearFilter = b.dataset.y ? +b.dataset.y : null;
  renderChips();
  const sel = drawLifers();
  if (yearFilter === null) map.fitBounds(SA_VIEW);
  else if (xy(sel).length) fit(L.latLngBounds(xy(sel)));
});
$('lifeList').addEventListener('click', e => {
  const b = e.target.closest('button[data-k]'); if (!b) return;
  const m = liferMarkers.get(b.dataset.k); if (!m) return;
  go(m.getLatLng(), Math.max(map.getZoom(), 12));
  setTimeout(() => m.openPopup(), reduceMotion ? 0 : 850);
});

function renderChart(){
  const counts = {}; lifers.forEach(i => { const y = yearOf(recs[i].d); counts[y] = (counts[y]||0) + 1; });
  const ys = []; for (let y = y0; y <= y1; y++) ys.push(y);
  let run = 0; const cum = ys.map(y => run += (counts[y]||0));
  const W = 340, H = 130, L0 = 4, R0 = 4, T = 20, B = 22, bw = (W - L0 - R0) / ys.length;
  const maxBar = Math.max(...ys.map(y => counts[y]||0)), maxCum = cum[cum.length-1];
  const by = v => T + (H - T - B) * (1 - v / maxBar), cy = v => T + (H - T - B) * (1 - v / maxCum);
  let s = $('cum').querySelector('title').outerHTML;
  s += `<line x1="${L0}" x2="${W-R0}" y1="${H-B}" y2="${H-B}" stroke="#CBD3C8"/>`;
  ys.forEach((y,k) => {
    const c = counts[y]||0, x = L0 + k*bw;
    if (c) s += `<rect x="${(x+bw*0.18).toFixed(1)}" y="${by(c).toFixed(1)}" width="${(bw*0.64).toFixed(1)}" height="${(H-B-by(c)).toFixed(1)}" rx="2" fill="${yearColor(y)}"><title>${y}: ${c} new</title></rect>`;
    if (y === y0 || y === y1 || y % 2 === 0) s += `<text x="${(x+bw/2).toFixed(1)}" y="${H-6}" text-anchor="middle" font-size="9.5" fill="#56655C" font-family="Public Sans, sans-serif">${String(y).slice(2)}</text>`;
  });
  const pts = ys.map((y,k) => `${(L0 + k*bw + bw/2).toFixed(1)},${cy(cum[k]).toFixed(1)}`).join(' ');
  s += `<polyline points="${pts}" fill="none" stroke="#13201A" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>`;
  s += `<text x="${W-R0}" y="${T-8}" text-anchor="end" font-size="10" fill="#13201A" font-family="Public Sans, sans-serif">${maxCum} total</text>`;
  $('cum').innerHTML = s;
}

$('lifeTotal').textContent = lifers.length;
$('lifeCap').textContent = `species on your life list, first logged ${pretty(recs[lifers[0]].d)}. Bars show new species each year; the line is the running total.`;
renderChips(); renderChart(); drawLifers();
/* ---------- hotspots page: heatmap of unseen species from public GBIF records, no account needed ---------- */
const GB = 'https://api.gbif.org/v1/';
const hsPrefs = (() => { try { return JSON.parse(localStorage.getItem('birdlog.hs3') || '{}'); } catch (e) { return {}; } })();
['hsArea','hsGrid','hsSource','hsYears','hsSeason'].forEach(id => {
  if (hsPrefs[id] && [...$(id).options].some(o => o.value === hsPrefs[id])) $(id).value = hsPrefs[id];
  $(id).addEventListener('change', () => { hsPrefs[id] = $(id).value; try { localStorage.setItem('birdlog.hs3', JSON.stringify(hsPrefs)); } catch (e) {} });
});
function loadCache(k){ try { return JSON.parse(localStorage.getItem(k) || '{}'); } catch (e) { return {}; } }
function saveCache(k, v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

/* GBIF may file a bird under a different name from yours (splits, genus changes).
   Each entry: your scientific name -> GBIF names that count as the same bird */
const GBIF_ALIASES = {
  'Upupa epops': ['Upupa africana'],
  'Corypha fasciolata': ['Mirafra fasciolata'],
  'Phalacrocorax carbo': ['Phalacrocorax lucidus'],
  'Thinornis tricollaris': ['Anarhynchus tricollaris', 'Charadrius tricollaris'],
  'Dessonornis caffer': ['Cossypha caffra'],
  'Phoenicopterus roseus': ['Phoenicopterus antiquorum'],
  'Milvus migrans': ['Milvus aegyptius'],
  'Acrocephalus scirpaceus': ['Acrocephalus baeticatus'],
  'Tockus rufirostris': ['Tockus erythrorhynchus'],
  'Torgos tracheliotos': ['Torgos tracheliotus'],
  'Tychaedon coryphoeus': ['Erythropygia coryphoeus'],
  'Curruca subcoerulea': ['Sylvia subcaerulea']
};
const keyCache = loadCache('birdlog.gbifkeys');     /* your scientific name -> GBIF species key */
const nameCache = loadCache('birdlog.gbifnames');   /* GBIF species key -> [scientific, common] */
const cellCache = new Map();                         /* settings + cell -> facet result, for this session */

async function gbif(path, params){
  const u = new URL(GB + path);
  for (const [k, v] of Object.entries(params || {})) {
    if (Array.isArray(v)) v.forEach(x => u.searchParams.append(k, x));
    else if (v !== undefined && v !== null && v !== '') u.searchParams.set(k, v);
  }
  let last;
  for (let attempt = 0; attempt < 3; attempt++){
    try {
      const r = await fetch(u);
      if (r.ok) return r.json();
      last = new Error('GBIF answered ' + r.status);
      if (r.status < 500 && r.status !== 429) break;
    } catch (e) { last = e; }
    await new Promise(res => setTimeout(res, 600 * (attempt + 1)));
  }
  throw last;
}
async function pool(items, n, fn, isCancelled){
  let next = 0; const out = new Array(items.length);
  await Promise.all(Array.from({length: Math.min(n, items.length)}, async () => {
    while (next < items.length && !(isCancelled && isCancelled())){ const k = next++; try { out[k] = await fn(items[k], k); } catch (e) { out[k] = {error: e}; } }
  }));
  return out;
}

/* GBIF resolves synonyms to one accepted species key, which smooths over IOC and Clements name differences */
async function lifeKeySet(onProgress){
  const mine = new Set(D.sp.map(p => p[0]));
  const ALIAS = {};   /* aliases from BirdReference.csv (D.alt) plus the hand-made ones above */
  [D.alt || {}, GBIF_ALIASES].forEach(o => Object.entries(o).forEach(([sci, a]) => { ALIAS[sci] = (ALIAS[sci] || []).concat(a); }));
  const extra = Object.entries(ALIAS).filter(([s]) => mine.has(s)).flatMap(([, a]) => a);
  const todo = [...new Set([...mine, ...extra])].filter(s => !keyCache[s]);   /* also retries names that failed before */
  if (todo.length){
    let done = 0;
    await pool(todo, 8, async sci => {
      const j = await gbif('species/match', {name: sci, class: 'Aves'});
      keyCache[sci] = (j.matchType && j.matchType !== 'NONE') ? (j.speciesKey || j.acceptedUsageKey || j.usageKey || 0) : 0;
      done++; if (done % 10 === 0 || done === todo.length) onProgress(done, todo.length);
    });
    saveCache('birdlog.gbifkeys', keyCache);
  }
  const wanted = new Set([...mine, ...extra]);
  return new Set(Object.entries(keyCache).filter(([s, k]) => k && wanted.has(s)).map(([, k]) => String(k)));
}
async function resolveNames(keys, isCancelled){
  const todo = [...new Set(keys)].filter(k => !nameCache[k]);
  await pool(todo, 8, async k => {
    const j = await gbif('species/' + k);
    nameCache[k] = [j.species || j.canonicalName || j.scientificName || ('GBIF ' + k), j.vernacularName || ''];
  }, isCancelled);
  if (todo.length) saveCache('birdlog.gbifnames', nameCache);
}
const nm = k => nameCache[k] || ['GBIF species ' + k, ''];
const refNames = sci => D.ref[keyN(sci)] || null;
const label = k => { const r = refNames(nm(k)[0]); return (r && pick(r[0], r[1], LANG)) || nm(k)[1] || nm(k)[0]; };
const allNames = k => { const r = refNames(nm(k)[0]); return [nm(k)[0], nm(k)[1], r && r[0], r && r[1]].filter(Boolean).join(' '); };

function cellCode(cell){
  if (Math.abs(cell.step - 1/12) > 1e-6 || cell.n > 0 || cell.w < 0) return null;
  const a = Math.round(-cell.n * 12), b = Math.round(cell.w * 12), f = x => String(x).padStart(2, '0');
  return f(Math.floor(a/12)) + f((a % 12) * 5) + '_' + f(Math.floor(b/12)) + f((b % 12) * 5);
}
const cellName = x => x.place ? x.place : (x.code ? 'Pentad ' + x.code : `${Math.abs(x.c.lat).toFixed(2)}\u00b0${x.c.lat < 0 ? 'S' : 'N'} ${Math.abs(x.c.lng).toFixed(2)}\u00b0${x.c.lng < 0 ? 'W' : 'E'}`);
function seasonMonths(){
  if ($('hsSeason').value !== 'now') return null;
  const m = new Date().getMonth() + 1;
  return [((m + 10) % 12) + 1, m, (m % 12) + 1];
}
const MIN_RECORDS = 1;   /* a species needs at least this many records in a square, to skip one-off vagrants and misidentifications */
const MAX_CELLS = 2081;   /* about one minute of GBIF requests */

const RAMP2 = ['#FBEFCF','#E3A91B','#B5651D','#6B2E1A'];
function rampColor(t){
  const p = Math.max(0, Math.min(1, t)) * (RAMP2.length - 1), k = Math.min(Math.floor(p), RAMP2.length - 2), f = p - k;
  const a = hex2rgb(RAMP2[k]), b = hex2rgb(RAMP2[k+1]);
  return '#' + a.map((v,j) => Math.round(v + (b[j]-v)*f).toString(16).padStart(2,'0')).join('');
}

const hotLayer = L.layerGroup(), pinLayer = L.layerGroup().addTo(hotLayer);
let hsCells = [], hsSpecies = [], hsTarget = null, hsToken = 0, hsRunning = false, hsMarkers = new Map();

const SOUTHERN_AFRICA = L.latLngBounds([-35, 11], [-15, 37]);
$('hsGo').addEventListener('click', () => {
  if (hsRunning){ hsToken++; hsRunning = false; $('hsGo').textContent = 'Map species I haven\u2019t seen'; $('hsBar').hidden = true; $('hsStatus').textContent = 'Stopped. Squares already read are still on the map.'; finishRun(); return; }
  runHeatmap();
});

function settingsKey(){ return [$('hsSource').value, $('hsYears').value, $('hsSeason').value === 'now' ? seasonMonths().join('-') : 'all'].join('|'); }
function progress(done, total){ $('hsBar').hidden = false; $('hsBarFill').style.width = (100 * done / Math.max(total, 1)).toFixed(1) + '%'; }

async function runHeatmap(){
  const t = ++hsToken, st = $('hsStatus'), cancelled = () => t !== hsToken;
  const step = +$('hsGrid').value, wholeRegion = $('hsArea').value === 'sa', b = wholeRegion ? SOUTHERN_AFRICA : map.getBounds();
  const s0 = Math.floor(Math.max(b.getSouth(), -89) / step) * step, w0 = Math.floor(b.getWest() / step) * step;
  const cells = [];
  for (let s = s0; s < Math.min(b.getNorth(), 89); s += step)
    for (let w = w0; w < b.getEast(); w += step)
      cells.push({s, w, n: s + step, e: w + step, step, c: {lat: s + step/2, lng: w + step/2}});
  if (cells.length > MAX_CELLS){
    st.textContent = `The map view needs ${cells.length.toLocaleString('en-ZA')} squares at this grid size, and the limit is ${MAX_CELLS}. ${wholeRegion ? 'Choose 1 degree squares for all of southern Africa, or zoom in and set the area to what the map shows.' : 'Zoom in or choose a larger grid.'}`;
    return;
  }
  if (wholeRegion) map.fitBounds(SOUTHERN_AFRICA);
  hsRunning = true; $('hsGo').textContent = 'Stop';
  hsTarget = null; $('hsTargetBlock').hidden = true;
  const src = SOURCES[$('hsSource').value], yrs = +$('hsYears').value, thisYear = new Date().getFullYear(), months = seasonMonths(), sk = settingsKey();
  try {
    const life = await lifeKeySet((d, n) => { if (!cancelled()){ st.textContent = `Matching your ${n} species to GBIF names (only needed once): ${d} of ${n}`; progress(d, n); } });
    if (cancelled()) return;

    hsCells = []; hotLayer.eachLayer(l => { if (l !== pinLayer) hotLayer.removeLayer(l); }); pinLayer.clearLayers();
    $('hsResultsBlock').hidden = true; $('hsSpeciesBlock').hidden = true;
    const base = {taxonKey: 212, occurrenceStatus: 'PRESENT', hasGeospatialIssue: 'false', limit: 0, facet: 'speciesKey', facetLimit: 2000, facetMincount: MIN_RECORDS};
    if (src.ds) base.datasetKey = src.ds;
    if (yrs) base.year = `${thisYear - yrs + 1},${thisYear}`;
    if (months) base.month = months;
    let done = 0, runMax = 1;
    st.textContent = `Reading public bird records for ${cells.length} squares\u2026`;
    await pool(cells, 8, async cell => {
      const ck = `${sk}|${step}|${cell.s.toFixed(4)}|${cell.w.toFixed(4)}`;
      let r = cellCache.get(ck);
      if (!r){
        const j = await gbif('occurrence/search', {...base, decimalLatitude: `${cell.s.toFixed(5)},${cell.n.toFixed(5)}`, decimalLongitude: `${cell.w.toFixed(5)},${cell.e.toFixed(5)}`});
        const f = (j.facets || []).find(x => /species/i.test(x.field));
        r = {records: j.count || 0, species: f ? f.counts.map(x => [x.name, x.count]) : []};
        cellCache.set(ck, r);
      }
      if (cancelled()) return;
      done++; progress(done, cells.length);
      st.textContent = `Reading public bird records: ${done} of ${cells.length} squares`;
      if (!r.records) return;
      const x = {...cell, code: cellCode(cell), records: r.records, total: r.species.length, all: r.species, fresh: r.species.filter(([k]) => !life.has(k))};
      hsCells.push(x);
      if (x.fresh.length > runMax){ runMax = x.fresh.length; hsCells.forEach(paintCell); }
      drawCell(x, runMax);
    }, cancelled);
    if (cancelled()) return;
    finishRun();
  } catch (e) {
    if (cancelled()) return;
    st.textContent = `Couldn\u2019t reach GBIF (${esc((e && e.message) || 'network error')}). Check your connection and try again.`;
  } finally {
    if (t === hsToken){ hsRunning = false; $('hsGo').textContent = 'Map species I haven\u2019t seen'; $('hsBar').hidden = true; }
  }
}

function drawCell(x){
  x.rect = L.rectangle([[x.s, x.w], [x.n, x.e]], {weight: 0.5, color: '#13201A', opacity: 0.25, fillOpacity: 0.6})
    .bindPopup('Loading\u2026', {maxWidth: 280})
    .on('popupopen', async ev => {
      ev.popup.setContent(cellPopup(x));
      const keys = (hsTarget ? [hsTarget] : []).concat(x.fresh.slice(0, 15).map(([k]) => k));
      if (keys.some(k => !nameCache[k])){ await resolveNames(keys); ev.popup.setContent(cellPopup(x)); }
    })
    .addTo(hotLayer);
  paintCell(x);
}
function paintCell(x){
  if (!x.rect) return;
  const max = hsCells.maxFresh || Math.max(1, ...hsCells.map(c => c.fresh.length));
  if (hsTarget){
    const n = (x.fresh.find(([k]) => k === hsTarget) || [, 0])[1];
    const tmax = hsCells.maxTarget || 1;
    x.rect.setStyle(n ? {fillColor: rampColor(0.25 + 0.75 * Math.log(n) / Math.log(Math.max(tmax, 2))), fillOpacity: 0.7, opacity: 0.3} : {fillColor: '#FFFFFF', fillOpacity: 0.08, opacity: 0.1});
  } else {
    x.rect.setStyle(x.fresh.length ? {fillColor: rampColor(x.fresh.length / max), fillOpacity: 0.6, opacity: 0.25} : {fillColor: '#FFFFFF', fillOpacity: 0.15, opacity: 0.15});
  }
}
function cellPopup(x){
  const head = `<h4>${esc(cellName(x))}</h4><div class="meta">${x.records.toLocaleString('en-ZA')} public records, ${x.total} species${x.code ? `, pentad ${x.code}` : ''}</div>`;
  if (hsTarget){
    const n = (x.fresh.find(([k]) => k === hsTarget) || [, 0])[1];
    return `<div class="pop"><span class="tag">${n ? `${n} records of ${esc(label(hsTarget))}` : `No records of ${esc(label(hsTarget))}`}</span>${head}</div>`;
  }
  const named = x.fresh.slice(0, 15);
  const items = named.map(([k, n]) => `<li>${esc(label(k))} <span class="sci">${n} records</span></li>`).join('');
  return `<div class="pop"><span class="tag">${x.fresh.length} species you haven\u2019t seen</span>${head}${items ? `<ul>${items}</ul>` : ''}${x.fresh.length > 15 ? `<div class="meta">And ${x.fresh.length - 15} more</div>` : ''}</div>`;
}

async function finishRun(){
  const t = hsToken, st = $('hsStatus');
  if (!hsCells.length){ st.textContent = 'No public bird records in this area for these settings. Move the map, choose all years, or switch to all public records.'; return; }
  hsCells.maxFresh = Math.max(1, ...hsCells.map(c => c.fresh.length));
  hsCells.forEach(paintCell);
  $('hsLegend').hidden = false; $('hsLegLo').textContent = 'Few'; $('hsLegHi').textContent = 'Many species you haven\u2019t seen';

  const agg = new Map();
  hsCells.forEach(x => x.fresh.forEach(([k, n]) => { const e = agg.get(k) || {k, cells: 0, recs: 0}; e.cells++; e.recs += n; agg.set(k, e); }));
  hsSpecies = [...agg.values()].sort((a, b) => b.cells - a.cells || b.recs - a.recs);

  const top = hsCells.slice().sort((a, b) => b.fresh.length - a.fresh.length).filter(x => x.fresh.length).slice(0, 8);
  hsCells.forEach(x => delete x.rank); top.forEach((x, i) => x.rank = i + 1);
  st.textContent = `${hsSpecies.length} species you haven\u2019t logged are recorded in this area, across ${hsCells.length} squares with ${hsCells.reduce((s, x) => s + x.records, 0).toLocaleString('en-ZA')} public records. Tap a square or a species to explore.`;

  const yrs = +$('hsYears').value, thisYear = new Date().getFullYear();
  await pool(top, 4, async x => {
    const q = {taxonKey: 212, limit: 150, hasCoordinate: 'true', decimalLatitude: `${x.s.toFixed(5)},${x.n.toFixed(5)}`, decimalLongitude: `${x.w.toFixed(5)},${x.e.toFixed(5)}`};
    if (yrs) q.year = `${thisYear - yrs + 1},${thisYear}`;
    let recs = (await gbif('occurrence/search', {...q, datasetKey: SOURCES.ebird.ds})).results || [];
    if (!recs.some(r => r.locality)) recs = (await gbif('occurrence/search', q)).results || [];
    const byLoc = new Map();
    recs.forEach(r => { if (r.locality && r.decimalLatitude != null){ const e = byLoc.get(r.locality) || {n: 0, lat: 0, lng: 0}; e.n++; e.lat += r.decimalLatitude; e.lng += r.decimalLongitude; byLoc.set(r.locality, e); } });
    const best = [...byLoc.entries()].sort((a, b) => b[1].n - a[1].n)[0];
    if (best){ x.place = best[0]; x.pt = {lat: best[1].lat / best[1].n, lng: best[1].lng / best[1].n}; }
  });
  if (t !== hsToken) return;
  drawPins(); renderTop(); renderSpecies();

  /* name every unseen species in the background so the list can be searched; names are cached for next time */
  const order = hsSpecies.map(e => e.k);
  for (let i = 0; i < order.length && t === hsToken; i += 40){
    $('hsSpNote').textContent = `Looking up names: ${Math.min(i + 40, order.length)} of ${order.length}`;
    await resolveNames(order.slice(i, i + 40), () => t !== hsToken);
    if (t === hsToken) renderSpecies();
  }
  if (t === hsToken){ $('hsSpNote').textContent = 'Most widespread first. Tap a species to map where it\u2019s been recorded.'; renderTop(); }
}

function drawPins(){
  pinLayer.clearLayers(); hsMarkers = new Map();
  hsCells.filter(x => x.rank).forEach(x => {
    const at = x.pt || x.c, size = 28;
    const m = L.marker([at.lat, at.lng], {
      icon: L.divIcon({className: '', html: `<div class="hotpin" style="width:${size}px;height:${size}px">${x.rank}</div>`, iconSize: [size, size], iconAnchor: [size/2, size/2]}),
      zIndexOffset: 1000 - x.rank, keyboard: false
    }).on('click', () => x.rect && x.rect.openPopup(at));
    m.addTo(pinLayer); hsMarkers.set(x.rank, {m, x});
  });
}
function renderTop(){
  const top = hsCells.filter(x => x.rank).sort((a, b) => a.rank - b.rank);
  $('hsResultsBlock').hidden = !top.length || !!hsTarget;
  $('hsList').innerHTML = top.map(x => {
    const named = x.fresh.slice(0, 12).filter(([k]) => nameCache[k]).map(([k]) => esc(label(k))).join(', ');
    return `<li><button type="button" class="hbtn" data-rank="${x.rank}"><span class="hn">${x.fresh.length}</span><span class="hname">${x.rank}. ${esc(cellName(x))}</span><span class="hsub">species you haven\u2019t seen, from ${x.records.toLocaleString('en-ZA')} records</span></button>${named ? `<p class="hint" style="margin:6px 0 0 64px">Most recorded: ${named}${x.fresh.length > 12 ? ' and more' : ''}.</p>` : ''}${x.code ? `<p style="margin:4px 0 0 64px;font-size:13px"><a href="https://sabap2.birdmap.africa/coverage/pentad/${x.code}" target="_blank" rel="noopener" style="color:var(--bush)">Pentad ${x.code} on SABAP2</a></p>` : ''}</li>`;
  }).join('');
}
function renderSpecies(){
  const q = norm($('hsFilter').value.trim());
  const rows = hsSpecies.filter(e => !q || norm(allNames(e.k)).includes(q)).slice(0, 300);
  $('hsSpeciesBlock').hidden = !hsSpecies.length;
  $('hsSpTitle').textContent = `Species you haven\u2019t seen in this area (${hsSpecies.length})`;
  $('hsSpList').innerHTML = rows.map(e => `<li><button type="button" data-k="${e.k}"><span class="nm">${esc(label(e.k))}</span>${label(e.k) !== nm(e.k)[0] ? `<span class="sc">${esc(nm(e.k)[0])}</span>` : ''}<span class="ct">${e.cells} square${e.cells > 1 ? 's' : ''}<br>${e.recs.toLocaleString('en-ZA')} records</span></button></li>`).join('')
    || '<li class="hint" style="padding:8px 0">No unseen species match that name.</li>';
}
$('hsFilter').addEventListener('input', renderSpecies);
$('hsSpList').addEventListener('click', async e => {
  const b = e.target.closest('button[data-k]'); if (!b) return;
  setTarget(b.dataset.k);
});
async function setTarget(k){
  hsTarget = k;
  if (!nameCache[k]) await resolveNames([k]);
  const e = hsSpecies.find(s => s.k === k);
  hsCells.maxTarget = Math.max(1, ...hsCells.map(x => (x.fresh.find(([kk]) => kk === k) || [, 0])[1]));
  hsCells.forEach(paintCell);
  pinLayer.clearLayers();
  $('hsTName').textContent = label(k);
  $('hsTSci').textContent = label(k) !== nm(k)[0] ? nm(k)[0] : '';
  $('hsTInfo').textContent = `Recorded in ${e.cells} of the ${hsCells.length} squares searched, ${e.recs.toLocaleString('en-ZA')} records in total. Darker squares have more records, so you're more likely to find it there.`;
  $('hsTargetBlock').hidden = false; $('hsResultsBlock').hidden = true;
  $('hsLegLo').textContent = 'Few records'; $('hsLegHi').textContent = 'Many records';
  const hits = hsCells.filter(x => x.fresh.some(([kk]) => kk === k));
  if (hits.length) fit(L.latLngBounds(hits.flatMap(x => [[x.s, x.w], [x.n, x.e]])));
  $('hsTargetBlock').scrollIntoView({block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth'});
}
$('hsTClear').addEventListener('click', () => {
  hsTarget = null; hsCells.forEach(paintCell); drawPins(); renderTop();
  $('hsTargetBlock').hidden = true;
  $('hsLegLo').textContent = 'Few'; $('hsLegHi').textContent = 'Many species you haven\u2019t seen';
});
$('hsList').addEventListener('click', e => {
  const b = e.target.closest('button[data-rank]'); if (!b) return;
  const h = hsMarkers.get(+b.dataset.rank); if (!h) return;
  const at = h.x.pt || h.x.c;
  go([at.lat, at.lng], Math.max(map.getZoom(), h.x.step >= 0.5 ? 9 : 11));
  setTimeout(() => h.x.rect && h.x.rect.openPopup([at.lat, at.lng]), reduceMotion ? 0 : 850);
});

/* ---------- hotspots page: curated target sites ---------- */
const sitesLayer = L.layerGroup();
let hsMode = prefs.hsMode === 'heat' ? 'heat' : 'sites', siteFilter = prefs.siteFilter || 'all', siteTarget = null, siteMarkers = new Map();
const STATUS_COLOR = {need: '#C0392B', part: '#D9822B', done: '#2E8B57'};
const tName = x => pick(x[0], x[1], LANG) || x[2];
const tAlt = x => { const a = pick(x[0], x[1], other(LANG)); return a && a !== tName(x) ? a : ''; };
function siteState(site){
  const need = site.t.filter(x => !x[3]), got = site.t.filter(x => x[3]);
  return {need, got, st: !need.length ? 'done' : (got.length ? 'part' : 'need')};
}
function sitePopup(site){
  const {need, got} = siteState(site);
  const li = (x, seen) => `<li>${esc(tName(x))}${tAlt(x) ? ` <small>${esc(tAlt(x))}</small>` : ''}${seen ? ` <small>first seen ${pretty(x[3])}</small>` : ''}</li>`;
  return `<div class="pop"><h4>${esc(site.n)}</h4>
    <div class="grid2"><b>Biome</b><span>${esc(site.b)}</span><b>Best season</b><span>${esc(site.s)}</span><b>Key sites</b><span>${esc(site.k)}</span><b>Access</b><span>${esc(site.a)}</span></div>
    <div class="meta" style="color:var(--need);font-weight:600">Needed targets (${need.length})</div>
    <ul class="need">${need.length ? need.map(x => li(x, false)).join('') : '<li style="color:var(--muted)">None, all target specials seen</li>'}</ul>
    <div class="meta" style="color:var(--done);font-weight:600">Already seen (${got.length})</div>
    <ul class="got">${got.length ? got.map(x => li(x, true)).join('') : '<li style="color:var(--muted)">None seen yet</li>'}</ul></div>`;
}
function renderSites(){
  const all = new Map(); D.sites.forEach(st => st.t.forEach(x => { if (!all.has(x[4])) all.set(x[4], x); }));
  const total = all.size, seenN = [...all.values()].filter(x => x[3]).length, pct = total ? Math.round(100 * seenN / total) : 0;
  $('dTotal').textContent = total; $('dSeen').textContent = seenN; $('dPct').textContent = `seen (${pct}%)`; $('dNeed').textContent = total - seenN;
  $('dBarFill').style.width = pct + '%'; $('dBar').setAttribute('aria-label', `${pct}% of target specials seen`);

  sitesLayer.clearLayers(); siteMarkers = new Map();
  const rows = D.sites.map((site, i) => ({site, i, ...siteState(site)}));
  const shown = rows.filter(r => siteFilter === 'all' || (siteFilter === 'todo' ? r.need.length : !r.need.length));
  const hasT = r => siteTarget === null || r.need.some(x => x[4] === siteTarget);
  shown.forEach(r => {
    const dim = !hasT(r);
    L.marker([r.site.lat, r.site.lng], {
      icon: L.divIcon({className: '', html: `<div class="sitepin${dim ? ' dim' : ''}" style="width:30px;height:30px;background:${STATUS_COLOR[r.st]}">${r.need.length || '\u2713'}</div>`, iconSize: [30, 30], iconAnchor: [15, 15]}),
      title: r.site.n, zIndexOffset: dim ? 0 : 500 + r.need.length, keyboard: false
    }).bindPopup(() => sitePopup(r.site), {maxWidth: 320}).addTo(sitesLayer);
  });
  shown.forEach(r => sitesLayer.eachLayer(m => { if (m.options.title === r.site.n) siteMarkers.set(r.i, m); }));
  const sorted = shown.slice().sort((a, b) => hasT(b) - hasT(a) || b.need.length - a.need.length || a.site.n.localeCompare(b.site.n));
  $('siteList').innerHTML = sorted.map(r => `<li class="${hasT(r) ? '' : 'dim'}"><button type="button" data-i="${r.i}"><span class="dot" style="background:${STATUS_COLOR[r.st]}">${r.need.length || '\u2713'}</span><span class="nm">${esc(r.site.n)}</span><span class="sub">${r.need.length ? `${r.need.length} of ${r.site.t.length} specials still needed` : `All ${r.site.t.length} specials seen`}, ${esc(r.site.b)}</span></button></li>`).join('')
    || '<li class="hint" style="padding:8px 0">No sites match this filter.</li>';

  const need = new Map();
  D.sites.forEach((st, i) => st.t.forEach(x => { if (!x[3]){ const e = need.get(x[4]) || {x, sites: []}; e.sites.push(i); need.set(x[4], e); } }));
  const list = [...need.values()].sort((a, b) => b.sites.length - a.sites.length || tName(a.x).localeCompare(tName(b.x)));
  $('needTitle').textContent = `Specials you still need (${list.length})`;
  $('needList').innerHTML = list.map(e => `<li><button type="button" data-g="${e.x[4]}" aria-pressed="${siteTarget === e.x[4]}"><span class="nm">${esc(tName(e.x))}</span><span class="sc">${esc([tAlt(e.x), e.x[2]].filter(Boolean).join(', '))}</span><span class="ct">${e.sites.length} site${e.sites.length > 1 ? 's' : ''}</span></button></li>`).join('')
    || '<li class="hint" style="padding:8px 0">You\u2019ve seen every special on the list.</li>';

  const t = siteTarget !== null ? need.get(siteTarget) : null;
  $('siteTargetBlock').hidden = !t;
  if (t){
    $('stName').textContent = tName(t.x); $('stAlt').textContent = tAlt(t.x); $('stSci').textContent = t.x[2];
    $('stInfo').textContent = `A special at ${t.sites.length} site${t.sites.length > 1 ? 's' : ''}: ${t.sites.map(i => D.sites[i].n).join('; ')}.`;
  }
  $('siteListTitle').textContent = t ? `Sites for ${tName(t.x)} first` : (siteFilter === 'done' ? 'Completed sites' : 'Sites, most targets first');
}
$('siteList').addEventListener('click', e => {
  const b = e.target.closest('button[data-i]'); if (!b) return;
  const m = siteMarkers.get(+b.dataset.i); if (!m) return;
  go(m.getLatLng(), Math.max(map.getZoom(), 8));
  setTimeout(() => m.openPopup(), reduceMotion ? 0 : 850);
});
$('needList').addEventListener('click', e => {
  const b = e.target.closest('button[data-g]'); if (!b) return;
  siteTarget = +b.dataset.g;
  if (siteFilter === 'done'){ siteFilter = 'all'; syncSeg('siteFilter', 'all'); }
  renderSites();
  const hits = D.sites.filter(st => st.t.some(x => x[4] === siteTarget && !x[3]));
  if (hits.length) fit(L.latLngBounds(hits.map(st => [st.lat, st.lng])).pad(0.2));
  $('siteTargetBlock').scrollIntoView({block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth'});
});
$('stClear').addEventListener('click', () => { siteTarget = null; renderSites(); });

/* ---------- stats page ---------- */
const QUAL = ['#2E5E4E','#E3A91B','#1F4E79','#B5651D','#7A4E9C','#5C8A2E','#C0392B','#3A9BB5','#8C6D1F','#D16BA5','#4D4D4D','#2E8B57','#9C5A3C','#6A7FDB'];
let statsDrawn = false, plotlyP = null, kpisDone = false, drawMonths = null;
let monthMode = ['all', 'species', 'lifers'].includes(prefs.monthMode) ? prefs.monthMode : 'all';
function loadScript(src){ return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); }); }
function loadPlotly(){
  if (window.Plotly) return Promise.resolve();
  if (!plotlyP) plotlyP = loadScript('https://cdn.plot.ly/plotly-2.35.2.min.js')
    .catch(() => loadScript('https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js'))
    .catch(e => { plotlyP = null; throw e; });
  return plotlyP;
}
const doy = d => { const y = yearOf(d), m = Math.floor(d / 100) % 100, dd = d % 100; return Math.round((Date.UTC(y, m - 1, dd) - Date.UTC(y, 0, 1)) / 864e5) + 1; };
const isoOf = d => { const s = String(d); return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`; };
function renderKPIs(){
  if (kpisDone) return; kpisDone = true;
  const byYear = new Map();
  recs.forEach(r => { const y = yearOf(r.d); const e = byYear.get(y) || {sp: new Set(), n: 0, lif: 0}; e.sp.add(r.s); e.n++; byYear.set(y, e); });
  lifers.forEach(i => byYear.get(yearOf(recs[i].d)).lif++);
  const ys = [...byYear.keys()].sort((a, b) => b - a);
  const best = ys.reduce((a, y) => byYear.get(y).sp.size > byYear.get(a).sp.size ? y : a, ys[0]);
  const byDay = new Map();
  recs.forEach(r => { const e = byDay.get(r.d) || {sp: new Set(), locs: new Map()}; e.sp.add(r.s); e.locs.set(D.lg[r.l], (e.locs.get(D.lg[r.l]) || 0) + 1); byDay.set(r.d, e); });
  const [bd, be] = [...byDay.entries()].sort((a, b) => b[1].sp.size - a[1].sp.size || a[0] - b[0])[0];
  const bdLoc = [...be.locs.entries()].sort((a, b) => b[1] - a[1])[0][0];
  const places = new Set(recs.map(r => D.lg[r.l])).size;
  const k = [[recs.length.toLocaleString('en-ZA'), 'sightings'], [D.sp.length, 'species'], [places, 'places (grouped)'], [ys.length, 'years with sightings'],
             [byYear.get(best).sp.size, `species in ${best}, your best year`], [be.sp.size, `species on ${pretty(bd)} at ${bdLoc}, your best day`]];
  $('kpis').innerHTML = k.map(([v, l]) => `<div><b>${v}</b><span>${esc(l)}</span></div>`).join('');
  $('ytable').innerHTML = ys.map(y => { const e = byYear.get(y); return `<tr><td>${y}</td><td>${e.sp.size}</td><td>${e.lif}</td><td>${e.n.toLocaleString('en-ZA')}</td></tr>`; }).join('');
}
async function renderStats(){
  renderKPIs();
  if (statsDrawn){ ['cBigYear','cGrowth','cMonths','cTopLoc','cTopLifer'].forEach(id => window.Plotly && Plotly.Plots.resize($(id))); return; }
  const ids = ['cBigYear','cGrowth','cMonths','cTopLoc','cTopLifer'];
  try { await loadPlotly(); }
  catch (e){ ids.forEach(id => $(id).innerHTML = '<p class="chartnote">The charts need an internet connection to load the Plotly charting library. Reconnect and open this tab again.</p>'); return; }
  statsDrawn = true;
  const font = {family: '"Public Sans", system-ui, sans-serif', color: '#13201A', size: 12.5};
  const base = (title, extra) => Object.assign({title: {text: title, x: 0.01, xanchor: 'left', font: {family: 'Literata, Georgia, serif', size: 17}}, font, paper_bgcolor: '#FFFFFF', plot_bgcolor: '#FFFFFF', margin: {l: 60, r: 20, t: 60, b: 50}, hoverlabel: {font: {family: font.family}}}, extra);
  const axis = extra => Object.assign({gridcolor: '#E6EAE4', zerolinecolor: '#CBD3C8', linecolor: '#CBD3C8'}, extra);
  const cfg = {responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d']};

  /* Big Year: cumulative species by day of year, one line per year */
  const thisYear = new Date().getFullYear();
  const years = [...new Set(recs.map(r => yearOf(r.d)))].sort();
  const traces = years.map((y, k) => {
    const first = new Map();
    recs.forEach(r => { if (yearOf(r.d) === y){ const d = doy(r.d); if (!first.has(r.s) || d < first.get(r.s).d) first.set(r.s, {d, date: r.d}); } });
    const pts = [...first.values()].sort((a, b) => a.d - b.d);
    const cur = y === thisYear;
    return {x: pts.map(p => p.d), y: pts.map((_, i) => i + 1), text: pts.map(p => `${MONTHS[Math.floor(p.date / 100) % 100 - 1]} ${String(p.date % 100).padStart(2, '0')}`),
      mode: 'lines', line: {shape: 'hv', width: cur ? 4 : 2, color: QUAL[k % QUAL.length]}, name: `${y}${cur ? ' (current)' : ''}`,
      hovertemplate: '<b>%{text} %{fullData.name}</b><br>Year species: <b>%{y}</b><extra></extra>'};
  });
  Plotly.newPlot('cBigYear', traces, base('Big Year pace: species added through each year', {
    xaxis: axis({title: {text: 'Date'}, tickmode: 'array', tickvals: [1,32,60,91,121,152,182,213,244,274,305,335], ticktext: MONTHS.map(m => m + ' 1'), range: [1, 366]}),
    yaxis: axis({title: {text: 'Species seen that year'}, rangemode: 'tozero'}), hovermode: 'closest', legend: {title: {text: 'Year'}}}), cfg);

  /* Life list growth */
  Plotly.newPlot('cGrowth', [{x: lifers.map(i => isoOf(recs[i].d)), y: lifers.map((_, k) => k + 1), mode: 'lines', line: {shape: 'hv', color: '#2E5E4E', width: 2.5},
    text: lifers.map(i => spName(recs[i].s)), hovertemplate: '%{x|%d %b %Y}<br>#%{y}: %{text}<extra></extra>', name: 'Life list'}],
    base('Life list growth', {xaxis: axis({type: 'date'}), yaxis: axis({title: {text: 'Total species'}, rangemode: 'tozero'}), showlegend: false}), cfg);

  /* Activity by month: total sightings, unique species or lifers, switched with the buttons above the chart */
  const mc = Array(12).fill(0), ms = Array.from({length: 12}, () => new Set()), ml = Array(12).fill(0);
  recs.forEach(r => { const m = Math.floor(r.d / 100) % 100 - 1; mc[m]++; ms[m].add(r.s); });
  lifers.forEach(i => ml[Math.floor(recs[i].d / 100) % 100 - 1]++);
  const custom = MONTHS.map((_, m) => [mc[m], ms[m].size, ml[m]]);
  const MONTH_VIEWS = {
    all:     {y: mc, axis: 'Total sightings logged', title: 'Birding activity by month: total sightings', color: '#E3A91B'},
    species: {y: ms.map(x => x.size), axis: 'Unique species logged', title: 'Birding activity by month: unique species', color: '#2E5E4E'},
    lifers:  {y: ml, axis: 'Lifers logged', title: 'Birding activity by month: lifers', color: '#7A4E9C'}
  };
  drawMonths = mode => {
    const v = MONTH_VIEWS[mode] || MONTH_VIEWS.all;
    Plotly.react('cMonths', [{x: MONTHS, y: v.y, type: 'bar', marker: {color: v.color}, customdata: custom,
      hovertemplate: '<b>%{x}</b><br>%{customdata[0]:,} sightings<br>%{customdata[1]} unique species<br>%{customdata[2]} lifers<extra></extra>'}],
      base(v.title, {xaxis: axis({}), yaxis: axis({title: {text: v.axis}, rangemode: 'tozero'}), showlegend: false}), cfg);
  };
  drawMonths(monthMode);

  /* Top places by species, and where lifers came from */
  const topBar = (counts, title, color, label) => {
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).reverse();
    return [[{x: top.map(e => e[1]), y: top.map(e => e[0]), type: 'bar', orientation: 'h', marker: {color}, hovertemplate: `%{y}: <b>%{x}</b> ${label}<extra></extra>`}],
      base(title, {xaxis: axis({title: {text: label}}), yaxis: axis({automargin: true, tickfont: {size: 11.5}}), margin: {l: 10, r: 20, t: 60, b: 50}, showlegend: false})];
  };
  const spByPlace = new Map();
  recs.forEach(r => { const g = D.lg[r.l]; if (!spByPlace.has(g)) spByPlace.set(g, new Set()); spByPlace.get(g).add(r.s); });
  const [t1, l1] = topBar(new Map([...spByPlace].map(([g, s]) => [g, s.size])), 'Top 20 places by species seen', '#2E5E4E', 'species');
  Plotly.newPlot('cTopLoc', t1, l1, cfg);
  const liferPlaces = new Map();
  lifers.forEach(i => { const g = D.lg[recs[i].l]; liferPlaces.set(g, (liferPlaces.get(g) || 0) + 1); });
  const [t2, l2] = topBar(liferPlaces, 'Top 20 places for new lifers', '#7A4E9C', 'lifers');
  Plotly.newPlot('cTopLifer', t2, l2, cfg);
}

/* ---------- names, toggles and routing ---------- */
function syncSeg(id, v){ $(id).querySelectorAll('button[data-v]').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v)); }
function setupSeg(id, v, onChange){
  syncSeg(id, v);
  $(id).addEventListener('click', e => { const b = e.target.closest('button[data-v]'); if (!b || b.disabled) return; syncSeg(id, b.dataset.v); onChange(b.dataset.v); });
}
if (!HEAT_OK) ['sDisp', 'lDisp'].forEach(id => { const b = $(id).querySelector('[data-v="heat"]'); b.disabled = true; b.title = 'The heatmap library didn\u2019t load. Check your internet connection.'; });
setupSeg('langSeg', LANG, v => { LANG = v; savePref('lang', v); applyLang(); });
setupSeg('sDisp', sDisp, v => { sDisp = v; savePref('sDisp', v); showSightings(); });
setupSeg('lDisp', lDisp, v => { lDisp = v; savePref('lDisp', v); showLifers(); });
setupSeg('monthMode', monthMode, v => { monthMode = v; savePref('monthMode', v); if (drawMonths) drawMonths(v); });
setupSeg('siteFilter', siteFilter, v => { siteFilter = v; savePref('siteFilter', v); renderSites(); });
setupSeg('hsMode', hsMode, v => { hsMode = v; savePref('hsMode', v); $('hsSites').hidden = v !== 'sites'; $('hsHeat').hidden = v !== 'heat'; route(); });
$('hsSites').hidden = hsMode !== 'sites'; $('hsHeat').hidden = hsMode !== 'heat';

function applyLang(){
  if (current !== null) selectSpecies(current, {keep: true});
  if (!sugg.hidden) renderSuggest();
  drawLifers();
  renderSites();
  if (hsCells.length){ renderTop(); renderSpecies(); }
  if (hsTarget){ $('hsTName').textContent = label(hsTarget); $('hsTSci').textContent = label(hsTarget) !== nm(hsTarget)[0] ? nm(hsTarget)[0] : ''; }
}
renderSites();

function route(){
  const page = pageNow();
  PAGES.forEach(p => { $('page-' + p).hidden = p !== page; $('tab-' + p).setAttribute('aria-selected', p === page); });
  $('statsMain').hidden = page !== 'stats';
  [recLayer, rangeLayer, hotLayer, sitesLayer].forEach(l => l && map.removeLayer(l));
  showSightings(); showLifers();
  if (page === 'sightings') [recLayer, rangeLayer].forEach(l => l && l.addTo(map));
  if (page === 'hotspots') (hsMode === 'sites' ? sitesLayer : hotLayer).addTo(map);
  if (page === 'stats') renderStats();
  else setTimeout(() => map.invalidateSize(), 0);
}
window.addEventListener('hashchange', route);
route();
</script>
</body>
</html>
"""


# ==============================================================================
# 5. WRITE THE HTML AND REPORT
# ==============================================================================
def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(data, title):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # a comment containing </script> must not end the script block
    html = TEMPLATE.replace("__DATA__", payload)
    html = html.replace("<title>Bird log map</title>", f"<title>{escape(title)}</title>")
    html = html.replace("<h1>Bird log</h1>", f"<h1>{escape(title)}</h1>")
    return html


def find_reference(explicit, csv_path):
    if explicit:
        return Path(explicit)
    script_dir = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    for folder in (script_dir, Path(csv_path).resolve().parent, Path.cwd()):
        p = folder / "BirdReference.csv"
        if p.exists():
            return p
    return None


def save_cleaned(path, headers, sightings, species, files):
    """Your original columns plus the cleaned coordinates, grouped location and both names."""
    extra = ["Source_File", "Latitude_CLEANED", "Longitude_CLEANED", "Coordinates_Filled", "grouped_location",
             "Afrikaans_Name", "English_Name", "Scientific_Name"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers + extra)
        for s in sightings:
            sp = species[s["sp"]]
            w.writerow([s["raw"].get(h, "") for h in headers] + [
                Path(files[s["src"]]).name, "" if s["lat"] is None else s["lat"], "" if s["lon"] is None else s["lon"],
                "yes" if s["filled"] else "", group_location(s["loc"]), sp["afr"], sp["eng"], sp["sci"]])


def parse_overrides(items):
    out = {}
    keys = {"species": "com", "common": "com", "com": "com", "scientific": "sci", "sci": "sci", "date": "date",
            "place": "loc", "location": "loc", "loc": "loc", "lat": "lat", "latitude": "lat", "lon": "lon",
            "longitude": "lon", "gps": "gps", "notes": "note", "comments": "note", "note": "note"}
    for item in items or []:
        if "=" not in item or item.split("=", 1)[0].strip().lower() not in keys:
            sys.exit(f"--column {item}: use the form name=Heading, where name is one of species, scientific, date, place, lat, lon, gps, notes.")
        k, v = item.split("=", 1)
        out[keys[k.strip().lower()]] = v
    return out

def build_report(files, ref_path=None, names="af", title="Bird log", overrides=None, log=print):
    """Everything between "which files" and "write the HTML": read the CSVs, link the bird names,
    place and count the sightings, and build the page. Returns a dict with the finished "html" and the
    pieces main() reports on. Raises ValueError (or OSError) with a readable message when a file can't be used.
    Paths can be on disk or in a virtual file system, so a browser running this under Pyodide can use it too."""
    headers, sightings = [], []
    for src, path in enumerate(files):
        h, rows, skipped, used = load_sightings(path, src, overrides)
        headers += [x for x in h if x not in headers]
        sightings += rows
        log(f"Loaded {Path(path).name}: {len(rows):,} sightings" + (f", {skipped} row(s) skipped for a missing species name or date" if skipped else ""))
        log("   columns used: " + "; ".join(f"{k}: {v}" for k, v in used.items() if v))

    book = NameBook()
    if ref_path and Path(ref_path).exists():
        try:
            n = book.load_reference(ref_path)
            log(f"Loaded {n} name entries from {Path(ref_path).name}")
        except (OSError, ValueError) as e:
            log(f"Warning: couldn't read {ref_path}: {e}. Carrying on with the names in your CSV only.")
            ref_path = None
    else:
        log("Warning: BirdReference.csv not found, so Afrikaans/English switching will only use the names in your CSV.")
        ref_path = None

    filled = fill_missing_coordinates(sightings)
    data, species, unresolved, unresolved_specials, duplicates = build_data(sightings, book, bool(ref_path))
    data["meta"] = {"lang": names, "source": ", ".join(Path(f).name for f in files), "generated": datetime.date.today().isoformat()}
    return {"html": build_html(data, title), "data": data, "headers": headers, "sightings": sightings, "species": species,
            "unresolved": unresolved, "unresolved_specials": unresolved_specials, "duplicates": duplicates,
            "filled": filled, "ref_path": ref_path}



def main():
    ap = argparse.ArgumentParser(description="Build an interactive birding report (HTML) from eBird and/or Roberts app CSV files.")
    ap.add_argument("csv", nargs="*", help="one or more sightings CSV files, e.g. an eBird and a Roberts export (leave out to choose in a dialog)")
    ap.add_argument("-o", "--output", help="HTML file to write (default: birding_report.html next to the first CSV)")
    ap.add_argument("--reference", help="path to BirdReference.csv (default: next to this script or the CSV)")
    ap.add_argument("--names", choices=["af", "en"], default="af", help="language the page opens in (default: af)")
    ap.add_argument("--title", default="Bird log", help="heading shown in the page")
    ap.add_argument("--column", action="append", metavar="NAME=HEADING",
                    help='tell the script which column to use when it can\'t work it out, e.g. --column date="Date Seen" '
                         "(names: species, scientific, date, place, lat, lon, gps, notes)")
    ap.add_argument("--save-cleaned", action="store_true", help="also write FixedeBird.csv (next to the report) with cleaned coordinates and names")
    ap.add_argument("--no-open", action="store_true", help="don't open the report in the browser")
    args = ap.parse_args()
    overrides = parse_overrides(args.column)

    files = args.csv or choose_files()
    if not files:
        sys.exit("No file chosen. Run again and pick your CSV file(s), or give their names after the command.")
    ref_path = find_reference(args.reference, files[0])
    try:
        r = build_report(files, ref_path, args.names, args.title, overrides)
    except (OSError, ValueError) as e:
        sys.exit(f"Error: {e}")
    headers, sightings, species, data = r["headers"], r["sightings"], r["species"], r["data"]
    unresolved, unresolved_specials, duplicates = r["unresolved"], r["unresolved_specials"], r["duplicates"]
    filled, ref_path = r["filled"], r["ref_path"]

    out = Path(args.output) if args.output else Path(files[0]).resolve().parent / "birding_report.html"
    out.write_text(r["html"], encoding="utf-8")

    days = [s["day"] for s in sightings]
    print(f"\nWrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    print(f"{len(sightings):,} sightings of {len({s['sp'] for s in sightings})} species, {min(days) // 10000} to {max(days) // 10000}")
    if duplicates:
        print(f"{duplicates:,} sighting(s) appeared in more than one file (same species, same day, within 10 km) and were counted once.")
    if ref_path:
        print(f"Names: {len(species) - len(unresolved)} of {len(species)} species matched in BirdReference.csv")
        for sp in unresolved:
            print(f"   not matched: {sp['com']}" + (f" ({sp['sci']})" if sp["sci"] != sp["com"] else ""))
    total = len({x[4] for site in data["sites"] for x in site["t"]})
    seen = len({x[4] for site in data["sites"] for x in site["t"] if x[3]})
    print(f"Hotspot specials: {seen} of {total} seen ({round(100 * seen / total) if total else 0}%)")
    for b in (unresolved_specials if ref_path else []):
        print(f"   special not in BirdReference.csv, matched on exact name only: {b.get('eng')} ({b.get('sci')})")

    print("\n" + "=" * 50 + "\nAUDIT: LOCATIONS WITHOUT COORDINATES\n" + "=" * 50)
    if filled:
        print(f"{filled} sighting(s) placed near a known location because they had no coordinates.")
    missing = {}
    for s in sightings:
        if s["lat"] is None:
            missing[s["loc"]] = missing.get(s["loc"], 0) + 1
    if missing:
        print(f"{sum(missing.values())} sighting(s) still have no coordinates, so they're in the lists and stats but not on the maps.")
        print("Add the place to MISSING_LOCATION_CENTERS at the top of this script to map them:")
        for loc, n in sorted(missing.items(), key=lambda x: -x[1]):
            print(f"   {loc}: {n}")
    else:
        print("All sightings have coordinates.")
    print("=" * 50)

    if args.save_cleaned:
        cleaned = out.resolve().parent / "FixedeBird.csv"
        save_cleaned(cleaned, headers, sightings, species, files)
        print(f"Saved cleaned data to {cleaned}")

    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
