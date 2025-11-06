# Minecraft player.dat converter
This is a basic converter to turn vanilla minecraft player.dat files into [Multiverse-Inventories](https://github.com/Multiverse/Multiverse-Inventories/) .json files.
Almost complete implementation of the original [Bukkit serialization algorithms](https://hub.spigotmc.org/stash/projects/SPIGOT/repos/bukkit/browse/src/main/java/org/bukkit/inventory/).

## Requirements:
1. python >= 3.9 (not tested with earlier versions).

2. [nbt library](https://pypi.org/project/NBT/) installed at system or [virtual environment](https://docs.python.org/3/library/venv.html).
```
pip install nbt
```

## Usage:
```
python ./convert.py [-w MVWorld] [-o OUTPUT_ROOT] <player.dat> [<player.dat> ...]
```
**player.dat** - Filename(s) or directories containing saved minecraft player state in [nbt format](https://minecraft.wiki/w/Player.dat_format); directories are scanned recursively for `.dat`/`.nbt` files.<br/>
**MVWorld** - Multiverse world(overworld) name. 'world' by default<br/>
**OUTPUT_ROOT** - Optional directory to place the generated structure (defaults to `./out`).

For each player the converter now produces both `<lastKnownName>.json` (full inventory data under `groups/<world>/` and `worlds/<world>/`) and `<uuid>.json` (a short `playerData` wrapper under `players/`). The layout matches:

```
out/
  groups/<world>/<lastKnownName>.json
  worlds/<world>/<lastKnownName>.json
  players/<uuid>.json
```

## Known issues:
See TODOs in convert.py<br/>

Still need some tests:
- Knowledge book (Creative mode only)

And implementation of some very specific futures:
- Skull owner profiles
- Written book pages json normlization
- BlockStateTag
- Custom tag
