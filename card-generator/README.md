# Card generator

Draws one image per artefact in the "5a" card style (era cap, set band with emblem, value coin, keyword ribbons, card text), in English and French.

## Setup (once)

You need Python 3.9 or newer. Install the one library it uses:

```
pip install pillow
```

## Make the cards

Open a terminal in this `card-generator` folder and run:

```
python generate_cards.py
```

This reads the **live** vault (`Documents\Turnabout Auction\Cards`), the released version of the game, and writes the images to `cards/en/` and `cards/fr/` at the root of the repo.

To preview work in progress from the **sandbox** vault instead:

```
python generate_cards.py --wip
```

WIP images go to `cards-wip/`, so they never overwrite the live ones. That folder is ignored by Git.

Each run of the live build also writes the two playingcards.io CSVs next to the images: `cards/TurnaboutAuctionArtefactsList_EN.csv` and `..._FR.csv` (see "The CSV" below).

Each image is named after the English name (`Cleopatra's Earring` → `cleopatras_earring.png`). Each run also makes `overview_en.jpg` and `overview_fr.jpg` with every card on one sheet, for a quick check.

Existing images with the same name are replaced. Images of artefacts you removed or renamed are **not** deleted: delete them yourself.

### Where the vaults are: `settings.json`

```json
{
  "image_base_url": "https://raw.githubusercontent.com/Djoaieuh/Turnabout-Auction/refs/heads/main/",
  "live": { "cards": "C:\\Users\\USER\\Documents\\Turnabout Auction\\Cards", "out": "../cards" },
  "wip":  { "cards": "C:\\Users\\USER\\Documents\\Turnabout Auction - SANDBOX\\Cards", "out": "../cards-wip" }
}
```

If you move a vault, change its path here. `out` is relative to this folder. `image_base_url` is where GitHub serves the repo's files; the CSV links are built from it.

## The CSV

One file per language, for importing into playingcards.io:

- A single column, `image`: the link to the card's picture on GitHub, e.g. `https://raw.githubusercontent.com/Djoaieuh/Turnabout-Auction/refs/heads/main/cards/en/ankh.png`. The French file links to `cards/fr/`.
- **One row per physical copy**: a card with `copies: 3` gets 3 identical rows. Rows follow the cards' `order`.
- UTF-8 with BOM, CRLF line endings.

The links only work once the images are on GitHub, so **commit and push the `cards` folder before importing the CSV**.

In playingcards.io, the card template needs one image layer whose Card Data Field is `image`, set to "Different per-card" and covering the whole card. The old text layers and the colour background aren't needed any more: everything is in the picture.

No CSV is written with `--wip` (those images aren't pushed), with `--only` (the CSV needs every card), or when `--out` is outside the repo.

### Options

| Option | What it does |
|---|---|
| `--wip` | Draw the sandbox vault into `cards-wip/` instead of the live vault into `cards/` |
| `--input PATH` | Override the source: a JSON file (e.g. `artefacts.json`), or any folder of card notes |
| `--out PATH` | Override the output folder |
| `--lang en` / `fr` / `both` | Which languages to draw. Default: both |
| `--scale N` | Size: 1 = 130 × 160, 2 = 260 × 320, 4 = 520 × 640 (default) |
| `--only TEXT` | Only cards whose English name contains TEXT, e.g. `--only "Serpent"` |
| `--no-sheet` | Skip the overview images |

## Input

**Card notes:** the properties at the top of each note are used: `era`, `set`, `base_value`, `copies`, `keyword`, `text`, `name_fr`, `keyword_fr`, `text_fr`, `order`. The card's English name is the note's file name.

**JSON:** a list of artefacts with the same fields plus `name` (see `artefacts.json`, a snapshot of the live vault; use it with `--input artefacts.json` when the vault isn't on this computer):

```json
{
  "name": "Cleopatra's Earring",
  "era": "Egyptian",
  "set": "Cleopatra",
  "base_value": 20,
  "copies": 3,
  "keyword": "Attachment: Egyptian",
  "text": "Double the final sell value of the artefact this is attached to.",
  "name_fr": "Boucle d'Oreille de Cléopâtre",
  "keyword_fr": "Accessoire : Égyptien",
  "text_fr": "La valeur de vente finale de l'artéfact auquel celui-ci est attaché est doublée.",
  "order": 10
}
```

- Several keywords: separate them with a comma (`"Attachment: Any, Container: 1"`). Each gets its own ribbon.
- No era or set: write `"N/A"`. An empty `base_value` shows as `?`.
- Before drawing anything, the program checks every card and stops with a list of problems if one is missing a style, a text or a translation, if `copies` isn't a whole number of 1 or more, or if two cards would get the same image name.
- If a text is too long, it is shrunk a little to fit and the program says so. If it still doesn't fit, it warns that the text overflows.

## Styles: `styles.json`

Everything visual that depends on the era or the set lives here, so new content needs no code changes.

- **`eras`**: one entry per era, keyed by its English name: `label` / `label_fr` (shown in the top cap), `color` (the cap), `pattern` (a name from `patterns`).
- **`sets`**: one entry per set: `label` / `label_fr` (under the emblem), `color` (band, coin, ribbons), `icon` (the emblem).
- **`patterns`**: the repeating era patterns: a `tile` size and SVG paths drawn in white.

Icons and patterns are SVG path data (the `d` of an SVG `<path>`): icons on a 24 × 24 grid. You can draw an emblem in any vector tool, export it as SVG, and paste its `d` attribute.

**Adding a new set:** add an entry to `sets` with its colour, labels and an icon. **Adding a new era:** add an entry to `eras`, and a pattern if it needs a new one.

## Layout

Sizes and spacing are constants at the top of `generate_cards.py` (in units of a 260 × 320 card), e.g. `BAND_H`, `COIN_D`, `TEXT_SIZE`. Change them there to adjust the design for every card at once.

## Fonts

Inter (SIL Open Font License, see `fonts/OFL.txt`), bundled so the cards look the same on every computer.
