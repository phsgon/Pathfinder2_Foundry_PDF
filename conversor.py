import json
import sys
import os
from datetime import datetime
from fpdf import FPDF
import math
import re

# ==============================
# CLASSE ANALISADORA DE PERSONAGEM
# ==============================

class CharacterAnalyzer:
    def __init__(self, json_data):
        self.data = json_data
        self.calculated_values = {}
        
    def calculate_ability_scores(self):
        """Calcula os valores de habilidade baseado nos boosts"""
        base_scores = {
            'str': 10, 'dex': 10, 'con': 10,
            'int': 10, 'wis': 10, 'cha': 10
        }
        
        # Aplicar boosts da ancestralidade
        for item in self.data['items']:
            if item['type'] == 'ancestry':
                if 'boosts' in item['system']:
                    boosts = item['system']['boosts']
                    for boost_key, boost_values in boosts.items():
                        if isinstance(boost_values, dict) and 'selected' in boost_values:
                            selected = boost_values['selected']
                            if selected:
                                base_scores[selected] += 2
        
        # Aplicar boosts do background
        for item in self.data['items']:
            if item['type'] == 'background':
                if 'boosts' in item['system']:
                    boosts = item['system']['boosts']
                    for boost_key, boost_values in boosts.items():
                        if isinstance(boost_values, dict) and 'selected' in boost_values:
                            selected = boost_values['selected']
                            if selected:
                                base_scores[selected] += 2
        
        # Aplicar boosts do build (níveis)
        if 'build' in self.data['system'] and 'attributes' in self.data['system']['build']:
            if 'boosts' in self.data['system']['build']['attributes']:
                build_boosts = self.data['system']['build']['attributes']['boosts']
                for level, boosts in build_boosts.items():
                    if isinstance(boosts, list):
                        for boost in boosts:
                            if boost in base_scores:
                                base_scores[boost] += 2
        
        # Calcular modificadores
        modifiers = {}
        for ability, score in base_scores.items():
            modifiers[ability] = math.floor((score - 10) / 2)
        
        self.calculated_values['ability_scores'] = base_scores
        self.calculated_values['ability_modifiers'] = modifiers
        
        return base_scores, modifiers
    
    def calculate_ac(self):
        """Calcula a Classe de Armadura"""
        base_ac = 10
        
        # Modificador de Destreza
        dex_mod = self.calculated_values.get('ability_modifiers', {}).get('dex', 0)
        
        # Bônus da armadura
        armor_bonus = 0
        armor_dex_cap = 99
        armor_check_penalty = 0
        
        for item in self.data['items']:
            if item['type'] == 'armor':
                armor_bonus = item['system']['acBonus']
                armor_dex_cap = item['system']['dexCap']
                armor_check_penalty = item['system']['checkPenalty']
                break
        
        # Limitar modificador de Destreza pelo cap da armadura
        effective_dex_mod = min(dex_mod, armor_dex_cap)
        
        # Bônus de proficiência
        level = self.data['system']['details']['level']['value']
        proficiency_bonus = level + 2
        
        # Cálculo final
        ac = base_ac + effective_dex_mod + armor_bonus + proficiency_bonus
        
        # Bônus de escudo
        shield_bonus = 0
        for item in self.data['items']:
            if item['type'] == 'shield':
                shield_bonus = item['system']['acBonus']
                break
        
        ac += shield_bonus
        
        self.calculated_values['ac'] = {
            'total': ac,
            'base': base_ac,
            'armor_bonus': armor_bonus,
            'shield_bonus': shield_bonus,
            'effective_dex_mod': effective_dex_mod,
            'proficiency_bonus': proficiency_bonus,
            'armor_check_penalty': armor_check_penalty
        }
        
        return ac
    
    def calculate_saves(self):
        """Calcula os testes de resistência"""
        level = self.data['system']['details']['level']['value']
        saves = {}
        
        saves['fortitude'] = {'base': 0, 'ability': 'con', 'proficiency': 1}
        saves['reflex'] = {'base': 0, 'ability': 'dex', 'proficiency': 2}
        saves['will'] = {'base': 0, 'ability': 'wis', 'proficiency': 2}
        
        # Verificar se há Fortitude Expertise
        for item in self.data['items']:
            if item.get('name') == 'Fortitude Expertise':
                saves['fortitude']['proficiency'] = 2
        
        ability_mods = self.calculated_values.get('ability_modifiers', {})
        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}
        
        for save, info in saves.items():
            ability_mod = ability_mods.get(info['ability'], 0)
            prof_bonus = proficiency_ranks.get(info['proficiency'], level)
            saves[save]['total'] = info['base'] + ability_mod + prof_bonus
            saves[save]['ability_mod'] = ability_mod
            saves[save]['prof_bonus'] = prof_bonus
        
        self.calculated_values['saves'] = saves
        return saves
    
    def calculate_attacks(self):
        """Calcula bônus de ataque"""
        level = self.data['system']['details']['level']['value']
        attacks = {}
        
        melee_proficiency = 2 if level >= 5 else 1
        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}
        
        str_mod = self.calculated_values.get('ability_modifiers', {}).get('str', 0)
        dex_mod = self.calculated_values.get('ability_modifiers', {}).get('dex', 0)
        
        attacks['melee'] = {
            'proficiency': melee_proficiency,
            'prof_bonus': proficiency_ranks.get(melee_proficiency, level),
            'str_mod': str_mod,
            'dex_mod': dex_mod
        }
        
        attacks['melee']['total'] = attacks['melee']['prof_bonus'] + max(str_mod, dex_mod)
        
        self.calculated_values['attacks'] = attacks
        return attacks
    
    def calculate_skills(self):
        """Calcula bônus de perícias"""
        level = self.data['system']['details']['level']['value']
        skills_data = self.data['system']['skills']
        ability_mods = self.calculated_values.get('ability_modifiers', {})
        
        skills = {}
        skill_abilities = {
            'acrobatics': 'dex', 'athletics': 'str', 'diplomacy': 'cha',
            'occultism': 'int', 'performance': 'cha', 'society': 'int',
            'deception': 'cha'
        }
        
        for skill, data in skills_data.items():
            if isinstance(data, dict) and 'rank' in data:
                rank = data['rank']
                ability = skill_abilities.get(skill, 'dex')
                ability_mod = ability_mods.get(ability, 0)
                
                proficiency_ranks = {0: 0, 1: level, 2: level + 4, 3: level + 8, 4: level + 12}
                prof_bonus = proficiency_ranks.get(rank, 0)
                
                skills[skill] = {
                    'rank': rank,
                    'ability': ability,
                    'ability_mod': ability_mod,
                    'prof_bonus': prof_bonus,
                    'total': prof_bonus + ability_mod
                }
        
        self.calculated_values['skills'] = skills
        return skills
    
    def calculate_perception(self):
        """Calcula bônus de Percepção"""
        level = self.data['system']['details']['level']['value']
        wis_mod = self.calculated_values.get('ability_modifiers', {}).get('wis', 0)
        
        proficiency_ranks = {1: level, 2: level + 4, 3: level + 8, 4: level + 12}
        prof_bonus = proficiency_ranks.get(2, level)
        
        perception = {
            'wis_mod': wis_mod,
            'prof_bonus': prof_bonus,
            'total': wis_mod + prof_bonus
        }
        
        self.calculated_values['perception'] = perception
        return perception
    
    def get_character_info(self):
        """Extrai informações básicas do personagem"""
        info = {
            'name': self.data.get('name', 'Desconhecido'),
            'level': self.data['system']['details']['level']['value'],
            'xp': self.data['system']['details']['xp']['value'],
            'hp': self.data['system']['attributes']['hp']['value'],
            'temp_hp': self.data['system']['attributes']['hp']['temp'],
            'hero_points': self.data['system']['resources']['heroPoints']['value'],
            'max_hero_points': self.data['system']['resources']['heroPoints']['max'],
            'key_ability': self.data['system']['details']['keyability']['value']
        }
        
        details = self.data['system']['details']
        for field in ['age', 'height', 'weight', 'gender', 'ethnicity', 'nationality']:
            if field in details:
                info[field] = details[field].get('value', '')
        
        return info
    
    def get_items_by_type(self, item_type):
        """Filtra itens por tipo"""
        return [item for item in self.data['items'] if item['type'] == item_type]
    
    def get_feats_by_category(self):
        """Organiza talentos por categoria"""
        feats = {
            'ancestry': [],
            'class': [],
            'skill': [],
            'general': []
        }
        
        for item in self.data['items']:
            if item['type'] == 'feat':
                category = item['system'].get('category', 'general')
                if category in feats:
                    feat_info = {
                        'name': item['name'],
                        'level': item['system']['level']['value']
                    }
                    feats[category].append(feat_info)
        
        return feats
    
    def calculate_all(self):
        """Calcula todos os valores"""
        self.calculate_ability_scores()
        self.calculate_ac()
        self.calculate_saves()
        self.calculate_attacks()
        self.calculate_skills()
        self.calculate_perception()
        
        return self.calculated_values

# ==============================
# CLASSE PDF COM SUPORTE ASCII APENAS
# ==============================

class PF2ECharacterPDF(FPDF):
    def __init__(self):
        super().__init__()
    
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'FICHA DE PERSONAGEM PATHFINDER 2E', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 5, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')
    
    def add_section_title(self, title):
        """Adiciona título de seção formatado"""
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, self.clean_text(title), 0, 1, 'L', 1)
        self.ln(2)
    
    def clean_text(self, text):
        """Converte texto para ASCII seguro"""
        if text is None:
            return ""
        
        text = str(text)
        
        # Mapeamento de caracteres especiais para ASCII
        char_map = {
            'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n',
            'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A',
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
            'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
            'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Ç': 'C', 'Ñ': 'N',
            'º': 'o', 'ª': 'a',
            '•': '-', '·': '-', '–': '-', '—': '-',
            '“': '"', '”': '"', '‘': "'", '’': "'",
            '…': '...'
        }
        
        # Remover colchetes e conteúdo entre colchetes
        text = re.sub(r'\[\[.*?\]\]', '', text)
        text = re.sub(r'\[.*?\]', '', text)
        
        # Converter caracteres
        result = []
        for char in text:
            if char in char_map:
                result.append(char_map[char])
            elif 32 <= ord(char) < 127:  # Caracteres ASCII imprimíveis
                result.append(char)
            else:
                result.append(' ')  # Substituir outros por espaço
        
        return ''.join(result).strip()
    
    def add_table(self, headers, data, col_widths=None):
        """Adiciona uma tabela formatada"""
        if not data:
            return
        
        if col_widths is None:
            col_widths = [self.w / len(headers) - 10] * len(headers)
        
        # Cabeçalho
        self.set_font('Arial', 'B', 11)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, self.clean_text(header), 1, 0, 'C')
        self.ln()
        
        # Dados
        self.set_font('Arial', '', 10)
        for row in data:
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 8, self.clean_text(str(cell)), 1, 0, 'C')
            self.ln()
        
        self.ln(3)
    
    def add_item_list(self, title, items, max_items=20):
        """Adiciona lista de itens formatada"""
        if not items:
            return
        
        self.set_font('Arial', 'B', 11)
        self.cell(0, 8, self.clean_text(title), 0, 1)
        self.ln(2)
        
        self.set_font('Arial', '', 10)
        seen_items = set()
        valid_items = []
        
        for item in items[:max_items]:
            item_name = self.clean_text(item['name'])
            if not item_name or item_name in seen_items:
                continue
            seen_items.add(item_name)
            
            quantity = item.get('system', {}).get('quantity', 1)
            if quantity > 1:
                valid_items.append(f"{item_name} (x{quantity})")
            else:
                valid_items.append(item_name)
        
        # Mostrar em lista simples
        for item_text in valid_items:
            self.cell(0, 6, f"- {item_text}", 0, 1)

# ==============================
# FUNÇÃO PRINCIPAL DE CRIAÇÃO PDF
# ==============================

def create_character_pdf(analyzer, output_filename):
    """Cria PDF usando apenas ASCII"""
    pdf = PF2ECharacterPDF()
    
    calculated = analyzer.calculate_all()
    character_info = analyzer.get_character_info()
    
    # Página 1: Informações básicas
    pdf.add_page()
    
    # Nome e nível
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, pdf.clean_text(character_info['name']), 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Nivel {character_info["level"]} - Pathfinder 2E', 0, 1, 'C')
    pdf.ln(5)
    
    # Atributos
    pdf.add_section_title("ATRIBUTOS")
    
    ability_scores = calculated['ability_scores']
    ability_mods = calculated['ability_modifiers']
    
    # Tabela de atributos
    headers = ['Atributo', 'Valor', 'Modificador']
    data = []
    
    ability_names = {
        'str': 'FORCA', 'dex': 'DESTREZA', 'con': 'CONSTITUICAO',
        'int': 'INTELIGENCIA', 'wis': 'SABEDORIA', 'cha': 'CARISMA'
    }
    
    for key, name in ability_names.items():
        score = ability_scores.get(key, 10)
        mod = ability_mods.get(key, 0)
        data.append([name, str(score), f"{mod:+}"])
    
    pdf.add_table(headers, data, [50, 40, 50])
    
    # Defesas
    pdf.add_section_title("DEFESAS")
    
    ac_info = calculated['ac']
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 8, 'Classe de Armadura:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, str(ac_info['total']), 0, 1)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 8, 'Armadura:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"+{ac_info['armor_bonus']}", 0, 1)
    
    if ac_info['shield_bonus'] > 0:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(50, 8, 'Escudo:', 0, 0)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 8, f"+{ac_info['shield_bonus']}", 0, 1)
    
    pdf.ln(5)
    
    # Testes de Resistência
    pdf.add_section_title("TESTES DE RESISTENCIA")
    
    saves = calculated['saves']
    headers = ['Teste', 'Total', 'Detalhes']
    data = []
    
    save_names = {
        'fortitude': 'Fortitude',
        'reflex': 'Reflexos', 
        'will': 'Vontade'
    }
    
    for save_key, save_name in save_names.items():
        if save_key in saves:
            save_info = saves[save_key]
            details = f"Mod: {save_info['ability_mod']:+}, Prof: +{save_info['prof_bonus']}"
            data.append([save_name, f"+{save_info['total']}", details])
    
    pdf.add_table(headers, data, [40, 40, 60])
    
    # Percepção
    perception = calculated['perception']
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 8, 'Percepcao:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"+{perception['total']} (Sab: {perception['wis_mod']:+}, Prof: +{perception['prof_bonus']})", 0, 1)
    
    # Ataques
    pdf.ln(5)
    pdf.add_section_title("ATAQUES")
    
    attacks = calculated['attacks']
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 8, 'Corpo a Corpo:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"+{attacks['melee']['total']}", 0, 1)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 8, 'Proficiencia:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"Nivel {attacks['melee']['proficiency']} (+{attacks['melee']['prof_bonus']})", 0, 1)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(50, 8, 'Modificadores:', 0, 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"STR: {attacks['melee']['str_mod']:+}, DEX: {attacks['melee']['dex_mod']:+}", 0, 1)
    
    # Página 2: Perícias
    pdf.add_page()
    pdf.add_section_title("PERICIAS")
    
    skills = calculated['skills']
    
    headers = ['Pericia', 'Nivel', 'Mod', 'Prof', 'Total']
    data = []
    
    skill_names_pt = {
        'acrobatics': 'Acrobacia',
        'athletics': 'Atletismo',
        'deception': 'Dissimulacao',
        'diplomacy': 'Diplomacia',
        'occultism': 'Ocultismo',
        'performance': 'Atuacao',
        'society': 'Sociedade'
    }
    
    rank_names = {0: 'NT', 1: 'T', 2: 'E', 3: 'M', 4: 'L'}
    
    for skill_key, skill_info in skills.items():
        skill_name = skill_names_pt.get(skill_key, skill_key.upper())
        rank = rank_names.get(skill_info['rank'], skill_info['rank'])
        
        data.append([
            skill_name,
            rank,
            f"{skill_info['ability_mod']:+}",
            f"+{skill_info['prof_bonus']}",
            f"+{skill_info['total']}"
        ])
    
    pdf.add_table(headers, data, [50, 20, 20, 20, 20])
    
    # Página 3: Talentos
    pdf.add_page()
    pdf.add_section_title("TALENTOS")
    
    feats = analyzer.get_feats_by_category()
    categories_pt = {
        'ancestry': 'Talentos de Ancestralidade',
        'class': 'Talentos de Classe',
        'skill': 'Talentos de Pericia',
        'general': 'Talentos Gerais'
    }
    
    for category, category_name in categories_pt.items():
        if feats[category]:
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(0, 8, pdf.clean_text(category_name), 0, 1)
            pdf.ln(2)
            
            pdf.set_font('Arial', '', 10)
            for feat in feats[category]:
                feat_name = pdf.clean_text(feat['name'])
                pdf.cell(0, 6, f"- {feat_name} (Nivel {feat['level']})", 0, 1)
            pdf.ln(3)
    
    # Página 4: Equipamento
    pdf.add_page()
    pdf.add_section_title("EQUIPAMENTO")
    
    # Armas
    weapons = analyzer.get_items_by_type('weapon')
    if weapons:
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, "ARMAS", 0, 1)
        pdf.ln(2)
        
        pdf.set_font('Arial', '', 10)
        seen_weapons = set()
        for weapon in weapons[:10]:
            weapon_name = pdf.clean_text(weapon['name'])
            if not weapon_name or weapon_name in seen_weapons:
                continue
            seen_weapons.add(weapon_name)
            
            # Extrair dano
            damage_text = ""
            if 'damage' in weapon.get('system', {}):
                damage = weapon['system']['damage']
                dice = damage.get('dice', 1)
                die = damage.get('die', 4)
                damage_type = damage.get('damageType', '')
                damage_text = f" - {dice}d{die} {pdf.clean_text(damage_type)}".strip()
            
            pdf.cell(0, 6, f"- {weapon_name}{damage_text}", 0, 1)
        
        pdf.ln(3)
    
    # Armaduras e Escudos
    armors = analyzer.get_items_by_type('armor')
    shields = analyzer.get_items_by_type('shield')
    
    if armors or shields:
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, "PROTECAO", 0, 1)
        pdf.ln(2)
        
        pdf.set_font('Arial', '', 10)
        for armor in armors:
            armor_name = pdf.clean_text(armor.get('name', ''))
            if armor_name:
                ac_bonus = armor.get('system', {}).get('acBonus', 0)
                pdf.cell(0, 6, f"- {armor_name}: +{ac_bonus} CA", 0, 1)
        
        for shield in shields:
            shield_name = pdf.clean_text(shield.get('name', ''))
            if shield_name:
                ac_bonus = shield.get('system', {}).get('acBonus', 0)
                pdf.cell(0, 6, f"- {shield_name}: +{ac_bonus} CA", 0, 1)
        
        pdf.ln(3)
    
    # Itens diversos
    equipment = analyzer.get_items_by_type('equipment')
    if equipment:
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, "ITENS DIVERSOS", 0, 1)
        pdf.ln(2)
        
        pdf.set_font('Arial', '', 10)
        seen_items = set()
        valid_items = []
        
        for item in equipment[:40]:
            item_name = pdf.clean_text(item.get('name', ''))
            if not item_name or item_name in seen_items:
                continue
            seen_items.add(item_name)
            
            quantity = item.get('system', {}).get('quantity', 1)
            if quantity > 1:
                valid_items.append(f"{item_name} (x{quantity})")
            else:
                valid_items.append(item_name)
        
        # Mostrar em duas colunas
        if valid_items:
            col_width = 85
            items_per_col = (len(valid_items) + 1) // 2
            
            # Salvar posição atual
            x_start = pdf.get_x()
            y_start = pdf.get_y()
            
            # Coluna 1
            for i in range(min(items_per_col, len(valid_items))):
                pdf.cell(col_width, 6, f"- {valid_items[i]}", 0, 1)
            
            # Mover para coluna 2
            pdf.set_xy(x_start + col_width + 5, y_start)
            
            # Coluna 2
            for i in range(items_per_col, min(2*items_per_col, len(valid_items))):
                pdf.cell(col_width, 6, f"- {valid_items[i]}", 0, 1)
            
            pdf.ln(3)
    
    # Consumíveis
    consumables = analyzer.get_items_by_type('consumable')
    if consumables:
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, "CONSUMIVEIS", 0, 1)
        pdf.ln(2)
        
        pdf.set_font('Arial', '', 10)
        seen_consumables = set()
        
        for item in consumables[:20]:
            item_name = pdf.clean_text(item.get('name', ''))
            if not item_name or item_name in seen_consumables:
                continue
            seen_consumables.add(item_name)
            
            quantity = item.get('system', {}).get('quantity', 1)
            pdf.cell(0, 6, f"- {item_name} (x{quantity})", 0, 1)
    
    # Página 5: Informações detalhadas
    pdf.add_page()
    pdf.add_section_title("INFORMACOES DETALHADAS")
    
    # Tabela de informações básicas
    headers = ['Campo', 'Valor']
    data = [
        ['Nome', pdf.clean_text(character_info['name'])],
        ['Nivel', character_info['level']],
        ['Pontos de Vida', f"{character_info['hp']} (+{character_info['temp_hp']} temporarios)"],
        ['Pontos de Heroi', f"{character_info['hero_points']}/{character_info['max_hero_points']}"],
        ['Experiencia', f"{character_info['xp']}/1000"],
        ['Atributo-Chave', character_info['key_ability'].upper()]
    ]
    
    pdf.add_table(headers, data, [60, 0])
    
    # Informações físicas
    pdf.ln(5)
    pdf.add_section_title("INFORMACOES FISICAS")
    
    physical_fields = [
        ('Idade', 'age'),
        ('Altura', 'height'), 
        ('Peso', 'weight'),
        ('Genero', 'gender'),
        ('Etnia', 'ethnicity'),
        ('Nacionalidade', 'nationality')
    ]
    
    pdf.set_font('Arial', 'B', 10)
    has_physical_info = False
    for field_name_pt, field_key in physical_fields:
        if field_key in character_info and character_info[field_key]:
            has_physical_info = True
            pdf.cell(40, 8, f"{field_name_pt}:", 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 8, pdf.clean_text(character_info[field_key]), 0, 1)
            pdf.set_font('Arial', 'B', 10)
    
    if not has_physical_info:
        pdf.set_font('Arial', 'I', 10)
        pdf.cell(0, 8, "Nenhuma informacao fisica registrada", 0, 1)
    
    # Origem do personagem
    pdf.ln(5)
    pdf.add_section_title("ORIGEM DO PERSONAGEM")
    
    # Ancestralidade
    ancestries = analyzer.get_items_by_type('ancestry')
    if ancestries:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, "Ancestralidade:", 0, 1)
        pdf.set_font('Arial', '', 10)
        for ancestry in ancestries:
            ancestry_name = pdf.clean_text(ancestry.get('name', ''))
            if ancestry_name:
                pdf.cell(0, 6, f"- {ancestry_name}", 0, 1)
        pdf.ln(2)
    
    # Classe
    classes = analyzer.get_items_by_type('class')
    if classes:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, "Classe:", 0, 1)
        pdf.set_font('Arial', '', 10)
        for class_item in classes:
            class_name = pdf.clean_text(class_item.get('name', ''))
            if class_name:
                pdf.cell(0, 6, f"- {class_name}", 0, 1)
        pdf.ln(2)
    
    # Antecedente
    backgrounds = analyzer.get_items_by_type('background')
    if backgrounds:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, "Antecedente:", 0, 1)
        pdf.set_font('Arial', '', 10)
        for background in backgrounds:
            background_name = pdf.clean_text(background.get('name', ''))
            if background_name:
                pdf.cell(0, 6, f"- {background_name}", 0, 1)
    
    # Salvar PDF
    try:
        pdf.output(output_filename)
        print(f"✓ PDF criado com sucesso: {output_filename}")
        return True
    except Exception as e:
        print(f"✗ Erro ao salvar PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================
# FUNÇÃO PRINCIPAL
# ==============================

def main():
    """Função principal"""
    if len(sys.argv) != 2:
        print("=" * 60)
        print("CONVERSOR DE FICHA PATHFINDER 2E - VERSÃO ASCII")
        print("=" * 60)
        print("Uso: python conversor_ascii.py <arquivo_json>")
        print("Exemplo: python conversor_ascii.py fvtt-Actor-nalarion.json")
        print("\nO arquivo PDF será gerado com o mesmo nome do JSON")
        print("=" * 60)
        sys.exit(1)
    
    json_file = sys.argv[1]
    
    try:
        if not os.path.exists(json_file):
            print(f"✗ Erro: Arquivo '{json_file}' não encontrado.")
            sys.exit(1)
        
        print(f"📂 Carregando arquivo: {json_file}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'name' not in data:
            print("✗ Erro: Arquivo JSON não parece ser uma ficha de personagem válida.")
            sys.exit(1)
        
        analyzer = CharacterAnalyzer(data)
        character_info = analyzer.get_character_info()
        print(f"👤 Personagem: {character_info['name']}")
        print(f"⭐ Nivel: {character_info['level']}")
        
        base_name = os.path.splitext(json_file)[0]
        pdf_filename = f"{base_name}_ficha_ascii.pdf"
        
        print("📄 Criando PDF...")
        result = create_character_pdf(analyzer, pdf_filename)
        
        if result:
            calculated = analyzer.calculated_values
            
            print("\n" + "=" * 60)
            print("✅ FICHA GERADA COM SUCESSO!")
            print("=" * 60)
            print(f"📋 Nome: {character_info['name']}")
            print(f"⭐ Nivel: {character_info['level']}")
            print(f"❤️  PV: {character_info['hp']}")
            print(f"🛡️  CA: {calculated['ac']['total']}")
            print(f"👁️  Percepcao: +{calculated['perception']['total']}")
            print(f"⚔️  Ataque: +{calculated['attacks']['melee']['total']}")
            print(f"\n📄 Arquivo PDF: {pdf_filename}")
            print("=" * 60)
            
            try:
                import platform
                system = platform.system()
                if system == "Windows":
                    os.startfile(pdf_filename)
                elif system == "Darwin":
                    os.system(f"open {pdf_filename}")
                elif system == "Linux":
                    os.system(f"xdg-open {pdf_filename}")
            except:
                print("Nota: O PDF foi criado mas não pôde ser aberto automaticamente.")
            
        else:
            print("✗ Falha ao criar o PDF.")
            
    except json.JSONDecodeError as e:
        print(f"✗ Erro ao decodificar JSON: {e}")
    except KeyError as e:
        print(f"✗ Erro no formato do JSON: Campo {e} não encontrado.")
    except Exception as e:
        print(f"✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()

# ==============================
# INÍCIO DO PROGRAMA
# ==============================

if __name__ == "__main__":
    try:
        from fpdf import FPDF
    except ImportError:
        print("=" * 60)
        print("📦 INSTALAÇÃO NECESSÁRIA")
        print("=" * 60)
        print("A biblioteca FPDF não está instalada.")
        print("\nInstale com: pip install fpdf")
        print("=" * 60)
        sys.exit(1)
    
    print("=" * 60)
    print("🔄 INICIANDO CONVERSOR DE FICHA PF2E - VERSÃO ASCII")
    print("=" * 60)
    print("Características:")
    print("✓ Usa apenas caracteres ASCII")
    print("✓ Sem erros de encoding")
    print("✓ Tabelas formatadas corretamente")
    print("✓ Itens limpos e sem duplicação")
    print("✓ Formatação profissional")
    print("=" * 60)
    
    main()