# Pathfinder2_Foundry_PDF

Conversor de ficha do **Foundry VTT (Pathfinder 2E)** de JSON para PDF, pensado para uso em mesas presenciais.

## Versões
Este projeto possui duas versões:
- **v1 (`conversor.py`)**: gera PDF direto com FPDF (mais simples).
- **v2 (`conversor_v2.py`)**: gera HTML/CSS com visual mais amigável e exporta para PDF via Chrome/Chromium.

Recomendado: **v2**.

## Como funciona (v2)
O script lê o JSON exportado do personagem no Foundry, calcula os valores derivados (atributos, CA, resistências, perícias, ataques e percepção) e gera um HTML com layout inspirado em PF2E. Em seguida, exporta para PDF usando o Chrome/Chromium em modo headless.

### Principais cálculos
- **Atributos**: começa em 10 e aplica boosts de ancestralidade, antecedente e níveis (build).
- **CA**: 10 + Destreza (limitada pelo cap da armadura) + bônus da armadura + proficiência + bônus de escudo.
- **Resistências**: Fortitude, Reflexos e Vontade com proficiência por rank e modificadores de habilidade.
- **Perícias**: rank + mod. de habilidade correspondente.
- **Ataques**: proficiência + maior entre Força/Destreza.

## Requisitos
- Python 3
- v1: Biblioteca `fpdf`
- v2: Chrome/Chromium instalado (para exportar PDF)

Instalação:
```bash
pip install fpdf
```

## Como usar
### v2 (recomendado)
```bash
python conversor_v2.py seu-personagem.json
```

Arquivos gerados:
- `output/<nome>_ficha.html`
- `output/<nome>_ficha.pdf`

### v2 CLI (opcoes)
```bash
python conversor_v2.py seu-personagem.json
```

### v2 Web UI (recomendado para selecao de secoes)
```bash
python conversor_v2.py --web-ui
```

A interface web permite hierarquia de secoes, botao "Ativar todas", selecao de JSONs disponiveis e upload via drag-and-drop. As escolhas ficam salvas em `output/config.json`.

Na Web UI, o botao "Gerar previa" cria um arquivo em `temp/` no formato `preview_<json>_YYYY-MM-DD_HH-MM-SS_temp.html` e abre em uma nova aba com um botao flutuante de "Gerar ficha".
A ordem das secoes pode ser ajustada na UI (botoes ↑/↓) e fica persistida no config.

### Tradução
A funcionalidade de tradução foi removida por enquanto.

### v1 (FPDF)
1. Exporte o JSON do personagem no Foundry VTT.
2. Coloque o arquivo JSON na mesma pasta do script.
3. Rode o conversor:

```bash
python conversor.py seu-personagem.json
```

O PDF será gerado com o mesmo nome do JSON, com o sufixo `_ficha_ascii.pdf`.

## O que sai no PDF
- Identificação do personagem (nome, nível, HP, XP, atributo-chave)
- Atributos e modificadores
- CA, resistências, percepção e ataques
- Perícias
- Talentos por categoria
- Equipamentos (armas, proteções, itens diversos e consumíveis)
- Informações físicas e origem (ancestralidade, classe, antecedente)

## Observações
- O PDF é gerado com **apenas caracteres ASCII** para evitar problemas de encoding.
- Se o PDF não abrir automaticamente, basta abrir o arquivo gerado manualmente.
- Na v2, os arquivos são salvos em `output/` (ignorados pelo git).
