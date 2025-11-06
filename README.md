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
python ./convert.py [-w MVWorld] [-o OUTPUT_DIR] <player.dat> [<player.dat> ...]
```
**player.dat** - Filename(s) of saved minecraft player state in [nbt format](https://minecraft.wiki/w/Player.dat_format) to be converted.<br/>
**MVWorld** - Multiverse world(overworld) name. 'world' by default<br/>
**OUTPUT_DIR** - Optional directory to place the generated `.json` files (defaults to the same directory as the `.dat` file).

For each player the converter now produces both `<lastKnownName>.json` and `<uuid>.json`, matching Multiverse-Inventories' expectations.

## Known issues:
See TODOs in convert.py<br/>

Still need some tests:
- Knowledge book (Creative mode only)

And implementation of some very specific futures:
- Skull owner profiles
- Written book pages json normlization
- BlockStateTag
- Custom tag
