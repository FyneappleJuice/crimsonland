# Patch Notes

Notes for alpha testers, newest first. This tracks what's changed between
handed-off alpha builds (not every internal commit).

## v0.0.7

- **Added - Pact of the Giant (relic):** dual-wield two weapons at once.
  The two guns take strict turns, one shot each, at a 1.5x slower fire
  rate - unless one is out of ammo, in which case the other fires alone at
  its normal rate. Both reload together once both are dry. Manual reload
  flips which slot is "active" (the one a weapon pickup replaces). Your
  first two kills with the starter Pistol each have the usual 3/4 chance
  to drop a weapon, and the second drop leans toward the same class and
  damage type as the first. Every weapon perk and effect (Ammo Maniac, My
  Favourite Weapon, Reflex Boost, Weapon Power Up, Fire Bullets, Plasma
  Overload refills, Ammo Shield, etc.) applies to both guns. Replaces the
  Alternate Weapon perk, which is out of the pool.
- **Added - dual-wield HUD:** with the Giant equipped, the top-left shows
  two framed weapon panels joined by panel hardware, and the ammo readout
  on your character shows "A, B" with the active weapon underlined.
- **Changed - Stunt Double / Domino Effect with two weapons:** the clone
  dual-wields and alternates exactly like you do, and Domino Effect's free
  shot fires the weapon that actually got the kill.
- **Added - Current Stats:** the level-up screen's Stat Bonuses panel now
  shows your actual HP, crit chance, crit multiplier, move speed and
  reload time in its bottom half (per weapon, comma-separated, when
  dual-wielding).
- **Added - Sandbox mode:** Play Game's "Maps" button is now "Sandbox" -
  an empty arena with damage dummies (live damage/DPS readouts), 1-HP
  test monsters, and a debug panel to add/remove perks, relics and run
  mods, equip any weapon, spawn monsters with chosen rarity/affixes, and
  change game speed. You can't die in Sandbox. Hovering a relic (here or
  in the relic inventory) now shows what it does.
- **Added - monster variety:** every creature type, Lizards included, can
  now show up from the start of a Survival run. Dens are a recurring
  system from level 4 on, and rare monsters get more common as you
  progress. There are 18 new monster modifiers (auras, Camouflaged,
  Flickering, Second Wind, Vortex, Phalanx and more). Explosive on-death
  modifiers (Bomber, Pyre, Anchoring) now show a fuse ring and give you
  time to get clear instead of hitting instantly.
- **Changed - Survival pacing:** regular monster waves now spawn 25% less
  often at every stage of a run. Dens appear at a random spot in the arena
  (never right on top of you) instead of always just off one of the four
  map edges. Rare (Tainted/Mutated/Apex) monsters and dens stay at their
  base odds until level 15, and only start getting more common from there.
- **Changed - relics:** each relic pact now comes in one strength only
  (the old Low tier); Medium/High versions are gone.
- **Changed - balance:** Ricochet 60% less damage per bounce (was 48%);
  Deadeye far bonus 20% and uncapped past 500 units; Gathering Winds
  range widened to +-20%; Leech heals over 5 seconds per hit instead of
  instantly; War Banner radius 60 / +25% speed (was 75 / +30%). Uranium
  Filled Bullets (+upgrade) 1.5x, Barrel Greaser 1.3x, Loose Cannon 1.3x
  average, Slayer 1.2x, Critical Mass 1.2x, Ricochet pact 0.35x, Impaler
  1.25x.
- **Changed - weapons:** the Blade Gun is back as a normal weapon drop.
- **Fixed - Multi-Plasma / Plasma Overload:** their extra bolts now crit
  and count as shots, so Fire and Forget, Deep Freeze, Harvester's Scythe,
  Overdue, Death Wish, Diamond Flask and Critical Mass all work with them
  (Fire and Forget used to never fire its rockets).
- **Fixed - crits on secondary damage:** Plasma Cannon rings, ion clouds,
  Explosive Payload and Seeker Rounds' bonus rocket now carry the crit of
  the hit that triggered them. In co-op, Arc Gun, Evil Scythe and Blade
  Orbit kills now credit the right player.
- **Fixed - Perk Gambler:** its penalty now always shows (and applies) a
  real run mod instead of a vague "Weapon Affinity". Arc Damage is no
  longer offered as a secondary perk.
- **Changed:** the "Reload Speed" run mod is now labelled "Reload Time",
  which is what it actually changes.

## v0.0.6

- **Added - Auto-fire:** new keybind (default **T**) toggles a mode where
  the fire button clicks instead of holds - click once to start firing
  continuously, click again to stop. Holding the fire button still works
  normally at any time, mode on or off. Rebindable per-player in the
  Controls menu.
- **Added - build panel:** a new panel slides in from the right edge of
  the screen during level-up, listing every perk you've picked this run
  plus a summary of your current stat bonuses (damage, fire rate, crit,
  move speed, etc.) at the bottom.
- **Fixed - level-up flow:** picking a perk now chains straight into the
  next one if you have several queued, instead of needing to re-open the
  menu for every single one. Cancel on either the main or secondary perk
  panel now backs you out of the whole level-up instead of leaving the
  other one stranded open; and once you've picked one side, the other
  side can no longer be cancelled out from under it - you have to also
  resolve it.
- **Added:** a fill indicator (green, growing from the tail) on the
  direction arrow for Full Steam Ahead (Kinetic Discipline), showing how
  close you are to the full damage bonus.
- **Performance:** meaningfully reduced lag from piercing weapons (Fire
  Bullets, Gauss Gun, Blade Gun, WPU pierce) in dense late-game hordes -
  a hot collision check was doing expensive precise math on targets that
  were nowhere near hit range; it now fast-rejects those first.

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
- **Fixed:** Ricochet could chain off a shot fired from a weapon that
  already pierces (Fire Bullets, Gauss Gun, Blade Gun) - piercing weapons
  are now excluded from chaining entirely, same rule Fork Shot already
  follows.
- **Changed - Barrel Greaser:** its damage and fire-rate/speed bonus now
  also apply to all four rocket weapons (Rocket Launcher, Seeker Rockets,
  Rocket Minigun, Mini-Rocket Swarmers) - previously it did nothing for
  rockets at all.

## v0.0.4

- Impale's hit-count indicator moved from grey circles under the creature
  to tally marks above it.
- Added Impaler, Fortification, and War Banner relics.
- Retuned pact relic numbers; added range/timer visual overlays; capped
  Rainy Day Fund's shield.
- Fixed a relic-seed persistence bug.
- Fixed Ricochet re-chaining multiple times off a single piercing shot.
