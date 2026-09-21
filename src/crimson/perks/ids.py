from __future__ import annotations

"""Perk ids and runtime metadata extracted from `perks_init_database`."""

from enum import IntEnum, IntFlag, unique

import msgspec


class PerkFlags(IntFlag):
    # `perk_can_offer` uses these bits as mode-specific allow-lists:
    # - in quest mode, only perks with QUEST_MODE_ALLOWED are eligible
    # - in multiplayer, only perks with MULTIPLAYER_ALLOWED are eligible
    QUEST_MODE_ALLOWED = 0x1
    MULTIPLAYER_ALLOWED = 0x2
    STACKABLE = 0x4  # can be offered even if already owned


# Native perk metadata defaults to both quest and multiplayer allow bits enabled
# (`perk_meta_entry_init` initializes flags to 3).
PERK_DEFAULT_FLAGS = PerkFlags.QUEST_MODE_ALLOWED | PerkFlags.MULTIPLAYER_ALLOWED


@unique
class PerkId(IntEnum):
    ANTIPERK = 0
    BLOODY_MESS_QUICK_LEARNER = 1
    SHARPSHOOTER = 2
    FASTLOADER = 3
    LEAN_MEAN_EXP_MACHINE = 4
    LONG_DISTANCE_RUNNER = 5
    PYROKINETIC = 6
    INSTANT_WINNER = 7
    GRIM_DEAL = 8
    ALTERNATE_WEAPON = 9
    PLAGUEBEARER = 10
    EVIL_EYES = 11
    AMMO_MANIAC = 12
    RADIOACTIVE = 13
    FASTSHOT = 14
    FATAL_LOTTERY = 15
    RANDOM_WEAPON = 16
    MR_MELEE = 17
    ANXIOUS_LOADER = 18
    FINAL_REVENGE = 19
    TELEKINETIC = 20
    PERK_EXPERT = 21
    UNSTOPPABLE = 22
    REGRESSION_BULLETS = 23
    INFERNAL_CONTRACT = 24
    POISON_BULLETS = 25
    DODGER = 26
    BONUS_MAGNET = 27
    URANIUM_FILLED_BULLETS = 28
    DOCTOR = 29
    MONSTER_VISION = 30
    HOT_TEMPERED = 31
    BONUS_ECONOMIST = 32
    THICK_SKINNED = 33
    BARREL_GREASER = 34
    AMMUNITION_WITHIN = 35
    VEINS_OF_POISON = 36
    TOXIC_AVENGER = 37
    REGENERATION = 38
    PYROMANIAC = 39
    NINJA = 40
    HIGHLANDER = 41
    JINXED = 42
    PERK_MASTER = 43
    REFLEX_BOOSTED = 44
    GREATER_REGENERATION = 45
    BREATHING_ROOM = 46
    DEATH_CLOCK = 47
    MY_FAVOURITE_WEAPON = 48
    BANDAGE = 49
    ANGRY_RELOADER = 50
    ION_GUN_MASTER = 51
    STATIONARY_RELOADER = 52
    MAN_BOMB = 53
    FIRE_CAUGH = 54
    LIVING_FORTRESS = 55
    TOUGH_RELOADER = 56
    LIFELINE_50_50 = 57

    # Rewrite-only: "++" tier upgrades. Each requires its base perk as a
    # prereq (see docs on PerkMeta.prereq below) and, like the four native
    # tier pairs (Dodger->Ninja, Veins of Poison->Toxic Avenger, Perk
    # Expert->Perk Master, Regeneration->Greater Regeneration), pushes the
    # same single knob further rather than adding a new effect.
    FASTSHOT_PLUS = 58
    FASTLOADER_PLUS = 59
    AMMO_MANIAC_PLUS = 60
    URANIUM_FILLED_BULLETS_PLUS = 61
    BONUS_ECONOMIST_PLUS = 62
    BLOODY_MESS_QUICK_LEARNER_PLUS = 63
    LEAN_MEAN_EXP_MACHINE_PLUS = 64
    LONG_DISTANCE_RUNNER_PLUS = 65
    MR_MELEE_PLUS = 66
    BONUS_MAGNET_PLUS = 67
    TOUGH_RELOADER_PLUS = 68
    THICK_SKINNED_PLUS = 69

    # Rewrite-only: brand-new perks (not tiers of anything), mined from D2/D3
    # unique-item research. Names are working placeholders, expected to change.
    AMMO_SHIELD = 70
    COUP_DE_GRACE = 71
    DEATH_WISH = 72
    MOMENTUM = 73
    COLD_SNAP = 74
    DESPERATION = 75
    OVERDUE = 76
    KINETIC_DISCIPLINE = 77
    FREE_ROUNDS = 78
    STEADY_HANDS = 79
    ADRENALINE_RUSH = 80
    PENDULUM = 81
    BANE_OF_LEGENDS = 82
    SOUL_TETHER = 83
    DIAMOND_FLASK = 84
    LIKE_CLOCKWORK = 85
    HOLLOW_FORM = 86
    HIT_LIST = 87
    DELICATE_WATCH = 88
    HARVESTER_SCYTHE = 89


class PerkMeta(msgspec.Struct, frozen=True):
    perk_id: PerkId
    name: str
    description: str
    flags: PerkFlags
    prereq: tuple[PerkId, ...] = ()


_PERK_TABLE = [
    PerkMeta(
        perk_id=PerkId.ANTIPERK,
        name="AntiPerk",
        description="You shouldn't be seeing this..",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BLOODY_MESS_QUICK_LEARNER,
        name="Bloody Mess",
        description="More the merrier. More blood guarantees a 30% better experience. You spill more blood and gain more experience points.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.SHARPSHOOTER,
        name="Sharpshooter",
        description="Miraculously your aiming improves drastically, but you take a little bit more time on actually firing the gun. If you order now, you also get a fancy LASER SIGHT without ANY charge!",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FASTLOADER,
        name="Fastloader",
        description="Man, you sure know how to load a gun.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.LEAN_MEAN_EXP_MACHINE,
        name="Lean Mean Exp Machine",
        description="Why kill for experience when you can make some of your own for free! With this perk the experience just keeps flowing in at a constant rate.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.LONG_DISTANCE_RUNNER,
        name="Long Distance Runner",
        description="You move like a train that has feet and runs. You just need a little time to warm up. In other words you'll move faster the longer you run without stopping.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PYROKINETIC,
        name="Pyrokinetic",
        description="You see flames everywhere. Bare aiming at creatures causes them to heat up.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.INSTANT_WINNER,
        name="Instant Winner",
        description="2500 experience points. Right away. Take it or leave it.",
        flags=PERK_DEFAULT_FLAGS | PerkFlags.STACKABLE,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.GRIM_DEAL,
        name="Grim Deal",
        description="I'll make you a deal: I'll give you 18% more experience points, and you'll give me your life. So you'll die but score higher. Ponder that one for a sec.",
        flags=PerkFlags(0),
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.ALTERNATE_WEAPON,
        name="Alternate Weapon",
        description="Ever fancied about having two weapons available for use? This might be your lucky day; with this perk you'll get an extra weapon slot for another gun! Carrying around two guns slows you down slightly though. (You can switch the weapon slots with RELOAD key)",
        flags=PerkFlags.QUEST_MODE_ALLOWED,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PLAGUEBEARER,
        name="Plaguebearer",
        description="You carry a horrible disease. Good for you: you are immune. Bad for them: it is contagious! (Monsters become resistant over time though.)",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.EVIL_EYES,
        name="Evil Eyes",
        description="No living (nor dead) can resist the hypnotic power of your eyes: monsters freeze still as you look at them!",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.AMMO_MANIAC,
        name="Ammo Maniac",
        description="You squeeze and you push and you pack your clips with about 20% more ammo than a regular fellow. They call you Ammo Maniac with a deep respect in their voices.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.RADIOACTIVE,
        name="Radioactive",
        description="You are the Radioactive-man; you have that healthy green glow around you! Others don't like it though, it makes them sick and nauseous whenever near you. It does affect your social life a bit.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FASTSHOT,
        name="Fastshot",
        description="Funny how you make your gun spit bullets faster than the next guy. Even the most professional of engineers are astonished.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FATAL_LOTTERY,
        name="Fatal Lottery",
        description="Fifty-fifty chance of dying OR gaining 10k experience points. Place your bets. Interested, anyone?",
        flags=PerkFlags.STACKABLE,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.RANDOM_WEAPON,
        name="Random Weapon",
        description="Here, have this weapon. No questions asked.",
        flags=PerkFlags.QUEST_MODE_ALLOWED | PerkFlags.STACKABLE,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.MR_MELEE,
        name="Mr. Melee",
        description="You master the art of melee fighting. You don't just stand still when monsters come near -- you hit back. Hard.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.ANXIOUS_LOADER,
        name="Anxious Loader",
        description="When you can't stand waiting your gun to be reloaded you can speed up the process by clicking your FIRE button repeatedly as fast as you can.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FINAL_REVENGE,
        name="Final Revenge",
        description="Pick this and you'll get your revenge. It's a promise.",
        flags=PerkFlags(0),
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.TELEKINETIC,
        name="Telekinetic",
        description="Picking up bonuses has never been so easy and FUN. You can pick up bonuses simply by aiming at them for a while. Ingenious.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PERK_EXPERT,
        name="Perk Expert",
        description="You sure know how to pick a perk -- most people just don't see that extra perk laying around. This gives you the opportunity to pick the freshest and shiniest perks from the top.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.UNSTOPPABLE,
        name="Unstoppable",
        description="Monsters can't slow you down with their nasty scratches and bites. It still hurts but you simply ignore the pain.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.REGRESSION_BULLETS,
        name="Regression Bullets",
        description="Attempt to shoot with an empty clip leads to a severe loss of experience. But hey, whatever makes them go down, right?",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.INFERNAL_CONTRACT,
        name="Infernal Contract",
        description="In exchange for your soul, a dark stranger is offering you three (3) new perks. To collect his part of the bargain soon enough, your health is reduced to a near-death status. Just sign down here below this pentagram..",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.POISON_BULLETS,
        name="Poison Bullets",
        description="You tend to explicitly treat each of your bullets with rat poison. You do it for good luck, but it seems to have other side effects too.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DODGER,
        name="Dodger",
        description="It seems so stupid just to take the hits. Each time a monster attacks you you have a chance to dodge the attack.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BONUS_MAGNET,
        name="Bonus Magnet",
        description="You somehow seem to lure all kinds of bonuses to appear around you more often.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.URANIUM_FILLED_BULLETS,
        name="Uranium Filled Bullets",
        description="Your bullets have a nice creamy uranium filling. Yummy. Now that's gotta hurt the monsters more, right?",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DOCTOR,
        name="Doctor",
        description="With a single glance you can tell the medical condition of, well, anything. Also, being a doctor, you know exactly what hurts the most enabling you to do slightly more damage with your attacks.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.MONSTER_VISION,
        name="Monster Vision",
        description="With your newly enhanced senses you can see all bad energy VERY clearly. That's got to be enough.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.HOT_TEMPERED,
        name="Hot Tempered",
        description="It literally boils inside you. That's exactly why you need to let it out once in a while, unfortunately for those near you.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BONUS_ECONOMIST,
        name="Bonus Economist",
        description="Your bonus power-ups last 50% longer than they normally would.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.THICK_SKINNED,
        name="Thick Skinned",
        description="Trade 1/3 of your health for only receiving 2/3rds damage on attacks.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BARREL_GREASER,
        name="Barrel Greaser",
        description="After studying a lot of physics and friction you've come up with a way to make your bullets fly faster. More speed, more damage.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.AMMUNITION_WITHIN,
        name="Ammunition Within",
        description="Empty clip doesn't prevent you from shooting with a weapon; instead the ammunition is drawn from your health while you are reloading.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.VEINS_OF_POISON,
        name="Veins of Poison",
        description="A strong poison runs through your veins. Monsters taking a bite of you are eventually to experience an agonizing death.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.TOXIC_AVENGER,
        name="Toxic Avenger",
        description="You started out just by being poisonous. The next logical step for you is to become highly toxic -- the ULTIMATE TOXIC AVENGER. Most monsters touching you will just drop dead within seconds!",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.VEINS_OF_POISON,),
    ),
    PerkMeta(
        perk_id=PerkId.REGENERATION,
        name="Regeneration",
        description="Your health replenishes but very slowly. What more there is to say?",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PYROMANIAC,
        name="Pyromaniac",
        description="You just enjoy using fire as your Tool of Destruction and you're good at it too; your fire based weapons do a lot more damage.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.NINJA,
        name="Ninja",
        description="You've taken your dodging abilities to the next level; monsters have really hard time hitting you.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.DODGER,),
    ),
    PerkMeta(
        perk_id=PerkId.HIGHLANDER,
        name="Highlander",
        description="You are immortal. Well, almost immortal. Instead of actually losing health on attacks you've got a 10% chance of just dropping dead whenever a monster attacks you. There really can be only one, you know.",
        flags=PerkFlags(0),
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.JINXED,
        name="Jinxed",
        description="Things happen near you. Strangest things. Creatures just drop dead and accidents happen. Beware.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PERK_MASTER,
        name="Perk Master",
        description="Being the Perk Expert taught you a few things and now you are ready to take your training to the next level doubling the ability effect.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.PERK_EXPERT,),
    ),
    PerkMeta(
        perk_id=PerkId.REFLEX_BOOSTED,
        name="Reflex Boosted",
        description="To you the world seems to go on about 10% slower than to an average person. It can be rather irritating sometimes, but it does give you a chance to react better.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.GREATER_REGENERATION,
        name="Greater Regeneration",
        description="Your health replenishes faster than ever.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.REGENERATION,),
    ),
    PerkMeta(
        perk_id=PerkId.BREATHING_ROOM,
        name="Breathing Room",
        description="Trade 2/3rds of your health for the killing of every single creature on the screen. No, you don't get the experience.",
        flags=PerkFlags.MULTIPLAYER_ALLOWED,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DEATH_CLOCK,
        name="Death Clock",
        description="You die exactly in 30 seconds. You can't escape your destiny, but feel free to go on a spree. Tick, tock.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.MY_FAVOURITE_WEAPON,
        name="My Favourite Weapon",
        description="You've grown very fond of your piece. You polish it all the time and talk nice to it, your precious. (+2 clip size, no more random weapon bonuses)",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BANDAGE,
        name="Bandage",
        description="Here, eat this bandage and you'll feel a lot better in no time. (restores up to 50% health)",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.ANGRY_RELOADER,
        name="Angry Reloader",
        description="You hate it when you run out of shots. You HATE HATE HATE reloading your gun. Lucky for you, and strangely enough, your hate materializes as Mighty Balls of Fire. Or more like Quite Decent Balls of Fire, but it's still kinda neat, huh?",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.ION_GUN_MASTER,
        name="Ion Gun Master",
        description="You're good with ion weapons. You're so good that not only your shots do slightly more damage but your ion blast radius is also increased.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.STATIONARY_RELOADER,
        name="Stationary Reloader",
        description="It's incredibly hard to reload your piece while moving around, you've noticed. In fact, realizing that, when you don't move a (leg) muscle you can reload the gun THREE TIMES FASTER!",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.MAN_BOMB,
        name="Man Bomb",
        description="You have the ability to go boom for you are the MAN BOMB. Going boom requires a lot of concentration and standing completely still for a few seconds.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FIRE_CAUGH,
        name="Fire Caugh",
        description="You have a fireball stuck in your throat. Repeatedly. Mind your manners.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.LIVING_FORTRESS,
        name="Living Fortress",
        description="It comes a time in each man's life when you'd just rather not move anymore. Being living fortress not moving comes with extra benefits as well. You do the more damage the longer you stand still.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.TOUGH_RELOADER,
        name="Tough Reloader",
        description="Damage received during reloading a weapon is halved.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.LIFELINE_50_50,
        name="Lifeline 50-50",
        description="The computer removes half of the wrong monsters for you. You don't gain any experience.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    # --- Rewrite-only "++" tier upgrades -------------------------------
    PerkMeta(
        perk_id=PerkId.FASTSHOT_PLUS,
        name="Fastshot++",
        description="Your gun spits bullets even faster than before. The engineers have given up trying to explain it.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.FASTSHOT,),
    ),
    PerkMeta(
        perk_id=PerkId.FASTLOADER_PLUS,
        name="Fastloader++",
        description="You've halved your reload time now. Loading a gun has never looked so effortless.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.FASTLOADER,),
    ),
    PerkMeta(
        perk_id=PerkId.AMMO_MANIAC_PLUS,
        name="Ammo Maniac++",
        description="You've upgraded your obsession; your clips now hold considerably more than before.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.AMMO_MANIAC,),
    ),
    PerkMeta(
        perk_id=PerkId.URANIUM_FILLED_BULLETS_PLUS,
        name="Uranium Filled Bullets++",
        description="You've enriched the filling even further. That's got to be against some kind of treaty.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.URANIUM_FILLED_BULLETS,),
    ),
    PerkMeta(
        perk_id=PerkId.BONUS_ECONOMIST_PLUS,
        name="Bonus Economist++",
        description="Your bonus power-ups now last twice as long as they normally would.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.BONUS_ECONOMIST,),
    ),
    PerkMeta(
        perk_id=PerkId.BLOODY_MESS_QUICK_LEARNER_PLUS,
        name="Bloody Mess++",
        description="You've taken your bloodlust to the next level; the carnage teaches you even faster now.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.BLOODY_MESS_QUICK_LEARNER,),
    ),
    PerkMeta(
        perk_id=PerkId.LEAN_MEAN_EXP_MACHINE_PLUS,
        name="Lean Mean Exp Machine++",
        description="You've tuned your experience machine into a leaner, meaner, faster-flowing one.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.LEAN_MEAN_EXP_MACHINE,),
    ),
    PerkMeta(
        perk_id=PerkId.LONG_DISTANCE_RUNNER_PLUS,
        name="Long Distance Runner++",
        description="You've kept training. You now warm up to a much higher top speed than before.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.LONG_DISTANCE_RUNNER,),
    ),
    PerkMeta(
        perk_id=PerkId.MR_MELEE_PLUS,
        name="Mr. Melee++",
        description="Your counterattacks hit twice as hard now. Some might say you've mastered the art.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.MR_MELEE,),
    ),
    PerkMeta(
        perk_id=PerkId.BONUS_MAGNET_PLUS,
        name="Bonus Magnet++",
        description="Bonuses find their way to you even more often now. You're basically a lodestone.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.BONUS_MAGNET,),
    ),
    PerkMeta(
        perk_id=PerkId.TOUGH_RELOADER_PLUS,
        name="Tough Reloader++",
        description="Damage received during reloading is cut down even further now.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.TOUGH_RELOADER,),
    ),
    PerkMeta(
        perk_id=PerkId.THICK_SKINNED_PLUS,
        name="Thick Skinned++",
        description="Your skin thickens further still. Trade another third of your health for another third off incoming damage.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(PerkId.THICK_SKINNED,),
    ),
    # --- Rewrite-only: new perks (name placeholders, TBD) --------------
    PerkMeta(
        perk_id=PerkId.AMMO_SHIELD,
        name="Ammo Insurance",
        description="Your ammo hates seeing you get hurt. HATES it. So now, whenever you'd take damage, a few rounds throw themselves in the way instead. Heroic, really. Also, kind of expensive.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.COUP_DE_GRACE,
        name="The Closer",
        description="Something in you can't stand watching an enemy limp along on fumes. It's gotta stop, right now. So anything clinging to its last sliver of health gets finished off completely. Unfortunate, but necessary.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DEATH_WISH,
        name="Nothing to Lose",
        description="Once your health bottoms out, something in you just stops caring. About missing, about dying, about a lot of things really. Every shot you fire from here on out is a critical hit. Fear does wonders for your aim.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.MOMENTUM,
        name="Domino Effect",
        description="You can't stop once you get going. One kill and something in you needs another, immediately, whether you meant to or not. A free shot flies out at whatever's closest. You didn't ask it to. It happened anyway.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.COLD_SNAP,
        name="Deep Freeze",
        description="Something about your critical hits just isn't right anymore. They don't wound, they freeze solid, on the spot, no warmup required. And whatever's frozen, yours or not, you just seem to hit harder. You've stopped asking why.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DESPERATION,
        name="Survival Instinct",
        description="Something primal kicks in once things get dicey, and it does NOT want to die today. The lower your health drops, the less incoming damage actually gets through. Logic has left the building.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.OVERDUE,
        name="Statistically Speaking",
        description="You keep track of every crit that doesn't land. Miss five in a row and something changes: for the next five seconds, every crit you do land comes back scorching hot, like it was making up for lost time.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.KINETIC_DISCIPLINE,
        name="Full Steam Ahead",
        description="You get a little obsessive about holding a straight line. The longer you commit, the harder you hit, like you're building up a full head of steam. Turn, stop, or so much as flinch, though, and poof. Right back to square one.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.FREE_ROUNDS,
        name="Five Finger Discount",
        description="Every so often, a bullet just doesn't get charged to your clip. You didn't do anything. You definitely didn't do anything. Nobody's checking the register anyway.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.STEADY_HANDS,
        name="Cheap Shot",
        description="You've got zero patience for enemies that haven't earned their scars yet. Anything still sitting near full health gets hit that much harder. Gotta soften them up somehow, right?",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.ADRENALINE_RUSH,
        name="Chip on Your Shoulder",
        description="Getting hurt just makes you meaner. For the next five seconds, every shot you fire lands like it's got something to prove.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.PENDULUM,
        name="Mood Swing",
        description="Your gun can't settle on a personality. Every clip it swings between hitting harder and shooting faster, and it never asks your permission. Reload early, though, and you get to make the call yourself.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.BANE_OF_LEGENDS,
        name="Taste of Blood",
        description="You pull every punch until you draw blood. Normally your hits land soft, but the second something actually dies, all that restraint goes out the window for a few seconds.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.SOUL_TETHER,
        name="Rainy Day Fund",
        description="You've never let a good thing go to waste. Healing that would overflow past full gets tucked away as a shield instead, though it won't stay in savings if you stop making deposits.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DIAMOND_FLASK,
        name="Double or Nothing",
        description="You never take the first answer luck gives you. You ask twice, and keep whichever roll you like better. Get greedy enough to land both, though, and the payout doubles right along with your nerve.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.LIKE_CLOCKWORK,
        name="Short Fuse",
        description="Everything you own that runs on a timer just got impatient. Whatever used to take its sweet time now can't wait around. It happens twice as often, whether you like it or not.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.HOLLOW_FORM,
        name="Stunt Double",
        description="You've got someone who does the dangerous work so you don't have to. Every so often they step in wearing your face, empty the clip at whatever's closest for a couple of seconds, and slip out before anyone realizes the swap.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.HIT_LIST,
        name="Personal Beef",
        description="You've picked a favorite out of the crowd, whichever apex predator caught your eye first, and now it's personal. Settling the score makes your hits land harder, permanently, though only so much. There's always another name worth holding a grudge against.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.DELICATE_WATCH,
        name="Glass Jaw",
        description="You hit like you've got something to prove, and it shows. The catch is you can't take a punch nearly as well, and one good hit is enough to rattle the confidence right out of you for good. You'll talk yourself into it again eventually.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
    PerkMeta(
        perk_id=PerkId.HARVESTER_SCYTHE,
        name="Critical Care",
        description="Somehow, every critical hit doubles as first aid. It's not much, just enough to keep you standing a little longer than you should. Call it a professional courtesy between you and whatever you just shot.",
        flags=PERK_DEFAULT_FLAGS,
        prereq=(),
    ),
]

PERK_BY_ID: dict[PerkId, PerkMeta] = {entry.perk_id: entry for entry in _PERK_TABLE}

QUICK_LEARNER_NAME = "Quick Learner"
QUICK_LEARNER_DESCRIPTION = (
    "You learn things faster than a regular Joe from now on gaining 30% more experience points from everything you do."
)

_PERK_FIXED_NAMES = {
    PerkId.FIRE_CAUGH: "Fire Cough",
}

_PERK_FIXED_DESCRIPTIONS = {
    PerkId.ANXIOUS_LOADER: "When you can't stand waiting for your gun to be reloaded you can speed up the process by clicking your FIRE button repeatedly as fast as you can.",
    PerkId.PERK_EXPERT: "You sure know how to pick a perk -- most people just don't see that extra perk laying around. This gives you the opportunity to pick the freshest and shiniest perks from the top.",
    PerkId.DODGER: "It seems so stupid just to take the hits. Each time a monster attacks you, you have a chance to dodge the attack.",
    PerkId.NINJA: "You've taken your dodging abilities to the next level; monsters have a really hard time hitting you.",
    PerkId.LIVING_FORTRESS: "There comes a time in each man's life when you'd just rather not move anymore. Being a living fortress comes with extra benefits as well. You do more damage the longer you stand still.",
}


def perk_display_name(perk_id: PerkId, *, violence_disabled: int = 0, preserve_bugs: bool = False) -> str:
    if perk_id == PerkId.BLOODY_MESS_QUICK_LEARNER and int(violence_disabled) != 0:
        return QUICK_LEARNER_NAME
    entry = PERK_BY_ID[perk_id]
    if not preserve_bugs:
        fixed = _PERK_FIXED_NAMES.get(perk_id)
        if fixed is not None:
            return fixed
    return entry.name


def perk_display_description(perk_id: PerkId, *, violence_disabled: int = 0, preserve_bugs: bool = False) -> str:
    if perk_id == PerkId.BLOODY_MESS_QUICK_LEARNER and int(violence_disabled) != 0:
        return QUICK_LEARNER_DESCRIPTION
    entry = PERK_BY_ID[perk_id]
    if not preserve_bugs:
        fixed = _PERK_FIXED_DESCRIPTIONS.get(perk_id)
        if fixed is not None:
            return fixed
    return entry.description


def perk_label(perk_id: PerkId, *, violence_disabled: int = 0, preserve_bugs: bool = False) -> str:
    return perk_display_name(perk_id, violence_disabled=violence_disabled, preserve_bugs=preserve_bugs)
