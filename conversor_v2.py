import json
import os
import sys
import math
import re
import html
import shutil
import subprocess
import argparse
from dataclasses import dataclass
from typing import Dict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading
import mimetypes
from datetime import datetime
from pathlib import Path

# ==============================
# CHARACTER ANALYZER
# ==============================

class CharacterAnalyzer:
    def __init__(self, json_data):
        self.data = json_data
        self.calculated_values = {}

    def calculate_ability_scores(self):
        base_scores = {
            "str": 10, "dex": 10, "con": 10,
            "int": 10, "wis": 10, "cha": 10
        }
        system_abilities = self.data.get("system", {}).get("abilities")
        if not isinstance(system_abilities, dict):
            system_abilities = {}

        for item in self.data.get("items", []):
            if item.get("type") == "ancestry":
                boosts = item.get("system", {}).get("boosts", {})
                for boost_values in boosts.values():
                    if isinstance(boost_values, dict) and "selected" in boost_values:
                        selected = boost_values["selected"]
                        if selected:
                            base_scores[selected] += 2

        for item in self.data.get("items", []):
            if item.get("type") == "background":
                boosts = item.get("system", {}).get("boosts", {})
                for boost_values in boosts.values():
                    if isinstance(boost_values, dict) and "selected" in boost_values:
                        selected = boost_values["selected"]
                        if selected:
                            base_scores[selected] += 2

        build = self.data.get("system", {}).get("build", {})
        build_boosts = build.get("attributes", {}).get("boosts", {})
        for boosts in build_boosts.values():
            if isinstance(boosts, list):
                for boost in boosts:
                    if boost in base_scores:
                        base_scores[boost] += 2

        modifiers = {}
        for ability, score in base_scores.items():
            ability_data = system_abilities.get(ability, {})
            if isinstance(ability_data, dict):
                if "value" in ability_data and ability_data["value"] is not None:
                    base_scores[ability] = ability_data["value"]
                if "mod" in ability_data and ability_data["mod"] is not None:
                    modifiers[ability] = ability_data["mod"]
        for ability, score in base_scores.items():
            if ability not in modifiers:
                modifiers[ability] = math.floor((score - 10) / 2)

        self.calculated_values["ability_scores"] = base_scores
        self.calculated_values["ability_modifiers"] = modifiers

        return base_scores, modifiers

    def calculate_ac(self):
        base_ac = 10

        dex_mod = self.calculated_values.get("ability_modifiers", {}).get("dex", 0)

        armor_bonus = 0
        armor_dex_cap = 99
        armor_check_penalty = 0

        for item in self.data.get("items", []):
            if item.get("type") == "armor":
                armor_bonus = item.get("system", {}).get("acBonus", 0)
                armor_dex_cap = item.get("system", {}).get("dexCap", 99)
                armor_check_penalty = item.get("system", {}).get("checkPenalty", 0)
                break

        effective_dex_mod = min(dex_mod, armor_dex_cap)

        level = self.data.get("system", {}).get("details", {}).get("level", {}).get("value", 1)
        proficiency_bonus = level + 2

        ac = base_ac + effective_dex_mod + armor_bonus + proficiency_bonus

        shield_bonus = 0
        for item in self.data.get("items", []):
            if item.get("type") == "shield":
                shield_bonus = item.get("system", {}).get("acBonus", 0)
                break

        ac += shield_bonus

        self.calculated_values["ac"] = {
            "total": ac,
            "base": base_ac,
            "armor_bonus": armor_bonus,
            "shield_bonus": shield_bonus,
            "effective_dex_mod": effective_dex_mod,
            "proficiency_bonus": proficiency_bonus,
            "armor_check_penalty": armor_check_penalty,
        }

        return ac

    def calculate_saves(self):
        level = self.data.get("system", {}).get("details", {}).get("level", {}).get("value", 1)
        saves = {}

        saves["fortitude"] = {"base": 0, "ability": "con", "proficiency": 1}
        saves["reflex"] = {"base": 0, "ability": "dex", "proficiency": 2}
        saves["will"] = {"base": 0, "ability": "wis", "proficiency": 2}

        for item in self.data.get("items", []):
            if item.get("name") == "Fortitude Expertise":
                saves["fortitude"]["proficiency"] = 2

        system_saves = self.data.get("system", {}).get("saves")
        if isinstance(system_saves, dict):
            for key in ["fortitude", "reflex", "will"]:
                if key in system_saves and isinstance(system_saves[key], dict):
                    rank = system_saves[key].get("rank")
                    if rank is not None:
                        saves[key]["proficiency"] = rank

        ability_mods = self.calculated_values.get("ability_modifiers", {})
        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}

        for save, info in saves.items():
            ability_mod = ability_mods.get(info["ability"], 0)
            prof_bonus = proficiency_ranks.get(info["proficiency"], level)
            saves[save]["total"] = info["base"] + ability_mod + prof_bonus
            saves[save]["ability_mod"] = ability_mod
            saves[save]["prof_bonus"] = prof_bonus

        self.calculated_values["saves"] = saves
        return saves

    def calculate_attacks(self):
        level = self.data.get("system", {}).get("details", {}).get("level", {}).get("value", 1)
        attacks = {}

        melee_proficiency = 2 if level >= 5 else 1
        for item in self.data.get("items", []):
            if item.get("type") == "class":
                class_attacks = item.get("system", {}).get("attacks", {})
                if isinstance(class_attacks, dict):
                    ranks = [
                        class_attacks.get("simple", 0),
                        class_attacks.get("martial", 0),
                        class_attacks.get("advanced", 0),
                        class_attacks.get("unarmed", 0),
                    ]
                    max_rank = max([r for r in ranks if isinstance(r, int)], default=0)
                    if max_rank:
                        melee_proficiency = max_rank
                break
        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}

        str_mod = self.calculated_values.get("ability_modifiers", {}).get("str", 0)
        dex_mod = self.calculated_values.get("ability_modifiers", {}).get("dex", 0)

        attacks["melee"] = {
            "proficiency": melee_proficiency,
            "prof_bonus": proficiency_ranks.get(melee_proficiency, level),
            "str_mod": str_mod,
            "dex_mod": dex_mod,
        }

        attacks["melee"]["total"] = attacks["melee"]["prof_bonus"] + max(str_mod, dex_mod)

        self.calculated_values["attacks"] = attacks
        return attacks

    def calculate_skills(self):
        level = self.data.get("system", {}).get("details", {}).get("level", {}).get("value", 1)
        skills_data = self.data.get("system", {}).get("skills", {})
        ability_mods = self.calculated_values.get("ability_modifiers", {})

        skills = {}
        skill_abilities = {
            "acrobatics": "dex",
            "arcana": "int",
            "athletics": "str",
            "crafting": "int",
            "deception": "cha",
            "diplomacy": "cha",
            "intimidation": "cha",
            "medicine": "wis",
            "nature": "wis",
            "occultism": "int",
            "performance": "cha",
            "religion": "wis",
            "society": "int",
            "stealth": "dex",
            "survival": "wis",
            "thievery": "dex",
        }

        for skill, data in (skills_data or {}).items():
            if isinstance(data, dict) and "rank" in data:
                rank = data["rank"]
                ability = data.get("ability") or skill_abilities.get(skill, "dex")
                if "lore" in skill or data.get("label"):
                    ability = data.get("ability") or "int"
                ability_mod = ability_mods.get(ability, 0)

                proficiency_ranks = {0: 0, 1: level, 2: level + 4, 3: level + 8, 4: level + 12}
                prof_bonus = proficiency_ranks.get(rank, 0)

                skills[skill] = {
                    "rank": rank,
                    "ability": ability,
                    "ability_mod": ability_mod,
                    "prof_bonus": prof_bonus,
                    "total": prof_bonus + ability_mod,
                    "label": data.get("label", ""),
                }

        self.calculated_values["skills"] = skills
        return skills

    def calculate_perception(self):
        level = self.data.get("system", {}).get("details", {}).get("level", {}).get("value", 1)
        wis_mod = self.calculated_values.get("ability_modifiers", {}).get("wis", 0)

        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}
        rank = 2
        system_perception = self.data.get("system", {}).get("perception")
        if isinstance(system_perception, dict) and system_perception.get("rank") is not None:
            rank = system_perception.get("rank")
        prof_bonus = proficiency_ranks.get(rank, level)

        perception = {
            "wis_mod": wis_mod,
            "prof_bonus": prof_bonus,
            "total": wis_mod + prof_bonus,
        }

        self.calculated_values["perception"] = perception
        return perception

    def get_character_info(self):
        system = self.data.get("system", {})
        details = system.get("details", {})
        resources = system.get("resources", {})

        key_ability = details.get("keyability", {}).get("value", "")
        if not key_ability:
            key_ability = details.get("keyAbility", {}).get("value", "")
        if isinstance(key_ability, list):
            key_ability = key_ability[0] if key_ability else ""

        class_key_ability = ""
        for item in self.data.get("items", []):
            if item.get("type") == "class":
                class_key_ability = item.get("system", {}).get("keyAbility", "")
                if isinstance(class_key_ability, dict):
                    class_key_ability = class_key_ability.get("value", "")
                if isinstance(class_key_ability, list):
                    class_key_ability = class_key_ability[0] if class_key_ability else ""
                break

        info = {
            "name": self.data.get("name", "Unknown"),
            "level": details.get("level", {}).get("value", 1),
            "xp": details.get("xp", {}).get("value", 0),
            "hp": system.get("attributes", {}).get("hp", {}).get("value", 0),
            "temp_hp": system.get("attributes", {}).get("hp", {}).get("temp", 0),
            "hero_points": resources.get("heroPoints", {}).get("value", 0),
            "max_hero_points": resources.get("heroPoints", {}).get("max", 0),
            "key_ability": key_ability,
            "class_key_ability": class_key_ability,
        }

        for field in ["age", "height", "weight", "gender", "ethnicity", "nationality"]:
            if field in details:
                info[field] = details[field].get("value", "")

        return info

    def get_items_by_type(self, item_type):
        return [item for item in self.data.get("items", []) if item.get("type") == item_type]

    def get_feats_by_category(self):
        feats = {
            "ancestry": [],
            "class": [],
            "skill": [],
            "general": [],
        }

        for item in self.data.get("items", []):
            if item.get("type") == "feat":
                category = item.get("system", {}).get("category", "general")
                if category in feats:
                    feat_info = {
                        "name": item.get("name", ""),
                        "level": item.get("system", {}).get("level", {}).get("value", 0),
                    }
                    feats[category].append(feat_info)

        return feats

    def calculate_all(self):
        self.calculate_ability_scores()
        self.calculate_ac()
        self.calculate_saves()
        self.calculate_attacks()
        self.calculate_skills()
        self.calculate_perception()
        return self.calculated_values


# ==============================
# HTML GENERATOR
# ==============================

def clean_text(text):
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r"\[\[.*?\]\]", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    return text.strip()


def h(text):
    return html.escape(clean_text(text))


def render_table(headers, rows):
    if not rows:
        return ""
    header_html = "".join(f"<th>{h(header)}</th>" for header in headers)
    row_html = ""
    for row in rows:
        row_html += "<tr>" + "".join(f"<td>{h(cell)}</td>" for cell in row) + "</tr>"
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{row_html}</tbody></table>"


def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if "value" in value:
            return normalize_list(value["value"])
        return list(value.values())
    return [value]


def format_list(value, empty_label="-"):
    values = [clean_text(v) for v in normalize_list(value) if clean_text(v)]
    return ", ".join(values) if values else empty_label


def format_typed_entries(entries):
    if not entries:
        return "-"
    items = []
    for entry in entries:
        if isinstance(entry, dict):
            entry_type = clean_text(entry.get("type", ""))
            entry_value = entry.get("value", "")
            if entry_type and entry_value != "":
                items.append(f"{entry_type} {entry_value}")
            elif entry_type:
                items.append(entry_type)
            else:
                items.append(clean_text(entry))
        else:
            items.append(clean_text(entry))
    items = [item for item in items if item]
    return ", ".join(items) if items else "-"


def extract_value(value):
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def format_resource_value(resource):
    if not isinstance(resource, dict):
        return ""
    value = resource.get("value")
    max_value = resource.get("max")
    if value is None:
        return ""
    if max_value is not None:
        return f"{value}/{max_value}"
    return str(value)


@dataclass
class SectionFlags:
    summary: bool = True
    summary_stats: bool = True
    summary_attributes: bool = True
    summary_defenses: bool = True
    summary_skills: bool = True
    talents_equipment: bool = True
    talents: bool = True
    equipment: bool = True
    inventory_notes: bool = True
    info: bool = True
    info_details: bool = True
    info_physical: bool = True
    info_origin: bool = True
    info_data: bool = True
    info_resist: bool = True
    info_actions: bool = True
    spells: bool = True
    spells_list: bool = True
    spells_resources: bool = True
    spells_notes: bool = True


def generate_html(analyzer, output_title, sections: SectionFlags):
    calculated = analyzer.calculate_all()
    info = analyzer.get_character_info()
    system = analyzer.data.get("system", {})
    if not isinstance(system, dict):
        system = {}
    attributes = system.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    details = system.get("details", {})
    if not isinstance(details, dict):
        details = {}

    ability_scores = calculated["ability_scores"]
    ability_mods = calculated["ability_modifiers"]
    ac_info = calculated["ac"]
    saves = calculated["saves"]
    perception = calculated["perception"]
    attacks = calculated["attacks"]
    skills = calculated["skills"]
    feats = analyzer.get_feats_by_category()

    ability_names = {
        "str": "Forca", "dex": "Destreza", "con": "Constituicao",
        "int": "Inteligencia", "wis": "Sabedoria", "cha": "Carisma",
    }

    attributes_rows = []
    for key, name in ability_names.items():
        score = ability_scores.get(key, 10)
        mod = ability_mods.get(key, 0)
        attributes_rows.append([name, str(score), f"{mod:+}"])

    saves_rows = []
    save_names = {"fortitude": "Fortitude", "reflex": "Reflexos", "will": "Vontade"}
    for save_key, save_name in save_names.items():
        if save_key in saves:
            save_info = saves[save_key]
            save_details = f"Mod: {save_info['ability_mod']:+} | Prof: +{save_info['prof_bonus']}"
            saves_rows.append([save_name, f"+{save_info['total']}", save_details])

    skill_names_pt = {
        "acrobatics": "Acrobacia",
        "arcana": "Arcanismo",
        "athletics": "Atletismo",
        "crafting": "Oficio",
        "deception": "Dissimulacao",
        "diplomacy": "Diplomacia",
        "intimidation": "Intimidacao",
        "medicine": "Medicina",
        "nature": "Natureza",
        "occultism": "Ocultismo",
        "performance": "Atuacao",
        "religion": "Religiao",
        "society": "Sociedade",
        "stealth": "Furtividade",
        "survival": "Sobrevivencia",
        "thievery": "Ladinagem",
    }
    rank_names = {0: "NT", 1: "T", 2: "E", 3: "M", 4: "L"}
    skills_rows = []
    for skill_key, skill_info in skills.items():
        label = skill_info.get("label") if isinstance(skill_info, dict) else ""
        if label:
            skill_name = label
        elif "lore" in skill_key:
            skill_name = f"Lore: {skill_key.replace('lore', '').strip().title()}".strip()
        else:
            skill_name = skill_names_pt.get(skill_key, skill_key.upper())
        rank = rank_names.get(skill_info["rank"], skill_info["rank"])
        skills_rows.append([
            skill_name,
            rank,
            f"{skill_info['ability_mod']:+}",
            f"+{skill_info['prof_bonus']}",
            f"+{skill_info['total']}",
        ])

    weapons = analyzer.get_items_by_type("weapon")
    armors = analyzer.get_items_by_type("armor")
    shields = analyzer.get_items_by_type("shield")
    equipment = analyzer.get_items_by_type("equipment")
    consumables = analyzer.get_items_by_type("consumable")
    treasures = analyzer.get_items_by_type("treasure")
    backpacks = analyzer.get_items_by_type("backpack")
    actions = analyzer.get_items_by_type("action")
    spell_entries = analyzer.get_items_by_type("spellcastingEntry")
    spells = analyzer.get_items_by_type("spell")

    ancestries = analyzer.get_items_by_type("ancestry")
    heritages = analyzer.get_items_by_type("heritage")
    classes = analyzer.get_items_by_type("class")
    backgrounds = analyzer.get_items_by_type("background")

    all_items = analyzer.data.get("items", [])
    contained_ids = {i.get("system", {}).get("containerId") for i in all_items if i.get("system", {}).get("containerId")}
    equipment_loose = [i for i in equipment if not i.get("system", {}).get("containerId")]
    consumables_loose = [i for i in consumables if not i.get("system", {}).get("containerId")]
    treasures_loose = [i for i in treasures if not i.get("system", {}).get("containerId")]

    speed = extract_value(attributes.get("speed", ""))
    initiative = extract_value(system.get("initiative", ""))
    if isinstance(initiative, dict):
        initiative_total = initiative.get("total")
        if initiative_total is not None:
            initiative = initiative_total
        elif initiative.get("statistic") == "perception":
            initiative = calculated.get("perception", {}).get("total", "")
    senses = extract_value(attributes.get("senses", ""))
    alignment = extract_value(details.get("alignment", ""))
    deity = extract_value(details.get("deity", ""))
    size = extract_value(details.get("size", ""))
    languages = extract_value(details.get("languages", ""))
    traits = system.get("traits", {}).get("traits", {}).get("value", "")

    resistances = attributes.get("resistances", [])
    immunities = attributes.get("immunities", [])
    weaknesses = attributes.get("weaknesses", [])
    resources = system.get("resources", {}) if isinstance(system.get("resources", {}), dict) else {}
    exploration = system.get("exploration", [])
    exploration_text = format_list(
        [e.get("label") if isinstance(e, dict) else e for e in (exploration or [])],
        empty_label="-",
    )

    resource_rows = []
    for key, value in resources.items():
        if key == "heroPoints":
            continue
        label = key.replace("_", " ").title()
        formatted = format_resource_value(value)
        if formatted:
            resource_rows.append([label, formatted])

    def list_items(items, max_items=20, item_formatter=None):
        if not items:
            return ""
        seen = set()
        lis = []
        for item in items[:max_items]:
            item_name = clean_text(item.get("name", ""))
            if not item_name or item_name in seen:
                continue
            seen.add(item_name)
            label = item_name
            if item_formatter:
                label = item_formatter(item, item_name)
            quantity = item.get("system", {}).get("quantity", 1)
            if quantity > 1:
                lis.append(f"{label} (x{quantity})")
            else:
                lis.append(label)
        return "".join(f"<li>{h(name)}</li>" for name in lis)

    def format_weapon(item, item_name):
        damage = item.get("system", {}).get("damage", {})
        dice = damage.get("dice", 0)
        die = damage.get("die", 0)
        damage_type = clean_text(damage.get("damageType", ""))
        damage_text = ""
        if dice and die:
            damage_text = f"{dice}{die}" if str(die).startswith("d") else f"{dice}d{die}"
            if damage_type:
                damage_text = f"{damage_text} {damage_type}"

        range_value = item.get("system", {}).get("range", None)
        range_text = ""
        if isinstance(range_value, dict):
            range_value = range_value.get("value", "")
        if range_value:
            range_text = f"alcance {range_value}"

        traits = item.get("system", {}).get("traits", {}).get("value", [])
        traits_text = ", ".join(clean_text(t) for t in traits if clean_text(t))

        bonus = item.get("system", {}).get("bonus", {}).get("value", 0)
        bonus_text = f"bonus +{bonus}" if bonus else ""

        runes = item.get("system", {}).get("runes", {})
        potency = runes.get("potency", 0)
        striking = runes.get("striking", 0)
        properties = runes.get("property", []) or []
        rune_parts = []
        if potency:
            rune_parts.append(f"+{potency}")
        if striking:
            rune_parts.append("striking" if striking == 1 else f"striking {striking}")
        for prop in properties:
            if prop:
                rune_parts.append(clean_text(prop))
        rune_text = ", ".join(rune_parts)

        parts = [item_name]
        if damage_text:
            parts.append(damage_text)
        if range_text:
            parts.append(range_text)
        if bonus_text:
            parts.append(bonus_text)
        if rune_text:
            parts.append(f"runas: {rune_text}")
        if traits_text:
            parts.append(f"tracos: {traits_text}")
        return " — ".join(parts) if len(parts) > 1 else item_name

    def format_armor(item, item_name):
        ac_bonus = item.get("system", {}).get("acBonus", 0)
        dex_cap = item.get("system", {}).get("dexCap", "")
        check_penalty = item.get("system", {}).get("checkPenalty", "")
        parts = [item_name, f"+{ac_bonus} CA"]
        if dex_cap != "" and dex_cap is not None:
            parts.append(f"DEX cap {dex_cap}")
        if check_penalty not in ("", None, 0):
            parts.append(f"penalidade {check_penalty}")
        return " — ".join(parts)

    def format_shield(item, item_name):
        ac_bonus = item.get("system", {}).get("acBonus", 0)
        return f"{item_name} — +{ac_bonus} CA"

    def format_treasure(item, item_name):
        price = item.get("system", {}).get("price", {}).get("value", {})
        if isinstance(price, dict) and price:
            price_text = " ".join(f"{v}{k}" for k, v in price.items())
            return f"{item_name} — {price_text}".strip()
        return item_name

    def format_action(item, item_name):
        action_type = item.get("system", {}).get("actionType", {}).get("value", "")
        actions_value = item.get("system", {}).get("actions", {}).get("value", "")
        if action_type == "action" and actions_value:
            return f"{item_name} — {actions_value} acao"
        if action_type:
            return f"{item_name} — {action_type}"
        return item_name

    def group_backpacks():
        if not backpacks:
            return ""
        items_by_container = {}
        for item in analyzer.data.get("items", []):
            container_id = item.get("system", {}).get("containerId")
            if container_id:
                items_by_container.setdefault(container_id, []).append(item)
        blocks = []
        for backpack in backpacks:
            pack_id = backpack.get("_id")
            pack_name = clean_text(backpack.get("name", "Mochila"))
            contents = items_by_container.get(pack_id, [])
            contents_list = list_items(contents, max_items=50)
            block = f"<div class='card'><h3>{h(pack_name)}</h3><ul>{contents_list}</ul></div>"
            blocks.append(block)
        return "".join(blocks)

    def format_spell(item):
        name = clean_text(item.get("name", ""))
        level = item.get("system", {}).get("level", {}).get("value", "")
        time = item.get("system", {}).get("time", {}).get("value", "")
        rng = item.get("system", {}).get("range", {}).get("value", "")
        traits = item.get("system", {}).get("traits", {}).get("value", [])
        trait_text = ", ".join(clean_text(t) for t in traits if clean_text(t))
        parts = [name]
        if level != "":
            parts.append(f"nivel {level}")
        if time:
            parts.append(f"acao {time}")
        if rng:
            parts.append(f"alcance {rng}")
        if trait_text:
            parts.append(f"tracos: {trait_text}")
        return " — ".join(parts)

    def render_spells_by_entry():
        if not spell_entries:
            return "<div class='note'>Nenhuma entrada de magia encontrada.</div>"
        spells_by_entry = {}
        for spell in spells:
            location = spell.get("system", {}).get("location", {}).get("value", "")
            if location:
                spells_by_entry.setdefault(location, []).append(spell)
        blocks = []
        for entry in spell_entries:
            entry_id = entry.get("_id")
            entry_name = clean_text(entry.get("name", "Entrada de Magias"))
            tradition = entry.get("system", {}).get("tradition", {}).get("value", "")
            prepared = entry.get("system", {}).get("prepared", {}).get("value", "")
            header = entry_name
            if tradition:
                header += f" ({tradition})"
            if prepared:
                header += f" — {prepared}"
            entry_spells = spells_by_entry.get(entry_id, [])
            lis = "".join(f"<li>{h(format_spell(spell))}</li>" for spell in entry_spells)
            blocks.append(f"<div class='card'><h3>{h(header)}</h3><ul>{lis}</ul></div>")
        return "".join(blocks)

    def list_feats(category):
        if not feats.get(category):
            return ""
        lis = []
        for feat in feats[category]:
            lis.append(f"{feat['name']} (Nivel {feat['level']})")
        return "".join(f"<li>{h(name)}</li>" for name in lis)

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    key_ability_map = {
        "str": "Forca",
        "dex": "Destreza",
        "con": "Constituicao",
        "int": "Inteligencia",
        "wis": "Sabedoria",
        "cha": "Carisma",
    }
    key_ability_label = key_ability_map.get(info["key_ability"], info["key_ability"]).strip()
    class_key_ability_label = key_ability_map.get(
        info.get("class_key_ability", ""), info.get("class_key_ability", "")
    ).strip()
    key_ability_display = key_ability_label
    if class_key_ability_label and class_key_ability_label.lower() != key_ability_label.lower():
        key_ability_display = f"{key_ability_label} (classe: {class_key_ability_label})"
    details_rows = [
        ["Nome", info["name"]],
        ["Nivel", info["level"]],
        ["Pontos de Vida", f"{info['hp']} (+{info['temp_hp']} temp)"],
        ["Pontos de Heroi", f"{info['hero_points']}/{info['max_hero_points']}"],
        ["Experiencia", f"{info['xp']}/1000"],
        ["Atributo-chave", key_ability_display],
    ]

    summary_cards = ""
    if sections.summary_stats:
        summary_cards += f"""
    <div class="grid-3">
      <div class="card">
        <h3>Vida</h3>
        <div class="stat">{info['hp']}</div>
        <div class="note">Temporario: +{info['temp_hp']}</div>
      </div>
      <div class="card">
        <h3>Classe de Armadura</h3>
        <div class="stat">{ac_info['total']}</div>
        <div class="note">Armadura +{ac_info['armor_bonus']} | Escudo +{ac_info['shield_bonus']}</div>
      </div>
      <div class="card">
        <h3>Percepcao</h3>
        <div class="stat">+{perception['total']}</div>
        <div class="note">Sab {perception['wis_mod']:+} | Prof +{perception['prof_bonus']}</div>
      </div>
    </div>
"""
    if sections.summary_attributes:
        summary_cards += f"""
    <div class="grid-2" style="margin-top: 12px;">
      <div class="card">
        <h3>Atributos</h3>
        {render_table(["Atributo", "Valor", "Mod"], attributes_rows)}
      </div>
"""
    if sections.summary_defenses:
        summary_cards += f"""
      <div class="card">
        <h3>Defesas</h3>
        {render_table(["Teste", "Total", "Detalhes"], saves_rows)}
        <div class="note" style="margin-top:8px;">Ataque corpo a corpo: +{attacks['melee']['total']}</div>
      </div>
"""
    if sections.summary_attributes or sections.summary_defenses:
        summary_cards += """
    </div>
"""
    if sections.summary_skills:
        summary_cards += f"""
    <div class="card" style="margin-top: 12px;">
      <h3>Pericias</h3>
      {render_table(["Pericia", "Rank", "Mod", "Prof", "Total"], skills_rows)}
    </div>
"""

    summary_section = ""
    if sections.summary and summary_cards.strip():
        summary_section = f"""
  <section class="page">
    <header>
      <div>
        <div class="title">{h(info['name'])}</div>
        <div class="subtitle">Pathfinder 2E • Nivel {info['level']} • Gerado em {generated_at}</div>
      </div>
      <div>
        <div class="chip">XP {info['xp']}/1000</div>
        <div class="chip">Heroi {info['hero_points']}/{info['max_hero_points']}</div>
      </div>
    </header>
{summary_cards}
  </section>
"""

    talents_cards = ""
    if sections.talents:
        talents_cards = f"""
    <div class="grid-2">
      <div class="card">
        <h3>Talentos de Ancestralidade</h3>
        <ul>{list_feats("ancestry")}</ul>
        <h3 style="margin-top:12px;">Talentos de Classe</h3>
        <ul>{list_feats("class")}</ul>
      </div>
      <div class="card">
        <h3>Talentos de Pericia</h3>
        <ul>{list_feats("skill")}</ul>
        <h3 style="margin-top:12px;">Talentos Gerais</h3>
        <ul>{list_feats("general")}</ul>
      </div>
    </div>
"""

    equipment_cards = ""
    if sections.equipment:
        equipment_cards = f"""
    <div class="grid-2" style="margin-top: 12px;">
      <div class="card">
        <h3>Armas</h3>
        <ul>{list_items(weapons, 12, format_weapon)}</ul>
        <h3 style="margin-top:12px;">Protecao</h3>
        <ul>{list_items(armors, 6, format_armor)}{list_items(shields, 6, format_shield)}</ul>
      </div>
      <div class="card">
        <h3>Itens e Consumiveis</h3>
        <ul>{list_items(equipment_loose, 30)}</ul>
        <h3 style="margin-top:12px;">Consumiveis</h3>
        <ul>{list_items(consumables_loose, 20)}</ul>
        <h3 style="margin-top:12px;">Tesouros</h3>
        <ul>{list_items(treasures_loose, 20, format_treasure)}</ul>
      </div>
    </div>
"""

    inventory_notes_card = ""
    if sections.inventory_notes:
        inventory_notes_card = """
    <div class="card" style="margin-top: 12px;">
      <h3>Anotacoes de Inventario</h3>
      <div class="notes-box"></div>
    </div>
"""

    backpacks_cards = ""
    if sections.equipment and backpacks:
        backpacks_cards = f"""
    <div class="grid-2" style="margin-top: 12px;">
      {group_backpacks()}
    </div>
"""

    talents_equipment_section = ""
    if sections.talents_equipment:
        if talents_cards:
            talents_equipment_section += f"""
  <section class="page">
    <header>
      <div>
        <div class="title">Talentos</div>
        <div class="subtitle">{h(info['name'])} • Nivel {info['level']}</div>
      </div>
      <div class="chip">Atributo-chave: {h(key_ability_display)}</div>
    </header>
{talents_cards}
  </section>
"""
        if equipment_cards or inventory_notes_card or backpacks_cards:
            talents_equipment_section += f"""
  <section class="page">
    <header>
      <div>
        <div class="title">Equipamentos</div>
        <div class="subtitle">{h(info['name'])} • Nivel {info['level']}</div>
      </div>
      <div class="chip">Atributo-chave: {h(key_ability_display)}</div>
    </header>
{equipment_cards}
{backpacks_cards}
{inventory_notes_card}
  </section>
"""

    details_card = ""
    if sections.info_details:
        details_card = f"""
    <div class="card">
      <h3>Detalhes</h3>
      {render_table(["Campo", "Valor"], details_rows)}
    </div>
"""

    physical_origin_card = ""
    if sections.info_physical or sections.info_origin:
        physical_block = ""
        origin_block = ""
        if sections.info_physical:
            physical_block = f"""
      <div class="card">
        <h3>Informacoes Fisicas</h3>
        {render_table(["Campo", "Valor"], [
          ["Idade", info.get("age", "")],
          ["Altura", info.get("height", "")],
          ["Peso", info.get("weight", "")],
          ["Genero", info.get("gender", "")],
          ["Etnia", info.get("ethnicity", "")],
          ["Nacionalidade", info.get("nationality", "")],
        ])}
      </div>
"""
        if sections.info_origin:
            origin_block = f"""
      <div class="card">
        <h3>Origem</h3>
        <div class="note">Ancestralidade</div>
        <ul>{list_items(ancestries, 5)}</ul>
        <div class="note" style="margin-top:8px;">Heranca</div>
        <ul>{list_items(heritages, 5)}</ul>
        <div class="note" style="margin-top:8px;">Classe</div>
        <ul>{list_items(classes, 5)}</ul>
        <div class="note" style="margin-top:8px;">Antecedente</div>
        <ul>{list_items(backgrounds, 5)}</ul>
      </div>
"""
        physical_origin_card = f"""
    <div class="grid-2" style="margin-top: 12px;">
{physical_block}{origin_block}
    </div>
"""

    data_resist_card = ""
    if sections.info_data or sections.info_resist:
        data_block = ""
        resist_block = ""
        if sections.info_data:
            data_block = f"""
      <div class="card">
        <h3>Dados do Personagem</h3>
        {render_table(["Campo", "Valor"], [
          ["Tamanho", size],
          ["Alinhamento", alignment],
          ["Deidade", deity],
          ["Idiomas", format_list(languages)],
          ["Traits", format_list(traits)],
          ["Velocidade", speed],
          ["Iniciativa", initiative],
          ["Sentidos", format_list(senses)],
          ["Exploracao", exploration_text],
        ])}
        {render_table(["Recurso", "Valor"], resource_rows)}
      </div>
"""
        if sections.info_resist:
            resist_block = f"""
      <div class="card">
        <h3>Resistencias e Imunidades</h3>
        {render_table(["Tipo", "Detalhes"], [
          ["Resistencias", format_typed_entries(resistances)],
          ["Imunidades", format_typed_entries(immunities)],
          ["Fraquezas", format_typed_entries(weaknesses)],
        ])}
      </div>
"""
        data_resist_card = f"""
    <div class="grid-2" style="margin-top: 12px;">
{data_block}{resist_block}
    </div>
"""

    actions_card = ""
    if sections.info_actions and actions:
        actions_card = f"""
    <div class="card" style="margin-top: 12px;">
      <h3>Acoes e Atividades</h3>
      <ul>{list_items(actions, 30, format_action)}</ul>
    </div>
"""

    info_section = ""
    if sections.info and (details_card or physical_origin_card or data_resist_card or actions_card):
        info_section = f"""
  <section class="page">
    <header>
      <div>
        <div class="title">Informacoes do Personagem</div>
        <div class="subtitle">{h(info['name'])}</div>
      </div>
      <div class="chip">Nivel {info['level']}</div>
    </header>
{details_card}
{physical_origin_card}
{data_resist_card}
{actions_card}
  </section>
"""

    spells_cards = ""
    if sections.spells_list:
        spells_cards += f"""
    <div class="grid-2">
      {render_spells_by_entry()}
    </div>
"""
    if sections.spells_resources:
        spells_cards += """
    <div class="card" style="margin-top: 12px;">
      <h3>Foco e Recursos</h3>
      <div class="note">Espaco reservado para foco e recursos magicos.</div>
    </div>
"""
    if sections.spells_notes:
        spells_cards += """
    <div class="card" style="margin-top: 12px;">
      <h3>Anotacoes de Magias</h3>
      <div class="notes-box"></div>
    </div>
"""

    spells_section = ""
    if sections.spells and spells_cards.strip():
        spells_section = f"""
  <section class="page">
    <header>
      <div>
        <div class="title">Magias</div>
        <div class="subtitle">{h(info['name'])} • Nivel {info['level']}</div>
      </div>
      <div class="chip">Atributo-chave: {h(key_ability_display)}</div>
    </header>
{spells_cards}
  </section>
"""

    html_out = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>{h(output_title)}</title>
  <style>
    :root {{
      --pf2e-green: #1f3f33;
      --pf2e-gold: #b48b2f;
      --pf2e-cream: #f6f1e7;
      --pf2e-ink: #1b1b1b;
      --pf2e-muted: #6b6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Palatino Linotype", "Book Antiqua", Palatino, serif;
      color: var(--pf2e-ink);
      background: var(--pf2e-cream);
    }}
    .page {{
      width: 210mm;
      min-height: 297mm;
      padding: 16mm 14mm;
      margin: 0 auto 8mm auto;
      background: #fff;
      box-shadow: 0 4px 18px rgba(0,0,0,0.12);
      page-break-after: always;
    }}
    .page:last-child {{ page-break-after: auto; }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      border-bottom: 2px solid var(--pf2e-gold);
      padding-bottom: 8px;
      margin-bottom: 12px;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
      color: var(--pf2e-green);
      letter-spacing: 0.5px;
    }}
    .subtitle {{
      font-size: 12px;
      color: var(--pf2e-muted);
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 10px;
      min-height: 22px;
      border: 1px solid var(--pf2e-gold);
      border-radius: 999px;
      font-size: 12px;
      background: #fff8e8;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
    }}
    .card {{
      border: 1px solid #e2d7c3;
      background: #fffdf8;
      padding: 10px 12px;
      border-radius: 8px;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .card h3 {{
      margin: 0 0 6px 0;
      font-size: 12px;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      color: var(--pf2e-green);
    }}
    .stat {{
      font-size: 20px;
      font-weight: 700;
      color: var(--pf2e-green);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
    }}
    th, td {{
      padding: 5px 7px;
      border-bottom: 1px solid #e6dccb;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      text-transform: uppercase;
      font-size: 11px;
      color: var(--pf2e-green);
      letter-spacing: 0.6px;
      background: #f5efe2;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
      font-size: 12px;
    }}
    .note {{
      font-size: 11px;
      color: var(--pf2e-muted);
    }}
    .notes-box {{
      min-height: 90mm;
      border: 1px dashed #d8c9b1;
      border-radius: 8px;
      background: repeating-linear-gradient(
        to bottom,
        #fffdf8 0px,
        #fffdf8 18px,
        #f0e7d6 19px
      );
      padding: 10px 12px;
      font-size: 12px;
      color: var(--pf2e-muted);
    }}
    @page {{
      size: A4;
      margin: 12mm;
    }}
    @media print {{
      body {{
        background: #fff;
      }}
      .page {{
        width: auto;
        min-height: auto;
        margin: 0;
        box-shadow: none;
      }}
    }}
  </style>
</head>
<body>
{summary_section}
{talents_equipment_section}
{info_section}
{spells_section}
</body>
</html>
"""
    return html_out


def find_chrome_executable():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        path = shutil.which(candidate)
        if path:
            return path
    return None


def export_pdf(html_path, pdf_path):
    chrome = find_chrome_executable()
    if not chrome:
        print("Aviso: Chrome/Chromium nao encontrado. HTML gerado, PDF nao exportado.")
        return False

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        str(html_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Erro ao exportar PDF via Chrome:")
        print(result.stderr.strip() or result.stdout.strip())
        return False
    return True


def load_config(config_path: Path) -> Dict:
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config_path: Path, config: Dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def section_flags_from_config(config: Dict) -> SectionFlags:
    sections = config.get("sections", {})
    return SectionFlags(
        summary=sections.get("summary", True),
        summary_stats=sections.get("summary_stats", True),
        summary_attributes=sections.get("summary_attributes", True),
        summary_defenses=sections.get("summary_defenses", True),
        summary_skills=sections.get("summary_skills", True),
        talents_equipment=sections.get("talents_equipment", True),
        talents=sections.get("talents", True),
        equipment=sections.get("equipment", True),
        inventory_notes=sections.get("inventory_notes", True),
        info=sections.get("info", True),
        info_details=sections.get("info_details", True),
        info_physical=sections.get("info_physical", True),
        info_origin=sections.get("info_origin", True),
        info_data=sections.get("info_data", True),
        info_resist=sections.get("info_resist", True),
        info_actions=sections.get("info_actions", True),
        spells=sections.get("spells", True),
        spells_list=sections.get("spells_list", True),
        spells_resources=sections.get("spells_resources", True),
        spells_notes=sections.get("spells_notes", True),
    )


def sections_to_config(sections: SectionFlags) -> Dict:
    return {
        "sections": {
            "summary": sections.summary,
            "summary_stats": sections.summary_stats,
            "summary_attributes": sections.summary_attributes,
            "summary_defenses": sections.summary_defenses,
            "summary_skills": sections.summary_skills,
            "talents_equipment": sections.talents_equipment,
            "talents": sections.talents,
            "equipment": sections.equipment,
            "inventory_notes": sections.inventory_notes,
            "info": sections.info,
            "info_details": sections.info_details,
            "info_physical": sections.info_physical,
            "info_origin": sections.info_origin,
            "info_data": sections.info_data,
            "info_resist": sections.info_resist,
            "info_actions": sections.info_actions,
            "spells": sections.spells,
            "spells_list": sections.spells_list,
            "spells_resources": sections.spells_resources,
            "spells_notes": sections.spells_notes,
        }
    }


def normalize_sections(sections: SectionFlags) -> SectionFlags:
    if not sections.summary:
        sections.summary_stats = False
        sections.summary_attributes = False
        sections.summary_defenses = False
        sections.summary_skills = False
    if not sections.talents_equipment:
        sections.talents = False
        sections.equipment = False
        sections.inventory_notes = False
    if not sections.info:
        sections.info_details = False
        sections.info_physical = False
        sections.info_origin = False
        sections.info_data = False
        sections.info_resist = False
        sections.info_actions = False
    if not sections.spells:
        sections.spells_list = False
        sections.spells_resources = False
        sections.spells_notes = False
    return sections


def run_generate(json_file: Path, sections: SectionFlags) -> bool:
    if not json_file.exists():
        print(f"Erro: Arquivo '{json_file}' nao encontrado.")
        return False

    data = json.loads(json_file.read_text(encoding="utf-8"))
    if "name" not in data:
        print("Erro: JSON nao parece ser uma ficha valida.")
        return False

    sections = normalize_sections(sections)
    analyzer = CharacterAnalyzer(data)
    character_info = analyzer.get_character_info()
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = json_file.stem
    html_path = output_dir / f"{base_name}_ficha.html"
    pdf_path = output_dir / f"{base_name}_ficha.pdf"

    html_out = generate_html(analyzer, f"Ficha {character_info['name']}", sections)
    html_path.write_text(html_out, encoding="utf-8")

    print(f"HTML gerado: {html_path}")
    if export_pdf(html_path, pdf_path):
        print(f"PDF gerado: {pdf_path}")
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(pdf_path)])
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(pdf_path)])
            elif sys.platform.startswith("win"):
                os.startfile(str(pdf_path))
        except Exception:
            print("Nota: PDF gerado, mas nao foi possivel abrir automaticamente.")
        return True
    else:
        print("Falha ao gerar PDF. Abra o HTML no navegador e imprima manualmente.")
        return False


def run_preview(json_file: Path, sections: SectionFlags) -> Path:
    if not json_file.exists():
        raise FileNotFoundError(f"Arquivo '{json_file}' nao encontrado.")
    data = json.loads(json_file.read_text(encoding="utf-8"))
    if "name" not in data:
        raise ValueError("JSON nao parece ser uma ficha valida.")
    sections = normalize_sections(sections)
    analyzer = CharacterAnalyzer(data)
    character_info = analyzer.get_character_info()
    temp_dir = Path("temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = json_file.stem.replace(" ", "_")
    html_path = temp_dir / f"preview_{safe_name}_{timestamp}_temp.html"
    html_out = generate_html(analyzer, f"Ficha {character_info['name']}", sections)
    floating_button = """
<a href="#" class="floating-generate" id="floatingGenerate">Gerar ficha</a>
<script>
  document.getElementById('floatingGenerate').addEventListener('click', (e) => {
    e.preventDefault();
    fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({json_path: '__JSON_PATH__', sections: __SECTIONS__})
    }).then(() => alert('Ficha gerada.')).catch(() => alert('Falha ao gerar ficha.'));
  });
</script>
"""
    floating_button = floating_button.replace("__JSON_PATH__", str(json_file).replace("\\", "\\\\"))
    floating_button = floating_button.replace("__SECTIONS__", json.dumps(sections_to_config(sections)["sections"]))
    html_out = html_out.replace("</body>", f"{floating_button}</body>")
    html_out = html_out.replace(
        "</style>",
        """
    .floating-generate {
      position: fixed;
      top: 16px;
      right: 16px;
      background: #1f3f33;
      color: #fff;
      padding: 10px 14px;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 700;
      z-index: 9999;
      box-shadow: 0 8px 18px rgba(0,0,0,0.2);
    }
        </style>""",
    )
    html_path.write_text(html_out, encoding="utf-8")
    return html_path


def main():
    parser = argparse.ArgumentParser(description="Conversor PF2E JSON -> PDF (HTML).")
    parser.add_argument("json", nargs="?", help="Arquivo JSON do personagem")
    parser.add_argument("--json", dest="json_flag", help="Arquivo JSON do personagem (usando --gui)")
    parser.add_argument("--web-ui", action="store_true", help="Abrir interface web local")
    args = parser.parse_args()

    output_dir = Path("output")
    config_path = output_dir / "config.json"
    config = load_config(config_path)

    if args.web_ui:
        output_dir = Path("output")
        config_path = output_dir / "config.json"

        class UIHandler(BaseHTTPRequestHandler):
            def _send_json(self, data, status=200):
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _serve_file(self, file_path):
                if not file_path.exists():
                    self.send_error(404)
                    return
                ctype, _ = mimetypes.guess_type(str(file_path))
                ctype = ctype or "application/octet-stream"
                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    return self._serve_file(Path("ui/index.html"))
                if parsed.path == "/app.js":
                    return self._serve_file(Path("ui/app.js"))
                if parsed.path == "/style.css":
                    return self._serve_file(Path("ui/style.css"))
                if parsed.path == "/preview":
                    cfg = load_config(config_path)
                    preview_path = Path(cfg.get("last_preview", ""))
                    if not preview_path.exists():
                        return self._serve_file(Path("ui/preview_placeholder.html"))
                    return self._serve_file(preview_path)
                if parsed.path == "/api/jsons":
                    jsons = [str(p) for p in Path(".").glob("*.json")]
                    uploads = list(Path("output/uploads").glob("*.json"))
                    jsons.extend([str(p) for p in uploads])
                    return self._send_json({"jsons": jsons})
                if parsed.path == "/api/config":
                    return self._send_json(load_config(config_path))
                self.send_error(404)

            def do_POST(self):
                parsed = urlparse(self.path)
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                if parsed.path == "/api/config":
                    data = json.loads(body.decode("utf-8"))
                    save_config(config_path, data)
                    return self._send_json({"ok": True})
                if parsed.path == "/api/generate":
                    data = json.loads(body.decode("utf-8"))
                    sections = SectionFlags(**data.get("sections", {}))
                    sections = normalize_sections(sections)
                    json_path = data.get("json_path", "")
                    if not json_path:
                        return self._send_json({"error": "json_path required"}, status=400)
                    ok = run_generate(Path(json_path), sections)
                    config_update = sections_to_config(sections)
                    config_update["last_json"] = json_path
                    save_config(config_path, config_update)
                    return self._send_json({"ok": ok})
                if parsed.path == "/api/preview":
                    data = json.loads(body.decode("utf-8"))
                    sections = SectionFlags(**data.get("sections", {}))
                    sections = normalize_sections(sections)
                    json_path = data.get("json_path", "")
                    if not json_path:
                        return self._send_json({"error": "json_path required"}, status=400)
                    try:
                        preview_path = run_preview(Path(json_path), sections)
                    except Exception as exc:
                        return self._send_json({"error": str(exc)}, status=400)
                    config_update = sections_to_config(sections)
                    config_update["last_json"] = json_path
                    config_update["last_preview"] = str(preview_path)
                    save_config(config_path, config_update)
                    return self._send_json({"ok": True})
                if parsed.path == "/api/upload":
                    boundary = self.headers.get("Content-Type", "").split("boundary=")[-1]
                    if not boundary:
                        return self._send_json({"error": "invalid upload"}, status=400)
                    boundary_bytes = ("--" + boundary).encode("utf-8")
                    parts = body.split(boundary_bytes)
                    upload_path = None
                    for part in parts:
                        if b"Content-Disposition" in part and b"filename=" in part:
                            header, file_data = part.split(b"\r\n\r\n", 1)
                            file_data = file_data.rsplit(b"\r\n", 1)[0]
                            filename = "upload.json"
                            header_str = header.decode("utf-8", errors="ignore")
                            if "filename=" in header_str:
                                filename = header_str.split("filename=")[-1].strip().strip('"')
                            safe_name = os.path.basename(filename)
                            uploads_dir = Path("output/uploads")
                            uploads_dir.mkdir(parents=True, exist_ok=True)
                            upload_path = uploads_dir / safe_name
                            upload_path.write_bytes(file_data)
                    if upload_path:
                        return self._send_json({"path": str(upload_path)})
                    return self._send_json({"error": "upload failed"}, status=400)
                self.send_error(404)

        server = HTTPServer(("127.0.0.1", 0), UIHandler)
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/"
        print(f"UI web em: {url}")
        if sys.platform == "darwin":
            subprocess.run(["open", url])
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", url])
        elif sys.platform.startswith("win"):
            os.startfile(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return

    if not args.json:
        print("Uso: python conversor_v2.py <arquivo_json>")
        print("Exemplo: python conversor_v2.py Umbriel.json")
        sys.exit(1)

    sections = section_flags_from_config(config)
    run_generate(Path(args.json), sections)


if __name__ == "__main__":
    main()
