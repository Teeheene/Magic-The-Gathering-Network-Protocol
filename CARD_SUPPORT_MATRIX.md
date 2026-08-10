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
| Skullcrack | skullcrack | Instant | Damage; stop life gain/prevention | COMPLETE | `test_skullcrack_blocks_swords_life_gain`, `test_skullcrack_sets_both_turn_restrictions_and_cleanup` | — |
| Rift Bolt | rift_bolt | Sorcery | Normal cast; Suspend | PARTIAL | `test_burn_family_normal_cast_resolution` | Normal cast works; Suspend is not wire-representable because CAST_SPELL has no cast-vs-suspend discriminator or time-counter lifecycle |
| Incinerate | incinerate | Instant | Damage; stop regeneration | COMPLETE | `test_terror_and_incinerate_honor_no_regeneration` | — |
| Goblin Guide | goblin_guide | Creature | Haste; attack trigger | COMPLETE | `test_real_trigger_orchestration_goblin_guide` | — |
| Goblin Bushwhacker | goblin_bushwhacker | Creature | Kicker ETB team buff/haste | COMPLETE | `test_bushwhacker_exact_normal_and_kicked_payments_and_cleanup`, `test_bushwhacker_rejects_intermediate_extra_and_insufficient_payment` | Kicker is inferred from exact documented mana_payment; no PDU field added |
| Reckless Wurm | reckless_wurm | Creature | Madness; Trample excluded | PARTIAL | `test_reckless_wurm_normal_cast_enters_as_creature` | Normal cast works; Madness has no discard-triggered offer/acceptance or alternate-cast encoding; MTGNP excludes trample overflow |
| Monastery Swiftspear | monastery_swiftspear | Creature | Haste; Prowess | COMPLETE | `test_real_trigger_orchestration_swiftspear_prowess` | — |
| Counterspell | counterspell | Instant | Counter spell | COMPLETE | `test_counterspell_zone_movement_e2e` | — |
| Cancel | cancel | Instant | Counter spell | COMPLETE | `test_cancel_and_negate_counter_through_cast_stack_path` | — |
| Unsummon | unsummon | Instant | Bounce creature | COMPLETE | `test_unsummon_e2e` | — |
| Ponder | ponder | Sorcery | Top-three reorder/shuffle/draw | COMPLETE | `test_ponder_orders_privately_then_optionally_shuffles_and_draws`, `test_ponder_short_and_empty_libraries` | Chained private ORDER_CARDS and YES_NO choices |
| Negate | negate | Instant | Counter noncreature spell | COMPLETE | `test_cancel_and_negate_counter_through_cast_stack_path` | Resolution restriction uses the same authoritative validator |
| Mana Leak | mana_leak | Instant | Counter unless controller pays 3 | COMPLETE | `test_mana_leak_target_controller_decides_and_exact_payment_is_authoritative` | Target spell controller receives authoritative PAY_MANA choice |
| Merfolk Looter | merfolk_looter | Creature | Tap: draw then discard | COMPLETE | `test_merfolk_looter_draws_then_privately_selects_discard` | Private discard uses CARD_CHOICE_REQUEST |
| Prodigal Sorcerer | prodigal_sorcerer | Creature | Tap: 1 damage | COMPLETE | `test_prodigal_sorcerer_activated_ability_resolution` | — |
| Air Elemental | air_elemental | Creature | Flying | COMPLETE | `test_flying_reach_and_protection_legality` | — |
| Phantasmal Bear | phantasmal_bear | Creature | Sacrifice when targeted | COMPLETE | `test_real_trigger_orchestration_phantasmal_bear` | — |
| Giant Growth | giant_growth | Instant | Temporary +3/+3 | COMPLETE | `test_giant_growth_cast_resolution_and_cleanup` | — |
| Rampant Growth | rampant_growth | Sorcery | Basic-land search tapped/shuffle | COMPLETE | `test_rampant_growth_selects_basic_tapped_and_shuffles` | Private search uses CARD_CHOICE_REQUEST |
| Naturalize | naturalize | Instant | Destroy artifact/enchantment | COMPLETE | `test_naturalize_e2e` | — |
| Vines of Vastwood | vines_of_vastwood | Instant | Target restriction; Kicker buff | COMPLETE | `test_vines_normal_kicked_invalid_insufficient_and_cleanup` | Kicker is inferred from exact documented mana_payment; no PDU field added |
| Llanowar Elves | llanowar_elves | Creature | Tap: add green | COMPLETE | `test_elves_are_implicit_green_sources_with_tap_and_sickness_rules` | Mana abilities are implicit under MTGNP |
| Elvish Mystic | elvish_mystic | Creature | Tap: add green | COMPLETE | `test_elves_are_implicit_green_sources_with_tap_and_sickness_rules` | Mana abilities are implicit under MTGNP |
| Grizzly Bears | grizzly_bears | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | `test_combat_damage_result_precedes_state_and_priority` | Generic creature/combat path |
| Leatherback Baloth | leatherback_baloth | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | — | Generic creature path; no card-specific test required |
| Troll Ascetic | troll_ascetic | Creature | Hexproof; regenerate | COMPLETE | `test_troll_hexproof_rejects_opponent_target_but_allows_controller`, `test_troll_regeneration_shield_prevents_lethal_sba_once` | — |
| Wall of Stone | wall_of_stone | Creature | Defender | COMPLETE | `test_defender_and_vigilance_combat` | — |
| Swords to Plowshares | swords_to_plowshares | Instant | Exile creature; controller gains power | COMPLETE | `test_swords_exiles_and_gains_effective_power` | — |
| Path to Exile | path_to_exile | Instant | Exile; optional basic-land search | COMPLETE | `test_path_exiles_then_affected_controller_may_search` | Chained private YES_NO and SELECT_CARDS choices |
| Healing Salve | healing_salve | Instant | Modal gain/prevent damage | COMPLETE | `test_healing_salve_modes_and_prevention_consumption_cleanup`, `test_healing_salve_cast_requires_known_mode_and_mode_legal_target` | CAST_SPELL mode is mandatory and enum-validated for this card |
| Pacifism | pacifism | Enchantment | Aura; cannot attack/block | COMPLETE | `test_pacifism_attaches_and_prevents_attacking`, `test_pacifism_prevents_blocking` | Orphaned Aura cleanup is enforced by SBA |
| White Knight | white_knight | Creature | First strike; protection black | COMPLETE | `test_flying_reach_and_protection_legality`, `test_first_and_double_strike_damage_windows` | — |
| Serra Angel | serra_angel | Creature | Flying; Vigilance | COMPLETE | `test_flying_reach_and_protection_legality`, `test_defender_and_vigilance_combat` | — |
| Savannah Lions | savannah_lions | Creature | Vanilla creature | NO SPECIAL ENGINE WORK REQUIRED | `test_combat_damage_result_precedes_state_and_priority` | Generic creature/combat path |
| Mother of Runes | mother_of_runes | Creature | Tap: temporary protection choice | COMPLETE | `test_mother_color_choice_and_cleanup` | COLOR choice is validated against the fixed five-color enum |
| Dark Ritual | dark_ritual | Instant | Add BBB | COMPLETE | `test_dark_ritual_mana_is_spendable_by_normal_cast_path` | MTGNP does not specify intermediate mana-pool expiry |
| Terror | terror | Instant | Restricted destroy; no regeneration | COMPLETE | `test_terror_and_doom_blade_cast_restrictions_and_resolution`, `test_terror_and_incinerate_honor_no_regeneration` | — |
| Doom Blade | doom_blade | Instant | Destroy nonblack creature | COMPLETE | `test_terror_and_doom_blade_cast_restrictions_and_resolution` | — |
| Raise Dead | raise_dead | Sorcery | Creature graveyard to hand | COMPLETE | `test_raise_dead_cast_resolution` | — |
| Mind Rot | mind_rot | Sorcery | Target player discards two | COMPLETE | `test_mind_rot_target_selects_exact_available_count` | Target player receives private SELECT_CARDS choice |
| Gray Merchant of Asphodel | gray_merchant | Creature | Devotion drain ETB | COMPLETE | `test_real_trigger_orchestration_gray_merchant` | — |
| Gravedigger | gravedigger | Creature | Target creature return ETB | COMPLETE | `test_gravedigger_trigger_choice_persistence` | — |
| Royal Assassin | royal_assassin | Creature | Tap: destroy tapped creature | COMPLETE | `test_repeatable_artifact_and_assassin_abilities_use_full_activation_path` | — |
| Black Knight | black_knight | Creature | First strike; protection white | COMPLETE | `test_flying_reach_and_protection_legality`, `test_first_and_double_strike_damage_windows` | — |
| Sol Ring | sol_ring | Artifact | Tap: add CC | COMPLETE | `test_sol_ring_produces_two_colorless_for_generic_payment` | Mana ability is implicit under MTGNP |
| Ornithopter | ornithopter | Artifact Creature | Flying | COMPLETE | `test_flying_reach_and_protection_legality` | — |
| Millstone | millstone | Artifact | Pay 2, tap: mill 2 | COMPLETE | `test_repeatable_artifact_and_assassin_abilities_use_full_activation_path` | — |
| Rod of Ruin | rod_of_ruin | Artifact | Pay 3, tap: 1 damage | COMPLETE | `test_event_emission_for_activated_abilities_phantasmal_bear` | Full activation path covered |

## Current totals

- COMPLETE: 48
- PARTIAL: 2
- MISSING: 0
- NO SPECIAL ENGINE WORK REQUIRED: 8
- Total: 58

## Protocol decision gaps

The fixed 25-PDU MTGNP protocol has no compatible wire representation for these required player choices. CAST_SPELL (`card_id`, `targets`, `mana_payment`), ACTIVATE_ABILITY (`source_id`, `ability_index`, `targets`, `cost_payment`), TRIGGER_CHOICE / TRIGGER_CHOICE_RESPONSE, TRIGGER_ORDER / TRIGGER_ORDER_RESPONSE, and Cleanup-only DISCARD were inspected; none may be overloaded with undocumented meanings.

- Merfolk Looter: ACTIVATE_ABILITY can identify the source/targets/cost, but cannot encode which newly hidden hand card to discard; DISCARD is explicitly Cleanup-only and trigger responses apply only to triggered abilities.
- Mother of Runes: ACTIVATE_ABILITY can target the creature, but has no chosen-color field; targets/cost_payment and trigger responses cannot legally encode a color.
- Rampant Growth: CAST_SPELL can identify the spell/payment, but targets cannot expose or select a private library card and no search-choice response exists.
- Path to Exile: CAST_SPELL targets the creature, but no PDU carries the affected controller's optional-search decision or private basic-land selection.
- Mind Rot: CAST_SPELL targets the player, but DISCARD is Cleanup-only and no request/response lets that player select two hidden hand cards during resolution.
- Ponder: CAST_SPELL has no private top-three ordering or optional-shuffle response; targets and trigger responses are not legal encodings.
- Mana Leak: CAST_SPELL targets the stack item, but no PDU requests or carries the affected spell controller's pay-three decision; mana_payment belongs to the caster's spell declaration.
- Healing Salve: CAST_SPELL has neither a mode field nor a prevention-target choice; targets cannot distinguish both catalog modes and trigger responses do not apply.

Other RFC representation gaps:

- Rift Bolt Suspend: CAST_SPELL has no action discriminator for casting versus suspending and the protocol defines no exile/time-counter lifecycle messages. Normal casting is supported.
- Reckless Wurm Madness: no PDU offers the discarded card to its owner, records acceptance, or legally declares the alternate Madness cast at the required time. Normal casting is supported; trample overflow remains excluded by MTGNP 1.0.

Kicker is representable for the two catalog cards using exact documented mana_payment values: Goblin Bushwhacker accepts only `{R:1}` or `{R:2, Generic:1}`; Vines of Vastwood accepts only `{G:1}` or `{G:2}`. Kicked status is authoritative internal stack state and is never added to a PDU.
