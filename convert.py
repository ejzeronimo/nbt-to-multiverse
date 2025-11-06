import argparse
import base64
import io
import json
from pathlib import Path
import uuid

from nbt import nbt as nbtlib

# https://minecraft.wiki/w/Item_format
# https://hub.spigotmc.org/stash/projects/SPIGOT/repos/bukkit/
# https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/
# https://github.com/Multiverse/Multiverse-Inventories/

DEFAULT_BUKKIT_VERSION = 4556
BUKKIT_VERSION = DEFAULT_BUKKIT_VERSION
GAME_MODES = ('SURVIVAL', 'CREATIVE', 'ADVENTURE', 'SPECTATOR')

# https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaItem.java#1394
HANDLED_TAGS = (
    'display', 'CustomModelData', 'BlockStateTag', 'RepairCost', 'Enchantments', 'HideFlags', 'Unbreakable', 'Damage',
    'PublicBukkitValues', 'AttributeModifiers', 'AttributeName', 'Name', 'Amount', 'UUIDMost', 'UUIDLeast', 'Slot',
    'Trim', 'material', 'pattern',  # Meta Armor
    'map_is_scaling', 'MapColor', 'map',  # Meta Map
    'custom_potion_effects', 'Potion', 'CustomPotionColor',  # Meta Potion
    'SkullOwner', 'SkullProfile',  # Meta Skull
    'EntityTag',  # Meta Spawn Egg
    'BlockEntityTag',  # Meta Block State
    'title', 'author', 'pages', 'resolved', 'generation',  # Meta Book
    'Fireworks',  # Meta Firework
    'StoredEnchantments',  # Meta Enchanted Book
    'Explosion',  # Meta Charge
    'Recipes',  # Meta Knowledge Book
    'BucketVariantTag',  # Meta Tropical Fish Bucket
    'Variant',  # Meta Axolotl Bucket
    'Charged', 'ChargedProjectiles',  # Meta Crossbow
    'effects',  # Meta Suspicious Stew
    'LodestoneDimension', 'LodestonePos', 'LodestoneTracked',  # Meta Compass
    'Items',  # Meta Bundle
    'instrument',  # Meta Music Instrument
)


def _build_enchantment_list(component_tag, name):
    enchant_list = nbtlib.TAG_List(type=nbtlib.TAG_Compound, name=name)
    for enchant_id, level_tag in component_tag.items():
        enchant = nbtlib.TAG_Compound()
        enchant['id'] = nbtlib.TAG_String(enchant_id)
        enchant['lvl'] = nbtlib.TAG_Short(level_tag.value)
        enchant_list.append(enchant)
    return enchant_list


def convert_fireworks_component(component_tag):
    fireworks = nbtlib.TAG_Compound()
    if 'flight_duration' in component_tag:
        fireworks['Flight'] = nbtlib.TAG_Byte(component_tag['flight_duration'].value)
    if 'explosions' in component_tag and len(component_tag['explosions']) > 0:
        explosions_list = nbtlib.TAG_List(type=nbtlib.TAG_Compound, name='Explosions')
        for explosion in component_tag['explosions']:
            explosion_tag = nbtlib.TAG_Compound()
            if 'shape' in explosion:
                shape = explosion['shape'].value
                shapes = {
                    'small_ball': 0,
                    'large_ball': 1,
                    'star': 2,
                    'creeper': 3,
                    'burst': 4,
                }
                if shape in shapes:
                    explosion_tag['Type'] = nbtlib.TAG_Byte(shapes[shape])
            if 'has_trail' in explosion:
                explosion_tag['Trail'] = nbtlib.TAG_Byte(1 if bool(explosion['has_trail'].value) else 0)
            if 'has_twinkle' in explosion:
                explosion_tag['Flicker'] = nbtlib.TAG_Byte(1 if bool(explosion['has_twinkle'].value) else 0)
            if 'colors' in explosion and len(explosion['colors']) > 0:
                colors_list = nbtlib.TAG_List(type=nbtlib.TAG_Int, name='Colors')
                for color in explosion['colors']:
                    colors_list.append(nbtlib.TAG_Int(color.value))
                explosion_tag['Colors'] = colors_list
            if 'fade_colors' in explosion and len(explosion['fade_colors']) > 0:
                fade_list = nbtlib.TAG_List(type=nbtlib.TAG_Int, name='FadeColors')
                for color in explosion['fade_colors']:
                    fade_list.append(nbtlib.TAG_Int(color.value))
                explosion_tag['FadeColors'] = fade_list
            explosions_list.append(explosion_tag)
        fireworks['Explosions'] = explosions_list
    return fireworks


def _dimension_suffix(dimension, fallback=''):
    mapping = {
        'minecraft:overworld': '',
        'minecraft:the_nether': '_nether',
        'minecraft:the_end': '_the_end',
        'minecraft:overworld/caves': '',
    }
    numeric_map = {
        0: '',
        -1: '_nether',
        1: '_the_end',
    }

    if isinstance(dimension, nbtlib.TAG_String):
        return mapping.get(dimension.value, fallback)
    if isinstance(dimension, nbtlib.TAG_Int):
        return numeric_map.get(dimension.value, fallback)
    if isinstance(dimension, str):
        return mapping.get(dimension, fallback)
    if isinstance(dimension, int):
        return numeric_map.get(dimension, fallback)
    return fallback


def normalize_item_tag(item_tag, slot=None):
    normalized = nbtlib.TAG_Compound()

    slot_value = None
    if slot is not None:
        slot_value = slot
    elif 'Slot' in item_tag:
        slot_value = item_tag['Slot'].value
    if slot_value is not None:
        normalized['Slot'] = nbtlib.TAG_Byte(slot_value)

    if 'id' in item_tag:
        normalized['id'] = nbtlib.TAG_String(item_tag['id'].value)

    count_value = 1
    if 'Count' in item_tag:
        count_value = item_tag['Count'].value
    elif 'count' in item_tag:
        count_value = item_tag['count'].value
    normalized['Count'] = nbtlib.TAG_Byte(count_value)

    if 'tag' in item_tag:
        normalized['tag'] = item_tag['tag']
    elif 'components' in item_tag:
        legacy_tag = components_to_legacy_tag(item_tag['components'], normalized.get('id').value if 'id' in normalized else None)
        if len(legacy_tag) > 0:
            normalized['tag'] = legacy_tag

    return normalized


def components_to_legacy_tag(components_tag, item_id=None):
    legacy = nbtlib.TAG_Compound()
    if not isinstance(components_tag, nbtlib.TAG_Compound):
        return legacy

    if 'minecraft:enchantments' in components_tag:
        enchant_component = components_tag['minecraft:enchantments']
        if isinstance(enchant_component, nbtlib.TAG_List):
            enchant_list = nbtlib.TAG_List(type=nbtlib.TAG_Compound, name='Enchantments')
            for entry in enchant_component:
                enchant = nbtlib.TAG_Compound()
                enchant['id'] = nbtlib.TAG_String(entry['enchantment'].value)
                enchant['lvl'] = nbtlib.TAG_Short(entry['level'].value)
                enchant_list.append(enchant)
            legacy['Enchantments'] = enchant_list
        else:
            legacy['Enchantments'] = _build_enchantment_list(enchant_component, 'Enchantments')

    if 'minecraft:stored_enchantments' in components_tag:
        stored_component = components_tag['minecraft:stored_enchantments']
        legacy['StoredEnchantments'] = _build_enchantment_list(stored_component, 'StoredEnchantments')

    if 'minecraft:repair_cost' in components_tag:
        legacy['RepairCost'] = nbtlib.TAG_Int(components_tag['minecraft:repair_cost'].value)

    if 'minecraft:damage' in components_tag:
        legacy['Damage'] = nbtlib.TAG_Int(components_tag['minecraft:damage'].value)

    if 'minecraft:fireworks' in components_tag:
        fireworks = convert_fireworks_component(components_tag['minecraft:fireworks'])
        if len(fireworks) > 0:
            legacy['Fireworks'] = fireworks

    if 'minecraft:container' in components_tag:
        legacy['BlockEntityTag'] = convert_container_component(components_tag['minecraft:container'], item_id)

    return legacy


def _container_block_entity_id(item_id):
    if not item_id:
        return 'minecraft:chest'
    if item_id.endswith('_shulker_box'):
        return 'minecraft:shulker_box'
    return item_id


def convert_container_component(container_list, item_id=None):
    block_entity_tag = nbtlib.TAG_Compound()
    block_entity_tag['id'] = nbtlib.TAG_String(_container_block_entity_id(item_id))
    items_list = nbtlib.TAG_List(type=nbtlib.TAG_Compound, name='Items')
    for entry in container_list:
        slot_value = entry['slot'].value
        normalized = normalize_item_tag(entry['item'], slot=slot_value)
        items_list.append(normalized)
    block_entity_tag['Items'] = items_list
    return block_entity_tag


def serialize_enchantments(enchantments_tag):
    id_to_enchant = {
        'protection': 'PROTECTION_ENVIRONMENTAL',
        'fire_protection': 'PROTECTION_FIRE',
        'feather_falling': 'PROTECTION_FALL',
        'blast_protection': 'PROTECTION_EXPLOSIONS',
        'projectile_protection': 'PROTECTION_PROJECTILE',
        'respiration': 'OXYGEN',
        'aqua_affinity': 'WATER_WORKER',
        'sharpness': 'DAMAGE_ALL',
        'smite': 'DAMAGE_UNDEAD',
        'bane_of_arthropods': 'DAMAGE_ARTHROPODS',
        'looting': 'LOOT_BONUS_MOBS',
        'sweeping': 'SWEEPING_EDGE',
        'efficiency': 'DIG_SPEED',
        'unbreaking': 'DURABILITY',
        'fortune': 'LOOT_BONUS_BLOCKS',
        'power': 'ARROW_DAMAGE',
        'punch': 'ARROW_KNOCKBACK',
        'flame': 'ARROW_FIRE',
        'infinity': 'ARROW_INFINITE',
        'luck_of_the_sea': 'LUCK',
    }

    result = {}
    for enchant in enchantments_tag:
        enchant_id = enchant['id'].value.split(':')[1]
        enchant_name = id_to_enchant.get(enchant_id, enchant_id.upper())
        result[enchant_name] = enchant['lvl'].value
    return result


def serialize_color(color_int, has_alpha=False):
    return {
        '==': 'Color',
        'ALPHA': color_int >> 24 & 0xff if has_alpha else 255,
        'RED': color_int >> 16 & 0xff,
        'BLUE': color_int >> 0 & 0xff,
        'GREEN': color_int >> 8 & 0xff
    }


def serialize_potion_effect(effect):
    return {
        '==': 'PotionEffect',
        'effect': effect['Id'].value,
        'duration': effect['Duration'].value,
        'amplifier': effect['Amplifier'].value,
        'ambient': bool(effect['Ambient'].value),
        'has-particles': bool(effect['ShowParticles'].value),
        'has-icon': bool(effect['ShowIcon'].value),
    }


def serialize_explosion_effect(effect):
    effect_types = ('BALL', 'BALL_LARGE', 'STAR', 'CREEPER', 'BURST')
    return {
        '==': 'Firework',
        'flicker': bool(effect.get('Flicker', False)),
        'trail': bool(effect.get('Trail', False)),
        'colors': [serialize_color(color) for color in effect['Colors']],  # always has color
        'fade-colors': [serialize_color(color) for color in effect.get('FadeColors', [])],
        'type': effect_types[effect['Type'].value]
    }


def serialize_modifiers(modifiers):
    result = {}
    for modifier in modifiers:
        hexed_uuid = [format(num & 0xffffffff, '08x') for num in modifier['UUID']]
        attrib_mod = {
            "==": "org.bukkit.attribute.AttributeModifier",
            'amount': modifier['Amount'].value,
            'name': modifier['Name'].value,
            'uuid': f'{hexed_uuid[0]}-{hexed_uuid[1][:4]}-{hexed_uuid[1][4:8]}-{hexed_uuid[2][:4]}-{hexed_uuid[2][4:8]}{hexed_uuid[3]}',
            'operation': modifier['Operation'].value,
        }
        if 'Slot' in modifier:
            attrib_mod['slot'] = modifier['Slot'].value.upper()
            if attrib_mod['slot'] == 'MAINHAND':
                attrib_mod['slot'] = 'HAND'
            elif attrib_mod['slot'] == 'OFFHAND':
                attrib_mod['slot'] = 'OFF_HAND'
        attrib_name = modifier['AttributeName'].value.split(':')[1].replace('.', '_').upper()
        attrib = result.setdefault(attrib_name, [])
        attrib.append(attrib_mod)
    return result


def serialize_meta_armor(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'ARMOR')
    if 'Trim' in meta_item_tag:
        trim = meta_item_tag['Trim']
        if 'material' in trim and 'pattern' in trim:
            meta['trim'] = {
                'material': trim['material'].value,
                'pattern': trim['pattern'].value
            }
    return meta


def serialize_meta_armor_stand(meta_item_tag):
    internal_tag = None
    if 'EntityTag' in meta_item_tag and len(meta_item_tag['EntityTag']) > 0:
        internal_tag = meta_item_tag['EntityTag']
    meta = serialize_meta_item(meta_item_tag, 'ARMOR_STAND', internal_tag)
    return meta


def serialize_meta_banner(meta_item_tag):
    dye_colors = ('WHITE', 'ORANGE', 'MAGENTA', 'LIGHT_BLUE', 'YELLOW', 'LIME', 'PINK', 'GRAY',
                  'LIGHT_GRAY', 'CYAN', 'PURPLE', 'BLUE', 'BROWN', 'GREEN', 'RED', 'BLACK')
    meta = serialize_meta_item(meta_item_tag, 'BANNER')
    entity_tag = meta_item_tag.get('BlockEntityTag')
    if entity_tag is None:
        return meta
    if 'Base' in entity_tag:
        meta['base-color'] = dye_colors[entity_tag['Base'].value]
    if 'Patterns' in entity_tag and len(entity_tag['Patterns']) > 0:
        meta['patterns'] = []
        for pattern in entity_tag['Patterns']:
            meta['patterns'].append(
                {
                    '==': 'Pattern',
                    'color': dye_colors[pattern['Color'].value],
                    'pattern': pattern['Pattern'].value
                }
            )
    return meta


def serialize_meta_block_state(meta_item_tag, item_type):
    internal_tag = meta_item_tag.get('BlockEntityTag')
    meta = serialize_meta_item(meta_item_tag, 'TILE_ENTITY', internal_tag)
    meta['blockMaterial'] = item_type
    return meta


def serialize_meta_book(meta_item_tag, meta_type='BOOK'):
    meta = serialize_meta_item(meta_item_tag, meta_type)
    if 'title' in meta_item_tag:
        meta['title'] = meta_item_tag['title'].value
    if 'author' in meta_item_tag:
        meta['author'] = meta_item_tag['author'].value
    if 'pages' in meta_item_tag:
        pages = meta_item_tag['pages']
        # TODO: Implement book pages normalization
        # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaBook.java#111
        # max_page_length = 320
        # if meta_type == 'BOOK_SIGNED':
        # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/util/CraftChatMessage.java
        #     page = CraftChatMessage.fromJSONOrStringToJSON(page,
        #                                                    nullable=false,
        #                                                    keepNewlines=true,
        #                                                    max_page_length,
        #                                                    checkJsonContentLength=false) ->
        #     page = "" if null
        #     IChatBaseComponent component = IChatBaseComponent.ChatSerializer.fromJson(page)
        #     if component: return page
        #     else:
        #         page = page[:max_page_length]
        #         IChatBaseComponent component = new StringMessage(page, keepNewlines=true, plain=false).getOutput()[0]
        #         json_page = IChatBaseComponent.ChatSerializer.toJson(component)
        #
        # else:
        #    pages = [page[:max_page_length] for page in pages]
        meta['pages'] = [page.value for page in pages]
    if 'resolved' in meta_item_tag:
        meta['resolved'] = bool(meta_item_tag['resolved'].value)
    if 'generation' in meta_item_tag:
        meta['generation'] = meta_item_tag['generation'].value
    return meta


def serialize_meta_book_signed(meta_item_tag):
    meta = serialize_meta_book(meta_item_tag, 'BOOK_SIGNED')
    return meta


def serialize_meta_skull(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'SKULL')
    # TODO: Implement skull owner profile serialization
    # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaSkull.java
    if 'SkullOwner' in meta_item_tag:
        # meta['skull-owner'] =
        # meta_item_tag['SkullOwner'] # TAG_String or TAG_Compound
        # 1: profile = GameProfileSerializer.readGameProfile(TAG_Compound)
        # 2: profile = GameProfile(TAG_String) # UUID ?
        #    -> CraftPlayerProfile(profile).serialize
        #    https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/profile/CraftPlayerProfile.java#239
        #    {
        #        '==': 'PlayerProfile',
        #        'uniqueId': '',  #if no null
        #        'name': '',  #if not null
        #        'properties': []  #if has properties
        #    }
        pass
    if 'BlockEntityTag' in meta_item_tag and 'note_block_sound' in meta_item_tag['BlockEntityTag']:
        meta['note_block_sound'] = meta_item_tag['BlockEntityTag']['note_block_sound'].value
    return meta


def serialize_meta_leather_armor(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'LEATHER_ARMOR')
    if 'display' in meta_item_tag and 'color' in meta_item_tag['display']:
        meta['color'] = serialize_color(meta_item_tag['display']['color'].value)
    return meta


def serialize_meta_colorable_armor(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'COLORABLE_ARMOR')
    if 'display' in meta_item_tag and 'color' in meta_item_tag['display']:
        meta['color'] = serialize_color(meta_item_tag['display']['color'].value)
    return meta


def serialize_meta_map(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'MAP')
    if 'map' in meta_item_tag:
        meta['map-id'] = meta_item_tag['map'].value
    if 'map_is_scaling' in meta_item_tag:
        meta['scaling'] = bool(meta_item_tag['map_is_scaling'].value)
    if 'display' in meta_item_tag and 'MapColor' in meta_item_tag['display']:
        meta['display-map-color'] = serialize_color(meta_item_tag['display']['MapColor'].value)
    return meta


def serialize_meta_potion(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'POTION')
    if 'Potion' in meta_item_tag and meta_item_tag['Potion'].value != 'empty':
        meta['potion-type'] = meta_item_tag['Potion'].value
    if 'CustomPotionColor' in meta_item_tag:
        meta['custom-color'] = serialize_color(meta_item_tag['CustomPotionColor'].value)
    if 'custom_potion_effects' in meta_item_tag:
        meta['custom-effects'] = [serialize_potion_effect(effect) for effect in meta_item_tag['custom_potion_effects']]
    return meta


def serialize_meta_spawn_egg(meta_item_tag):
    internal_tag = None
    if 'EntityTag' in meta_item_tag and len(meta_item_tag['EntityTag']) > 0:
        internal_tag = meta_item_tag['EntityTag']
    meta = serialize_meta_item(meta_item_tag, 'SPAWN_EGG', internal_tag)
    return meta


def serialize_meta_enchanted_book(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'ENCHANTED')
    meta['stored-enchants'] = serialize_enchantments(meta_item_tag['StoredEnchantments'])
    return meta


def serialize_meta_firework(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'FIREWORK')
    if 'Fireworks' in meta_item_tag:
        fireworks = meta_item_tag['Fireworks']
        if 'Explosions' in fireworks:
            meta['firework-effects'] = [serialize_explosion_effect(effect) for effect in fireworks['Explosions']]
        meta['power'] = fireworks['Flight'].value
    return meta


def serialize_meta_charge(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'FIREWORK_EFFECT')
    if 'Explosion' in meta_item_tag:
        meta['firework-effect'] = serialize_explosion_effect(meta_item_tag['Explosion'])
    return meta


def serialize_meta_knowledge_book(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'KNOWLEDGE_BOOK')
    # TODO: Test knowledge book
    if 'Recipes' in meta_item_tag and len(meta_item_tag['Recipes']) > 0:
        meta['Recipes'] = [recipe.value for recipe in meta_item_tag['Recipes']]
    return meta


def serialize_meta_tropical_fish_bucket(meta_item_tag):
    internal_tag = None
    if 'EntityTag' in meta_item_tag and len(meta_item_tag['EntityTag']) > 0:
        internal_tag = meta_item_tag['EntityTag']
    meta = serialize_meta_item(meta_item_tag, 'TROPICAL_FISH_BUCKET', internal_tag)
    if 'BucketVariantTag' in meta_item_tag:
        meta['fish-variant'] = meta_item_tag['BucketVariantTag'].value
    return meta


def serialize_meta_axolotl_bucket(meta_item_tag):
    internal_tag = None
    if 'EntityTag' in meta_item_tag and len(meta_item_tag['EntityTag']) > 0:
        internal_tag = meta_item_tag['EntityTag']
    meta = serialize_meta_item(meta_item_tag, 'AXOLOTL_BUCKET', internal_tag)
    if 'Variant' in meta_item_tag:
        meta['axolotl-variant'] = meta_item_tag['Variant'].value
    return meta


def serialize_meta_crossbow(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'CROSSBOW')
    meta['charged'] = bool(meta_item_tag['Charged'].value)
    if 'ChargedProjectiles' in meta_item_tag and len(meta_item_tag['ChargedProjectiles']) > 0:
        meta['charged-projectiles'] = [serialize_item_stack(item_stack)
                                       for item_stack
                                       in meta_item_tag['ChargedProjectiles']]
    return meta


def serialize_meta_suspicious_stew(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'SUSPICIOUS_STEW')
    if 'effects' in meta_item_tag:
        meta['effects'] = [serialize_potion_effect(effect) for effect in meta_item_tag['effects']]
    return meta


def serialize_meta_entity_tag(meta_item_tag):
    internal_tag = None
    if 'EntityTag' in meta_item_tag and len(meta_item_tag['EntityTag']) > 0:
        internal_tag = meta_item_tag['EntityTag']
    meta = serialize_meta_item(meta_item_tag, 'ENTITY_TAG', internal_tag)
    return meta


def serialize_meta_compass(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'COMPASS')
    if 'LodestoneDimension' in meta_item_tag and 'LodestonePos' in meta_item_tag:
        meta['LodestonePosWorld'] = meta_item_tag['LodestoneDimension'].value
        meta['LodestonePosX'] = meta_item_tag['LodestonePos']['X'].value
        meta['LodestonePosY'] = meta_item_tag['LodestonePos']['Y'].value
        meta['LodestonePosZ'] = meta_item_tag['LodestonePos']['Z'].value
    if 'LodestoneTracked' in meta_item_tag:
        meta['LodestoneTracked'] = bool(meta_item_tag['LodestoneTracked'].value)
    return meta


def serialize_meta_bundle(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'BUNDLE')
    if 'Items' in meta_item_tag and len(meta_item_tag['Items']) > 0:
        meta['items'] = [serialize_item_stack(item_stack) for item_stack in meta_item_tag['Items']]
    return meta


def serialize_meta_music_instrument(meta_item_tag):
    meta = serialize_meta_item(meta_item_tag, 'MUSIC_INSTRUMENT')
    if 'instrument' in meta_item_tag:
        meta['instrument'] = meta_item_tag['instrument'].value
    return meta


def serialize_meta_item(meta_item_tag, meta_type='UNSPECIFIC', internal_tag=None):
    # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaItem.java
    meta = {
        '==': 'ItemMeta',
        'meta-type': meta_type
    }

    if 'display' in meta_item_tag:
        display = meta_item_tag['display']
        if 'Name' in display:
            meta['display-name'] = display['Name'].value
        if 'LocName' in display:
            meta['loc-name'] = display['LocName'].value
        if 'Lore' in display and len(display['Lore']) > 0:
            meta['lore'] = [text.value for text in display['Lore']]

    if 'CustomModelData' in meta_item_tag:
        meta['custom-model-data'] = meta_item_tag['CustomModelData'].value

    if 'BlockStateTag' in meta_item_tag:
        # TODO: Implement item BlockStateTag serialization
        # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaItem.java#1250
        # blockData = meta_item_tag['BlockStateTag'] # TAG_Compound
        # meta['BlockStateTag'] = CraftNBTTagConfigSerializer.serialize(blockData)
        #       -> return SnbtPrinterTagVisitor().visit(blockData) (net.minecraft.nbt.SnbtPrinterTagVisitor)
        pass

    if 'Enchantments' in meta_item_tag and len(meta_item_tag['Enchantments']) > 0:
        meta['enchants'] = serialize_enchantments(meta_item_tag['Enchantments'])

    if 'AttributeModifiers' in meta_item_tag and len(meta_item_tag['AttributeModifiers']) > 0:
        meta['attribute-modifiers'] = serialize_modifiers(meta_item_tag['AttributeModifiers'])

    if 'RepairCost' in meta_item_tag and meta_item_tag['RepairCost'].value > 0:
        meta['repair-cost'] = meta_item_tag['RepairCost'].value

    if 'HideFlags' in meta_item_tag:
        hide_flag = meta_item_tag['HideFlags'].value
        item_flags = zip(format(hide_flag, '08b'),
                         ('HIDE_ARMOR_TRIM', 'HIDE_DYE', 'HIDE_POTION_EFFECTS', 'HIDE_PLACED_ON',
                          'HIDE_DESTROYS', 'HIDE_UNBREAKABLE', 'HIDE_ATTRIBUTES', 'HIDE_ENCHANTS')
                         )
        meta['ItemFlags'] = [flag for bit, flag in item_flags if bit == '1']

    if 'Unbreakable' in meta_item_tag:
        meta['Unbreakable'] = bool(meta_item_tag['Unbreakable'].value)

    if 'Damage' in meta_item_tag and meta_item_tag['Damage'].value > 0:
        meta['Damage'] = meta_item_tag['Damage'].value

    internal = [meta_item_tag[tag] for tag in meta_item_tag if tag not in HANDLED_TAGS]
    if internal_tag is not None:
        internal.append(internal_tag)
    if len(internal) > 0:
        with io.BytesIO() as out:
            internal_nbt = nbtlib.NBTFile()
            internal_nbt.tags = internal
            internal_nbt.write_file(fileobj=out)
            meta['internal'] = base64.b64encode(out.getvalue()).decode('utf-8')

    # TODO: Implement item custom tags serialization
    # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/craftbukkit/browse/src/main/java/org/bukkit/craftbukkit/inventory/CraftMetaItem.java#1293
    # Store custom tags, wrapped in their compound
    # meta_item_tag['PublicBukkitValues']

    return meta


def serialize_meta_fn(item_type: str) -> ():
    funcs_map = {
        # ('AIR',): None,
        ('WRITTEN_BOOK',): serialize_meta_book_signed,
        ('WRITABLE_BOOK',): serialize_meta_book,
        ('CREEPER_HEAD', 'CREEPER_WALL_HEAD', 'DRAGON_HEAD', 'DRAGON_WALL_HEAD', 'PIGLIN_HEAD', 'PIGLIN_WALL_HEAD',
         'PLAYER_HEAD', 'PLAYER_WALL_HEAD', 'SKELETON_SKULL', 'SKELETON_WALL_SKULL', 'WITHER_SKELETON_SKULL',
         'WITHER_SKELETON_WALL_SKULL', 'ZOMBIE_HEAD', 'ZOMBIE_WALL_HEAD',): serialize_meta_skull,
        ('CHAINMAIL_HELMET', 'CHAINMAIL_CHESTPLATE', 'CHAINMAIL_LEGGINGS', 'CHAINMAIL_BOOTS', 'DIAMOND_HELMET',
         'DIAMOND_CHESTPLATE', 'DIAMOND_LEGGINGS', 'DIAMOND_BOOTS', 'GOLDEN_HELMET', 'GOLDEN_CHESTPLATE',
         'GOLDEN_LEGGINGS', 'GOLDEN_BOOTS', 'IRON_HELMET', 'IRON_CHESTPLATE', 'IRON_LEGGINGS', 'IRON_BOOTS',
         'NETHERITE_HELMET', 'NETHERITE_CHESTPLATE', 'NETHERITE_LEGGINGS', 'NETHERITE_BOOTS',
         'TURTLE_HELMET',): serialize_meta_armor,
        ('LEATHER_HELMET', 'LEATHER_CHESTPLATE', 'LEATHER_LEGGINGS', 'LEATHER_BOOTS',): serialize_meta_colorable_armor,
        ('LEATHER_HORSE_ARMOR',): serialize_meta_leather_armor,
        ('POTION', 'SPLASH_POTION', 'LINGERING_POTION', 'TIPPED_ARROW',): serialize_meta_potion,
        ('FILLED_MAP',): serialize_meta_map,
        ('FIREWORK_ROCKET',): serialize_meta_firework,
        ('FIREWORK_STAR',): serialize_meta_charge,
        ('ENCHANTED_BOOK',): serialize_meta_enchanted_book,
        ('BLACK_BANNER', 'BLACK_WALL_BANNER', 'BLUE_BANNER', 'BLUE_WALL_BANNER', 'BROWN_BANNER', 'BROWN_WALL_BANNER',
         'CYAN_BANNER', 'CYAN_WALL_BANNER', 'GRAY_BANNER', 'GRAY_WALL_BANNER', 'GREEN_BANNER', 'GREEN_WALL_BANNER',
         'LIGHT_BLUE_BANNER', 'LIGHT_BLUE_WALL_BANNER', 'LIGHT_GRAY_BANNER', 'LIGHT_GRAY_WALL_BANNER', 'LIME_BANNER',
         'LIME_WALL_BANNER', 'MAGENTA_BANNER', 'MAGENTA_WALL_BANNER', 'ORANGE_BANNER', 'ORANGE_WALL_BANNER',
         'PINK_BANNER', 'PINK_WALL_BANNER', 'PURPLE_BANNER', 'PURPLE_WALL_BANNER', 'RED_BANNER', 'RED_WALL_BANNER',
         'WHITE_BANNER', 'WHITE_WALL_BANNER', 'YELLOW_BANNER', 'YELLOW_WALL_BANNER',): serialize_meta_banner,
        ('ALLAY_SPAWN_EGG', 'AXOLOTL_SPAWN_EGG', 'BAT_SPAWN_EGG', 'BEE_SPAWN_EGG', 'BLAZE_SPAWN_EGG',
         'BREEZE_SPAWN_EGG', 'CAT_SPAWN_EGG', 'CAMEL_SPAWN_EGG', 'CAVE_SPIDER_SPAWN_EGG', 'CHICKEN_SPAWN_EGG',
         'COD_SPAWN_EGG', 'COW_SPAWN_EGG', 'CREEPER_SPAWN_EGG', 'DOLPHIN_SPAWN_EGG', 'DONKEY_SPAWN_EGG',
         'DROWNED_SPAWN_EGG', 'ELDER_GUARDIAN_SPAWN_EGG', 'ENDER_DRAGON_SPAWN_EGG', 'ENDERMAN_SPAWN_EGG',
         'ENDERMITE_SPAWN_EGG', 'EVOKER_SPAWN_EGG', 'FOX_SPAWN_EGG', 'FROG_SPAWN_EGG', 'GHAST_SPAWN_EGG',
         'GLOW_SQUID_SPAWN_EGG', 'GOAT_SPAWN_EGG', 'GUARDIAN_SPAWN_EGG', 'HOGLIN_SPAWN_EGG', 'HORSE_SPAWN_EGG',
         'HUSK_SPAWN_EGG', 'IRON_GOLEM_SPAWN_EGG', 'LLAMA_SPAWN_EGG', 'MAGMA_CUBE_SPAWN_EGG', 'MOOSHROOM_SPAWN_EGG',
         'MULE_SPAWN_EGG', 'OCELOT_SPAWN_EGG', 'PANDA_SPAWN_EGG', 'PARROT_SPAWN_EGG', 'PHANTOM_SPAWN_EGG',
         'PIGLIN_BRUTE_SPAWN_EGG', 'PIGLIN_SPAWN_EGG', 'PIG_SPAWN_EGG', 'PILLAGER_SPAWN_EGG', 'POLAR_BEAR_SPAWN_EGG',
         'PUFFERFISH_SPAWN_EGG', 'RABBIT_SPAWN_EGG', 'RAVAGER_SPAWN_EGG', 'SALMON_SPAWN_EGG', 'SHEEP_SPAWN_EGG',
         'SHULKER_SPAWN_EGG', 'SILVERFISH_SPAWN_EGG', 'SKELETON_HORSE_SPAWN_EGG', 'SKELETON_SPAWN_EGG',
         'SLIME_SPAWN_EGG', 'SNIFFER_SPAWN_EGG', 'SNOW_GOLEM_SPAWN_EGG', 'SPIDER_SPAWN_EGG', 'SQUID_SPAWN_EGG',
         'STRAY_SPAWN_EGG', 'STRIDER_SPAWN_EGG', 'TADPOLE_SPAWN_EGG', 'TRADER_LLAMA_SPAWN_EGG',
         'TROPICAL_FISH_SPAWN_EGG', 'TURTLE_SPAWN_EGG', 'VEX_SPAWN_EGG', 'VILLAGER_SPAWN_EGG', 'VINDICATOR_SPAWN_EGG',
         'WANDERING_TRADER_SPAWN_EGG', 'WARDEN_SPAWN_EGG', 'WITCH_SPAWN_EGG', 'WITHER_SKELETON_SPAWN_EGG',
         'WITHER_SPAWN_EGG', 'WOLF_SPAWN_EGG', 'ZOGLIN_SPAWN_EGG', 'ZOMBIE_HORSE_SPAWN_EGG', 'ZOMBIE_SPAWN_EGG',
         'ZOMBIE_VILLAGER_SPAWN_EGG', 'ZOMBIFIED_PIGLIN_SPAWN_EGG',): serialize_meta_spawn_egg,
        ('ARMOR_STAND',): serialize_meta_armor_stand,
        ('KNOWLEDGE_BOOK',): serialize_meta_knowledge_book,
        ('FURNACE', 'CHEST', 'TRAPPED_CHEST', 'JUKEBOX', 'DISPENSER', 'DROPPER', 'ACACIA_HANGING_SIGN', 'ACACIA_SIGN',
         'ACACIA_WALL_HANGING_SIGN', 'ACACIA_WALL_SIGN', 'BAMBOO_HANGING_SIGN', 'BAMBOO_SIGN',
         'BAMBOO_WALL_HANGING_SIGN', 'BAMBOO_WALL_SIGN', 'BIRCH_HANGING_SIGN', 'BIRCH_SIGN', 'BIRCH_WALL_HANGING_SIGN',
         'BIRCH_WALL_SIGN', 'CHERRY_HANGING_SIGN', 'CHERRY_SIGN', 'CHERRY_WALL_HANGING_SIGN', 'CHERRY_WALL_SIGN',
         'CRIMSON_HANGING_SIGN', 'CRIMSON_SIGN', 'CRIMSON_WALL_HANGING_SIGN', 'CRIMSON_WALL_SIGN',
         'DARK_OAK_HANGING_SIGN', 'DARK_OAK_SIGN', 'DARK_OAK_WALL_HANGING_SIGN', 'DARK_OAK_WALL_SIGN',
         'JUNGLE_HANGING_SIGN', 'JUNGLE_SIGN', 'JUNGLE_WALL_HANGING_SIGN', 'JUNGLE_WALL_SIGN', 'MANGROVE_HANGING_SIGN',
         'MANGROVE_SIGN', 'MANGROVE_WALL_HANGING_SIGN', 'MANGROVE_WALL_SIGN', 'OAK_HANGING_SIGN', 'OAK_SIGN',
         'OAK_WALL_HANGING_SIGN', 'OAK_WALL_SIGN', 'SPRUCE_HANGING_SIGN', 'SPRUCE_SIGN', 'SPRUCE_WALL_HANGING_SIGN',
         'SPRUCE_WALL_SIGN', 'WARPED_HANGING_SIGN', 'WARPED_SIGN', 'WARPED_WALL_HANGING_SIGN', 'WARPED_WALL_SIGN',
         'SPAWNER', 'BREWING_STAND', 'ENCHANTING_TABLE', 'COMMAND_BLOCK', 'REPEATING_COMMAND_BLOCK',
         'CHAIN_COMMAND_BLOCK', 'BEACON', 'DAYLIGHT_DETECTOR', 'HOPPER', 'COMPARATOR', 'SHIELD', 'STRUCTURE_BLOCK',
         'SHULKER_BOX', 'WHITE_SHULKER_BOX', 'ORANGE_SHULKER_BOX', 'MAGENTA_SHULKER_BOX', 'LIGHT_BLUE_SHULKER_BOX',
         'YELLOW_SHULKER_BOX', 'LIME_SHULKER_BOX', 'PINK_SHULKER_BOX', 'GRAY_SHULKER_BOX', 'LIGHT_GRAY_SHULKER_BOX',
         'CYAN_SHULKER_BOX', 'PURPLE_SHULKER_BOX', 'BLUE_SHULKER_BOX', 'BROWN_SHULKER_BOX', 'GREEN_SHULKER_BOX',
         'RED_SHULKER_BOX', 'BLACK_SHULKER_BOX', 'ENDER_CHEST', 'BARREL', 'BELL', 'BLAST_FURNACE', 'CAMPFIRE',
         'SOUL_CAMPFIRE', 'JIGSAW', 'LECTERN', 'SMOKER', 'BEEHIVE', 'BEE_NEST', 'SCULK_CATALYST', 'SCULK_SHRIEKER',
         'SCULK_SENSOR', 'CALIBRATED_SCULK_SENSOR', 'CHISELED_BOOKSHELF', 'DECORATED_POT', 'SUSPICIOUS_SAND',
         'SUSPICIOUS_GRAVEL', 'CRAFTER', 'TRIAL_SPAWNER',): serialize_meta_block_state,
        ('TROPICAL_FISH_BUCKET',): serialize_meta_tropical_fish_bucket,
        ('AXOLOTL_BUCKET',): serialize_meta_axolotl_bucket,
        ('CROSSBOW',): serialize_meta_crossbow,
        ('SUSPICIOUS_STEW',): serialize_meta_suspicious_stew,
        ('COD_BUCKET', 'PUFFERFISH_BUCKET', 'SALMON_BUCKET', 'ITEM_FRAME', 'GLOW_ITEM_FRAME',
         'PAINTING',): serialize_meta_entity_tag,
        ('COMPASS',): serialize_meta_compass,
        ('BUNDLE',): serialize_meta_bundle,
        ('GOAT_HORN',): serialize_meta_music_instrument,
    }

    for item_types, fn in funcs_map.items():
        if item_type in item_types:
            return fn
    return serialize_meta_item  # default serialize meta function


def get_item_meta(item_type, meta_item_tag):
    serialize_fn = serialize_meta_fn(item_type)
    if serialize_fn is serialize_meta_block_state:
        meta = serialize_fn(meta_item_tag, item_type)
    else:
        meta = serialize_fn(meta_item_tag)
    return meta


def serialize_item_stack(item_tag):
    item_tag = normalize_item_tag(item_tag)
    # https://hub.spigotmc.org/stash/projects/SPIGOT/repos/bukkit/browse/src/main/java/org/bukkit/inventory/ItemStack.java#466
    item_data = {
        '==': 'org.bukkit.inventory.ItemStack',
        'v': BUKKIT_VERSION,
        'type': item_tag['id'].value.split(':')[1].upper(),
    }

    # add item amount
    if item_tag['Count'].value != 1:
        item_data['amount'] = item_tag['Count'].value

    # add item meta
    if 'tag' in item_tag:
        item_data['meta'] = get_item_meta(item_data['type'], item_tag['tag'])

    return item_data


def serialize_player_nbt(player_nbt, mv_world):
    # https://github.com/Multiverse/Multiverse-Inventories/blob/main/src/main/java/com/onarandombox/multiverseinventories/share/Sharables.java
    output_game_mode = 'SURVIVAL'

    def valuestr_or(default, *names):
        for name in names:
            if name in player_nbt:
                return player_nbt[name].valuestr()
        return default

    # Build default empty json structure
    dimension_suffix = _dimension_suffix(player_nbt['Dimension'])

    json_data = {
        output_game_mode: {
            'inventoryContents': {},
            'offHandItem': {
                "==": "org.bukkit.inventory.ItemStack",
                "v": BUKKIT_VERSION,
                "type": "AIR",
                "amount": 0
            },
            'potions': [],
            'enderChestContents': {},
            'armorContents': {},
        }
    }

    # Parse inventory
    for tag in player_nbt['Inventory']:
        slot = tag['Slot'].value
        if slot >= 100:
            json_data[output_game_mode]['armorContents'][str(slot - 100)] = serialize_item_stack(tag)
        elif slot == -106:
            json_data[output_game_mode]['offHandItem'] = serialize_item_stack(tag)
        else:
            json_data[output_game_mode]['inventoryContents'][str(slot)] = serialize_item_stack(tag)

    if 'equipment' in player_nbt:
        equipment = player_nbt['equipment']
        armor_slot_map = {
            'feet': '0',
            'legs': '1',
            'chest': '2',
            'head': '3',
        }
        for key, idx in armor_slot_map.items():
            if key in equipment:
                json_data[output_game_mode]['armorContents'][idx] = serialize_item_stack(equipment[key])
        if 'off_hand' in equipment:
            json_data[output_game_mode]['offHandItem'] = serialize_item_stack(equipment['off_hand'])

    # Parse Ender chest
    for tag in player_nbt['EnderItems']:
        json_data[output_game_mode]['enderChestContents'][str(tag['Slot'].value)] = serialize_item_stack(tag)

    # Parse last location
    json_data[output_game_mode]['lastLocation'] = {
        '==': 'org.bukkit.Location',
        'world': mv_world + dimension_suffix,
        'x': player_nbt['Pos'][0].value,
        'y': player_nbt['Pos'][1].value,
        'z': player_nbt['Pos'][2].value,
        'pitch': player_nbt['Rotation'][0].value,
        'yaw': player_nbt['Rotation'][1].value,
    }

    # Parse spawn location
    spawn_location = None
    if {'SpawnDimension', 'SpawnX', 'SpawnY', 'SpawnZ', 'SpawnAngle'}.issubset(player_nbt.keys()):
        spawn_location = {
            '==': 'org.bukkit.Location',
            'world': mv_world + _dimension_suffix(player_nbt['SpawnDimension']),
            'x': player_nbt['SpawnX'].value,
            'y': player_nbt['SpawnY'].value,
            'z': player_nbt['SpawnZ'].value,
            'pitch': 0,
            'yaw': player_nbt['SpawnAngle'].value
        }
    elif 'respawn' in player_nbt:
        respawn = player_nbt['respawn']
        respawn_dimension = respawn['dimension'] if 'dimension' in respawn else 'minecraft:overworld'
        respawn_suffix = _dimension_suffix(respawn_dimension)
        respawn_pos = list(respawn['pos']) if 'pos' in respawn else [0, 0, 0]
        spawn_location = {
            '==': 'org.bukkit.Location',
            'world': mv_world + respawn_suffix,
            'x': respawn_pos[0],
            'y': respawn_pos[1],
            'z': respawn_pos[2],
            'pitch': respawn['pitch'].value if 'pitch' in respawn else 0,
            'yaw': respawn['yaw'].value if 'yaw' in respawn else 0,
        }
    if spawn_location is None:
        spawn_location = {
            '==': 'org.bukkit.Location',
            'world': json_data[output_game_mode]['lastLocation']['world'],
            'x': json_data[output_game_mode]['lastLocation']['x'],
            'y': json_data[output_game_mode]['lastLocation']['y'],
            'z': json_data[output_game_mode]['lastLocation']['z'],
            'pitch': 0,
            'yaw': json_data[output_game_mode]['lastLocation']['yaw'],
        }
    json_data[output_game_mode]['bedSpawnLocation'] = spawn_location

    # Parse potion effects
    if 'ActiveEffects' in player_nbt:
        json_data[output_game_mode]['potions'] = [serialize_potion_effect(effect) for effect in player_nbt['ActiveEffects']]

    # Parse stats
    json_data[output_game_mode]['stats'] = {
        'ex': valuestr_or('0', 'foodExhaustionLevel'),  # Float
        'ma': '300',  # Integer (max air)
        'fl': valuestr_or('0', 'foodLevel'),  # Integer
        'el': valuestr_or('0', 'XpLevel'),  # Integer
        'xp': valuestr_or('0', 'XpP'),  # Float
        'hp': valuestr_or('0', 'Health'),  # Double
        'txp': valuestr_or('0', 'XpTotal'),  # Integer
        'fd': valuestr_or('0', 'FallDistance', 'fall_distance'),  # Float
        'ft': valuestr_or('0', 'Fire'),  # Integer
        'sa': valuestr_or('0', 'foodSaturationLevel'),  # Float
        'ra': valuestr_or('0', 'Air'),  # Integer
    }

    return json_data


def _uuid_from_player(player):
    if 'UUID' in player:
        value = 0
        for part in player['UUID']:
            value = (value << 32) | (part & 0xffffffff)
        return str(uuid.UUID(int=value))
    if 'UUIDMost' in player and 'UUIDLeast' in player:
        most = player['UUIDMost'].value & ((1 << 64) - 1)
        least = player['UUIDLeast'].value & ((1 << 64) - 1)
        combined = (most << 64) | least
        return str(uuid.UUID(int=combined))
    return None


def convert_player_file(player_filename, mv_world='world', output_dir=None):
    player_path = Path(player_filename)
    player = nbtlib.NBTFile(str(player_path), 'rb')

    global BUKKIT_VERSION
    previous_version = BUKKIT_VERSION
    data_version = player.get('DataVersion')
    if data_version is not None:
        BUKKIT_VERSION = data_version.value
    else:
        BUKKIT_VERSION = DEFAULT_BUKKIT_VERSION

    try:
        json_data = serialize_player_nbt(player, mv_world)
    finally:
        BUKKIT_VERSION = previous_version

    name = None
    if 'bukkit' in player and 'lastKnownName' in player['bukkit']:
        name = player['bukkit']['lastKnownName'].value

    player_uuid = _uuid_from_player(player)

    output_root = Path(output_dir) if output_dir else Path('out')
    players_dir = output_root / 'players'
    groups_dir = output_root / 'groups' / mv_world
    worlds_dir = output_root / 'worlds' / mv_world

    players_dir.mkdir(parents=True, exist_ok=True)
    groups_dir.mkdir(parents=True, exist_ok=True)
    worlds_dir.mkdir(parents=True, exist_ok=True)

    outputs = {'root': output_root}
    if name:
        group_path = groups_dir / f"{name}.json"
        with group_path.open('w') as out_file:
            json.dump(json_data, out_file)
        world_path = worlds_dir / f"{name}.json"
        with world_path.open('w') as out_file:
            json.dump(json_data, out_file)
        outputs['group_path'] = group_path
        outputs['world_path'] = world_path

    if player_uuid:
        uuid_path = players_dir / f"{player_uuid}.json"
        uuid_payload = {
            "playerData": {
                "lastWorld": mv_world,
                "lastKnownName": name or "",
                "loadOnLogin": False,
            }
        }
        with uuid_path.open('w') as out_file:
            json.dump(uuid_payload, out_file)
        outputs['uuid_path'] = uuid_path

    outputs['source'] = player_path
    outputs['world'] = mv_world
    outputs['uuid'] = player_uuid
    outputs['name'] = name
    return outputs


def collect_player_files(paths):
    files = []
    seen = set()
    for entry in paths:
        path = Path(entry)
        if path.is_dir():
            candidates = []
            for pattern in ('*.dat', '*.nbt'):
                candidates.extend(sorted(path.rglob(pattern)))
        else:
            if not path.exists():
                raise FileNotFoundError(f'Path does not exist: "{path}"')
            candidates = [path]
        if not candidates:
            raise FileNotFoundError(f'No player files found in "{path}"')
        for candidate in candidates:
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(candidate)
    return files


def main(player_filenames, mv_world='world', output_dir=None):
    results = []
    for filename in player_filenames:
        results.append(convert_player_file(filename, mv_world, output_dir))
    return results


def test():
    player = nbtlib.NBTFile('76121406-7ac6-32c8-90ee-2368a675ad02.dat', 'rb')
    result = serialize_player_nbt(player, 'world')
    print(result)


def cli():
    parser = argparse.ArgumentParser(description='Convert player data NBT into Multiverse JSON format.')
    parser.add_argument('player_dat', nargs='+', help='Path(s) to player .dat/.nbt files or directories containing them')
    parser.add_argument('-w', '--world', default='world', help='Multiverse world name (default: world)')
    parser.add_argument('-o', '--output-dir', help='Directory to place generated JSON files')
    args = parser.parse_args()
    try:
        player_files = collect_player_files(args.player_dat)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    if not player_files:
        parser.error('No player files were found to convert.')

    results = main(player_files, args.world, args.output_dir)
    for result in results:
        created = []
        root = result.get('root')

        def rel(path):
            if not path:
                return None
            try:
                if root:
                    return path.relative_to(root)
            except ValueError:
                pass
            return path

        for key in ('group_path', 'world_path', 'uuid_path'):
            path = result.get(key)
            if path:
                created.append(str(rel(path)))
        created_str = ', '.join(created) if created else 'no files'
        print(f"Converted {result['source']} -> {created_str}")


if __name__ == '__main__':
    cli()
