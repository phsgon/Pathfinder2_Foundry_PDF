# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Fixed section toggles so unchecking a subsection no longer disables the whole section unless all children are off.
- Added first-page combat block with actions and weapon attack/damage summaries.
- Expanded spell rendering to include full descriptions and extra spell details.
- Simplified skills table to show totals only and always list all skills (including zero values).
- Fixed spell rendering crash when spell/entry fields are null or missing.
- Cleaned compendium/UUID markup from all text fields (not just spell descriptions).
- Added UI controls to reorder sections and persist the chosen order.
- Added drag-and-drop reordering for sections in the UI.
- Added `conversor_v2.py` (HTML/CSS -> PDF) with PF2E-inspired layout.
- Added sectioned layout with summary, talents, equipment, character info, and spells.
- Added inventory and spells notes areas for in-session writing.
- Added weapon, armor, shield, and treasure enrichment (damage, bonuses, traits, runes, CA, DEX cap, penalties).
- Added spells support (spellcasting entries + spells grouped by entry).
- Added actions and backpack contents rendering.
- Added support for `system.abilities`, expanded skills mapping, and lore labels.
- Added exploration/initiative/resources rendering in character data section.
- Added Web UI (`--web-ui`) with hierarchical section toggles, JSON list, and drag-and-drop upload.
- Added Web UI preview generation with floating "Gerar ficha" button and timestamped `temp/` previews.
- Added output organization (`output/` + `temp/`) and config persistence.
