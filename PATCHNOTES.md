# Patch Notes

Notes for alpha testers, newest first. This tracks what's changed between
handed-off alpha builds (not every internal commit).

## v0.0.5

- **Fixed:** Ricochet-chained shots and Fork Shot could double up on
  piercing weapons (Fire Bullets, Gauss Gun, Blade Gun), sometimes spawning
  extra chained bolts off a single shot that hit several enemies. Piercing
  weapons are now consistently excluded from both Fork Shot and Ricochet -
  a bullet that already punches through a line of enemies doesn't also
  fork or chain off them.
- **Changed - Death Clock:** while its 30-second countdown is running, all
  healing is blocked and any shield you're carrying (Rainy Day Fund, etc.)
  is stripped immediately. Leech, Harvester's Scythe, and every other
  life-gain source do nothing until the clock resolves - the only thing
  moving your health while it's active is the clock itself.
- **Changed - late-game scaling:** past level 30, enemy spawn rate, enemy
  HP, and the XP needed to level up all now ramp up exponentially instead
  of leveling off. Kill rewards scale to match, so a player who's actually
  keeping up with the harder waves keeps progressing at a fair rate - it's
  the players who fall behind who'll feel the squeeze.
- **Added:** a visual indicator (cyan arc) for Pact of Gathering Winds'
  Tailwind stacks, so you can actually see them building.

## v0.0.4

- Impale's hit-count indicator moved from grey circles under the creature
  to tally marks above it.
- Added Impaler, Fortification, and War Banner relics.
- Retuned pact relic numbers; added range/timer visual overlays; capped
  Rainy Day Fund's shield.
- Fixed a relic-seed persistence bug.
- Fixed Ricochet re-chaining multiple times off a single piercing shot.
