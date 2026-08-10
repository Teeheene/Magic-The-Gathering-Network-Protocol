# MTGNP 58-Card Backend Support Matrix

Baseline audited at `c2151ca`. “COMPLETE” requires a production-path regression, not merely an effect helper branch.

| Card | Base ID | Type | Mechanic | Status | Production Test | Known Limitation |
|---|---|---|---|---|---|---|
| Mountain | mountain | Land | Basic red mana source | NO SPECIAL ENGINE WORK REQUIRED | `test_play_land_mtgnp_spec_behavior` | Generic land/mana-source path |
| Forest | forest | Land | Basic green mana source | NO SPECIAL ENGINE WORK REQUIRED | `test_play_land_mtgnp_spec_behavior` | Generic land/mana-source path |
| Plains | plains | Land | Basic white mana source | NO SPECIAL ENGINE WORK REQUIRED | `test_play_land_mtgnp_spec_behavior` | Generic land/mana-source path |
| Island | island | Land | Basic blue mana source | NO SPECIAL ENGINE WORK REQUIRED | `test_play_land_mtgnp_spec_behavior` | Generic land/mana-source path |
| Swamp | swamp | Land | Basic black mana source | NO SPECIAL ENGINE WORK REQUIRED | `test_play_land_mtgnp_spec_behavior` | Generic land/mana-source path |
| Lightning Bolt | lightning_bolt | Instant | 3 damage to any target | COMPLETE | `test_lightning_bolt_e2e` | — |
| Shock | shock | Instant | 2 damage to any target | COMPLETE | `test_burn_family_normal_cast_resolution` | — |
| Lava Spike | lava_spike | Sorcery | 3 damage to target player | COMPLETE | `test_burn_family_normal_cast_resolution` | — |
| Flame Slash | flame_slash | Sorcery | 4 damage to creature | COMPLETE | `test_flame_slash_e2e` | — |
| Searing Spear | searing_spear | Instant | 3 damage to any target | COMPLETE | `test_burn_family_normal_cast_resolution` | — |
| Skullcrack | skullcrack | Instant | Damage; stop life gain/prevention | PARTIAL | — | Damage branch exists; life-gain flag is not comprehensively enforced; prevention framework absent |
| Rift Bolt | rift_bolt | Sorcery | Normal cast; Suspend | PARTIAL | — | Normal damage branch unproved; Suspend missing |
| Incinerate | incinerate | Instant | Damage; stop regeneration | COMPLETE | `test_terror_and_incinerate_honor_no_regeneration` | — |
| Goblin Guide | goblin_guide | Creature | Haste; attack trigger | COMPLETE | `test_real_trigger_orchestration_goblin_guide` | — |
| Goblin Bushwhacker | goblin_bushwhacker | Creature | Kicker ETB team buff/haste | MISSING | — | Kicker payment/state and conditional ETB effect absent |
| Reckless Wurm | reckless_wurm | Creature | Madness; Trample excluded | MISSING | — | Madness lifecycle absent; MTGNP excludes trample overflow |
| Monastery Swiftspear | monastery_swiftspear | Creature | Haste; Prowess | COMPLETE | `test_real_trigger_orchestration_swiftspear_prowess` | — |
| Counterspell | counterspell | Instant | Counter spell | COMPLETE | `test_counterspell_zone_movement_e2e` | — |
| Cancel | cancel | Instant | Counter spell | COMPLETE | `test_cancel_and_negate_counter_through_cast_stack_path` | — |
| Unsummon | unsummon | Instant | Bounce creature | COMPLETE | `test_unsummon_e2e` | — |
| Ponder | ponder | Sorcery | Top-three reorder/shuffle/draw | PARTIAL | — | Draw exists; MTGNP has no private reorder/optional-shuffle request or response |
| Negate | negate | Instant | Counter noncreature spell | COMPLETE | `test_cancel_and_negate_counter_through_cast_stack_path` | Resolution restriction uses the same authoritative validator |
| Mana Leak | mana_leak | Instant | Counter unless controller pays 3 | PARTIAL | — | Existing server auto-decision is insufficient; MTGNP has no affected-player payment response |
| Merfolk Looter | merfolk_looter | Creature | Tap: draw then discard | MISSING | — | Ability resolution and mandatory discard decision absent |
| Prodigal Sorcerer | prodigal_sorcerer | Creature | Tap: 1 damage | COMPLETE | `test_prodigal_sorcerer_activated_ability_resolution` | — |
| Air Elemental | air_elemental | Creature | Flying | MISSING | — | Flying block restriction absent |
| Phantasmal Bear | phantasmal_bear | Creature | Sacrifice when targeted | COMPLETE | `test_real_trigger_orchestration_phantasmal_bear` | — |
| Giant Growth | giant_growth | Instant | Temporary +3/+3 | COMPLETE | `test_giant_growth_cast_resolution_and_cleanup` | — |
| Rampant Growth | rampant_growth | Sorcery | Basic-land search tapped/shuffle | MISSING | — | MTGNP CAST_SPELL has no library-card selection field |
| Naturalize | naturalize | Instant | Destroy artifact/enchantment | COMPLETE | `test_naturalize_e2e` | — |
| Vines of Vastwood | vines_of_vastwood | Instant | Target restriction; Kicker buff | MISSING | — | Kicker and temporary targeting restriction absent |
| Llanowar Elves | llanowar_elves | Creature | Tap: add green | COMPLETE | `test_elves_are_implicit_green_sources_with_tap_and_sickness_rules` | Mana abilities are implicit under MTGNP |
| Elvish Mystic | elvish_mystic | Creature | Tap: add green | COMPLETE | `test_elves_are_implicit_green_sources_with_tap_and_sickness_rules` | Mana abilities are implicit under MTGNP |
| Grizzly Bears | grizzly_bears | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | `test_combat_damage_result_precedes_state_and_priority` | Generic creature/combat path |
| Leatherback Baloth | leatherback_baloth | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | — | Generic creature path; no card-specific test required |
| Troll Ascetic | troll_ascetic | Creature | Hexproof; regenerate | COMPLETE | `test_troll_hexproof_rejects_opponent_target_but_allows_controller`, `test_troll_regeneration_shield_prevents_lethal_sba_once` | — |
| Wall of Stone | wall_of_stone | Creature | Defender | COMPLETE | `test_defender_and_vigilance_combat` | — |
| Swords to Plowshares | swords_to_plowshares | Instant | Exile creature; controller gains power | COMPLETE | `test_swords_exiles_and_gains_effective_power` | — |
| Path to Exile | path_to_exile | Instant | Exile; optional basic-land search | MISSING | — | MTGNP has no optional-search response or library-card selection field |
| Healing Salve | healing_salve | Instant | Modal gain/prevent damage | MISSING | — | MTGNP CAST_SPELL has no mode/prevention-target field and no modal-choice response |
| Pacifism | pacifism | Enchantment | Aura; cannot attack/block | COMPLETE | `test_pacifism_attaches_and_prevents_attacking`, `test_pacifism_prevents_blocking` | Orphaned Aura cleanup is enforced by SBA |
| White Knight | white_knight | Creature | First strike; protection black | PARTIAL | — | First-strike engine exists; protection absent and no card production proof |
| Serra Angel | serra_angel | Creature | Flying; Vigilance | PARTIAL | `test_defender_and_vigilance_combat` | Vigilance proved; Flying restriction absent |
| Savannah Lions | savannah_lions | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | `test_combat_damage_result_precedes_state_and_priority` | Generic creature/combat path |
| Mother of Runes | mother_of_runes | Creature | Tap: temporary protection choice | MISSING | — | MTGNP ACTIVATE_ABILITY has no chosen-color field |
| Dark Ritual | dark_ritual | Instant | Add BBB | COMPLETE | `test_dark_ritual_mana_is_spendable_by_normal_cast_path` | MTGNP does not specify intermediate mana-pool expiry |
| Terror | terror | Instant | Restricted destroy; no regeneration | COMPLETE | `test_terror_and_doom_blade_cast_restrictions_and_resolution`, `test_terror_and_incinerate_honor_no_regeneration` | — |
| Doom Blade | doom_blade | Instant | Destroy nonblack creature | COMPLETE | `test_terror_and_doom_blade_cast_restrictions_and_resolution` | — |
| Raise Dead | raise_dead | Sorcery | Creature graveyard to hand | COMPLETE | `test_raise_dead_cast_resolution` | — |
| Mind Rot | mind_rot | Sorcery | Target player discards two | MISSING | — | MTGNP DISCARD is Cleanup-only; no in-game hidden-card choice request exists |
| Gray Merchant of Asphodel | gray_merchant | Creature | Devotion drain ETB | COMPLETE | `test_real_trigger_orchestration_gray_merchant` | — |
| Gravedigger | gravedigger | Creature | Target creature return ETB | COMPLETE | `test_gravedigger_trigger_choice_persistence` | — |
| Royal Assassin | royal_assassin | Creature | Tap: destroy tapped creature | COMPLETE | `test_repeatable_artifact_and_assassin_abilities_use_full_activation_path` | — |
| Black Knight | black_knight | Creature | First strike; protection white | PARTIAL | — | First-strike engine exists; protection absent and no card production proof |
| Sol Ring | sol_ring | Artifact | Tap: add CC | COMPLETE | `test_sol_ring_produces_two_colorless_for_generic_payment` | Mana ability is implicit under MTGNP |
| Ornithopter | ornithopter | Artifact Creature | Flying | MISSING | — | Flying block restriction absent |
| Millstone | millstone | Artifact | Pay 2, tap: mill 2 | COMPLETE | `test_repeatable_artifact_and_assassin_abilities_use_full_activation_path` | — |
| Rod of Ruin | rod_of_ruin | Artifact | Pay 3, tap: 1 damage | COMPLETE | `test_event_emission_for_activated_abilities_phantasmal_bear` | Full activation path covered |

## Baseline totals

- COMPLETE: 31
- PARTIAL: 7
- MISSING: 11
- NO SPECIAL ENGINE WORK REQUIRED: 9
- Total: 58

## Protocol decision gaps

The fixed 25-PDU MTGNP protocol has no compatible wire representation for these required player choices:

- Merfolk Looter: which card to discard after drawing outside Cleanup.
- Mother of Runes: which color to choose.
- Rampant Growth: which basic land to select from the controller's library.
- Path to Exile: whether to search and which basic land to select.
- Mind Rot: which two hidden cards the targeted player discards outside Cleanup.
- Ponder: private top-three ordering and optional shuffle.
- Mana Leak: whether the targeted spell's controller pays three mana.
- Healing Salve: mode selection and the prevention target.

Per the completion plan, no new PDU or overloaded incompatible field was invented. Passes D–F and the final keyword audit are paused at this protocol boundary.
