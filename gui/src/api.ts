import { Build, GameType, Item, PlayerData, StatusState, SlotType, BackendItem } from './types';

function getTypeForCsv(csv: string): SlotType {
    const lookup: Record<string, SlotType> = {
        'er_weapons.csv': SlotType.WEAPON_R,
        'er_armors.csv': SlotType.ARMOR_HEAD,
        'er_accessories.csv': SlotType.TALISMAN,
        'er_spells.csv': SlotType.SPELL,
        'er_items.csv': SlotType.QUICK_ITEM,
        'ds3_weapons.csv': SlotType.WEAPON_R,
        'ds3_armors.csv': SlotType.ARMOR_HEAD,
        'ds3_rings.csv': SlotType.RING,
        'ds3_spells.csv': SlotType.SPELL,
        'ds3_items.csv': SlotType.QUICK_ITEM,
    };
    return lookup[csv] || SlotType.WEAPON_R;
}

function getTypeForBackendKey(beKey: string): SlotType {
    const key = beKey.toLowerCase();
    if (key.includes('head') || key.includes('helmet')) return SlotType.ARMOR_HEAD;
    if (key.includes('chest') || key.includes('armor')) return SlotType.ARMOR_CHEST;
    if (key.includes('hand') || key.includes('gauntlet')) return SlotType.ARMOR_HANDS;
    if (key.includes('leg') || key.includes('leggings')) return SlotType.ARMOR_LEGS;
    if (key.includes('ring')) return SlotType.RING;
    if (key.includes('accessory') || key.includes('talisman')) return SlotType.TALISMAN;
    if (key.includes('arrow') || key.includes('ammo_1')) return SlotType.AMMO_ARROW;
    if (key.includes('bolt') || key.includes('ammo_2')) return SlotType.AMMO_BOLT;
    if (key.includes('magic') || key.includes('spell')) return SlotType.SPELL;
    if (key.includes('quick_item') || key.includes('quick_')) return SlotType.QUICK_ITEM;
    if (key.includes('covenant')) return SlotType.COVENANT;
    return SlotType.WEAPON_R;
}

const API_BASE = import.meta.env.PROD ? '' : 'http://127.0.0.1:8000';

type BuildEquipmentEntry = number | { id: number; ash_of_war?: number; count?: number };
const EMPTY_EQUIP_ID = -1; // backend interprets -1/0xFFFFFFFF/0x0FFFFFFF as "unequip"
const DEFAULT_AMMO_COUNT = 99;

function buildFrontendToBackendSlotMapping(game: GameType): Record<string, string> {
    const slotMapping: Record<string, string> = {
        weapon_r_1: 'primary_right_wep',
        weapon_r_2: 'secondary_right_wep',
        weapon_r_3: 'tertiary_right_wep',
        weapon_l_1: 'primary_left_wep',
        weapon_l_2: 'secondary_left_wep',
        weapon_l_3: 'tertiary_left_wep',
        head: 'helmet',
        chest: 'armor',
        hands: 'gauntlet',
        legs: 'leggings',
    };

    if (game === 'DARK_SOULS_3') {
        slotMapping.ring_1 = 'ring_1';
        slotMapping.ring_2 = 'ring_2';
        slotMapping.ring_3 = 'ring_3';
        slotMapping.ring_4 = 'ring_4';
        slotMapping.covenant = 'covenant';
        slotMapping.ammo_arrow_1 = 'primary_arrow';
        slotMapping.ammo_arrow_2 = 'secondary_arrow';
        slotMapping.ammo_bolt_1 = 'primary_bolt';
        slotMapping.ammo_bolt_2 = 'secondary_bolt';
    } else {
        slotMapping.talisman_1 = 'accessory_1';
        slotMapping.talisman_2 = 'accessory_2';
        slotMapping.talisman_3 = 'accessory_3';
        slotMapping.talisman_4 = 'accessory_4';
        slotMapping.ammo_1_1 = 'primary_arrow';
        slotMapping.ammo_1_2 = 'secondary_arrow';
        slotMapping.ammo_2_1 = 'primary_bolt';
        slotMapping.ammo_2_2 = 'secondary_bolt';
    }

    for (let i = 1; i <= 10; i++) {
        const fePrefix = i <= 5 ? 'quick_1' : 'quick_2';
        slotMapping[`${fePrefix}_${i}`] = `quick_item_${i}`;
    }
    for (let i = 0; i < 14; i++) {
        slotMapping[`spell_${i + 1}`] = `magic_slot_${i}`;
    }
    return slotMapping;
}

function isWeaponBackendSlot(beKey: string): boolean {
    return beKey.endsWith('_wep');
}

// Mapping helpers
export function toFrontendGame(backendKey: string): GameType | null {
    if (backendKey === 'eldenring') return 'ELDEN_RING';
    if (backendKey === 'ds3') return 'DARK_SOULS_3';
    return null;
}

export function toBackendGame(frontendKey: GameType | string): string {
    if (frontendKey === 'ELDEN_RING') return 'eldenring';
    if (frontendKey === 'DARK_SOULS_3') return 'ds3';
    return (frontendKey as string).toLowerCase();
}

export async function detectGame(): Promise<GameType | null> {
    try {
        const res = await fetch(`${API_BASE}/system/detected_game`);
        const data = await res.json();
        return data.game ? toFrontendGame(data.game) : null;
    } catch (e) {
        console.warn('Failed to detect game', e);
        return null;
    }
}

export async function browseSaveFile(defaultName: string = "build"): Promise<string | null> {
    try {
        const res = await fetch(`${API_BASE}/system/browse_save_file?default_name=${encodeURIComponent(defaultName)}`);
        const data = await res.json();
        return data.path || null;
    } catch (e) {
        console.warn('Failed to browse save file', e);
        return null;
    }
}

interface BackendPlayer {
    player_num: number;
    name: string;
    stats?: {
        vigor?: number;
        mind?: number;
        attunement?: number;
        endurance?: number;
        vitality?: number;
        strength?: number;
        dexterity?: number;
        intelligence?: number;
        faith?: number;
        arcane?: number;
        luck?: number;
        level?: number;
        runes?: number;
        souls?: number;
        scadutree_blessing?: number;
        revered_spirit_ash_blessing?: number;
        hp?: number;
        max_hp?: number;
        steamId?: string;
    };
    equipment?: {
        covenant?: { name: string };
    } & Record<string, BackendItem>;
}

export async function getPlayers(game: GameType): Promise<PlayerData[]> {
    try {
        const gameKey = toBackendGame(game);
        const res = await fetch(`${API_BASE}/${gameKey}/players`);
        const data = await res.json();

        return (data as BackendPlayer[]).map((p) => {
            // Transform backend response to match frontend PlayerData structure
            const stats = p.stats || {};
            const attributes = {
                Vigor: stats.vigor || 0,
                Mind: stats.mind || 0,
                Attunement: stats.attunement || 0,
                Endurance: stats.endurance || 0,
                Vitality: stats.vitality || 0,
                Strength: stats.strength || 0,
                Dexterity: stats.dexterity || 0,
                Intelligence: stats.intelligence || 0,
                Faith: stats.faith || 0,
                Arcane: stats.arcane || 0,
                Luck: stats.luck || 0,
            };

            const status: StatusState = {
                level: stats.level || 0,
                secondary: stats.runes || stats.souls || 0,
                journey: 1,
                covenant: p.equipment?.covenant?.name || '-',
                attributes: attributes,
                scadutreeBlessing: stats.scadutree_blessing,
                reveredSpiritAsh: stats.revered_spirit_ash_blessing,
                hp: stats.hp,
                maxHp: stats.max_hp,
                steamId: stats.steamId
            };

            const slots: Record<string, Item | null> = {};
            if (p.equipment) {
                const equipment = p.equipment as Record<string, BackendItem>;
                // Helper to map backend slot to frontend slot
                const mapSlot = (beKey: string, feKey: string) => {
                    const itemData = equipment[beKey];
                    // Filter out invalid items and Unarmed (treat as empty). Keep "Unknown" items so
                    // builds can round-trip without unintentionally clearing real equipped items.
                    if (itemData && itemData.id > 0) {
                        const nameLower = itemData.name.toLowerCase();
                        if (nameLower.includes('unarmed')) {
                            return;
                        }

                        let upgrade: number | undefined = undefined;
                        if (feKey.includes('weapon')) {
                            const idNum = itemData.id;
                            if (!isNaN(idNum) && idNum > 0) {
                                // Simple heuristic for upgrade level: last 2 digits
                                // Works for most ER and DS3 weapons (0-25 or 0-10)
                                const rawUpgrade = idNum % 100;
                                if (rawUpgrade > 0 && rawUpgrade <= 25) {
                                    upgrade = rawUpgrade;
                                }
                            }
                        }

                        const displayName = upgrade ? `${itemData.name} +${upgrade}` : itemData.name;
                        const itemType = getTypeForBackendKey(beKey);
                        const showImage = itemData.icon_id && Number(itemData.icon_id) !== 0 && !itemData.name.toLowerCase().includes('unarmed') && !itemData.name.toLowerCase().includes('unknown');

                        slots[feKey] = {
                            id: itemData.id.toString(),
                            name: displayName,
                            image: showImage ? `${API_BASE}/${gameKey}/icons/${itemData.icon_id}` : '',
                            type: itemType,
                            description: '',
                            weight: 0,
                            upgrade,
                            maxUpgrade: itemData.max_upgrade,
                            gemId: itemData.gem_id,
                            count: itemData.count
                        };
                    }
                };

                mapSlot("primary_right_wep", "weapon_r_1");
                mapSlot("secondary_right_wep", "weapon_r_2");
                mapSlot("tertiary_right_wep", "weapon_r_3");
                mapSlot("primary_left_wep", "weapon_l_1");
                mapSlot("secondary_left_wep", "weapon_l_2");
                mapSlot("tertiary_left_wep", "weapon_l_3");
                mapSlot("helmet", "head");
                mapSlot("armor", "chest");
                mapSlot("gauntlet", "hands");
                mapSlot("leggings", "legs");

                // DS3 Rings / ER Talismans
                if (game === 'DARK_SOULS_3') {
                    mapSlot("ring_1", "ring_1");
                    mapSlot("ring_2", "ring_2");
                    mapSlot("ring_3", "ring_3");
                    mapSlot("ring_4", "ring_4");
                    mapSlot("covenant", "covenant");
                } else {
                    mapSlot("accessory_1", "talisman_1");
                    mapSlot("accessory_2", "talisman_2");
                    mapSlot("accessory_3", "talisman_3");
                    mapSlot("accessory_4", "talisman_4");
                }

                // Quick Items
                for (let i = 1; i <= 10; i++) {
                    const fePrefix = i <= 5 ? 'quick_1' : 'quick_2';
                    mapSlot(`quick_item_${i}`, `${fePrefix}_${i}`);
                }

                // Spells
                for (let i = 0; i < 14; i++) {
                    mapSlot(`magic_slot_${i}`, `spell_${i + 1}`);
                }

                // Ammo
                if (game === 'ELDEN_RING') {
                    // ER: primary/secondary arrow -> ammo_1_1 / ammo_1_2 implies arrow slots?
                    // Frontend EquipmentGrid for ER:
                    //   {[1, 2].map(i => renderSlot(`ammo_1_${i}`, SlotType.AMMO_ARROW))}
                    //   {[1, 2].map(i => renderSlot(`ammo_2_${i}`, SlotType.AMMO_ARROW))}
                    // Assuming ammo_1 is Arrows, ammo_2 is Bolts based on typical UI?
                    // But backend just has primary/secondary arrow/bolt.
                    // Let's assume ammo_1_x are arrows, ammo_2_x are bolts.
                    mapSlot("primary_arrow", "ammo_1_1");
                    mapSlot("secondary_arrow", "ammo_1_2");
                    mapSlot("primary_bolt", "ammo_2_1");
                    mapSlot("secondary_bolt", "ammo_2_2");
                } else {
                    // DS3: arrow_1, arrow_2, bolt_1, bolt_2
                    // Frontend: ammo_arrow_1, ammo_arrow_2, ammo_bolt_1, ammo_bolt_2
                    mapSlot("primary_arrow", "ammo_arrow_1");
                    mapSlot("secondary_arrow", "ammo_arrow_2");
                    mapSlot("primary_bolt", "ammo_bolt_1");
                    mapSlot("secondary_bolt", "ammo_bolt_2");
                }

                // DS3 Covenant handled above if present, also handled here if mapSlot called twice is fine (it overwrites)
            }

            const build: Build = {
                id: `player-${p.player_num}`,
                name: p.name,
                slots: slots
            };

            return {
                name: p.name,
                status,
                build,
                isLocal: p.player_num === 0,
                date: new Date().toISOString()
            };
        });
    } catch (e) {
        console.error('Failed to list players', e);
        return [];
    }
}


export async function getPlayer(game: GameType, playerNum: number): Promise<PlayerData | null> {
    // Legacy support or specific single update if needed, effectively duplicate of mapping logic above
    // keeping simplified for now or could just reuse list logic if backend supports it efficiently
    try {
        const gameKey = toBackendGame(game);
        const res = await fetch(`${API_BASE}/${gameKey}/players/${playerNum}`);
        if (!res.ok) return null;
        const data = await res.json();

        const stats = data.stats || {};
        const attributes = {
            Vigor: stats.vigor || 0,
            Mind: stats.mind || 0,
            Attunement: stats.attunement || 0,
            Endurance: stats.endurance || 0,
            Vitality: stats.vitality || 0,
            Strength: stats.strength || 0,
            Dexterity: stats.dexterity || 0,
            Intelligence: stats.intelligence || 0,
            Faith: stats.faith || 0,
            Arcane: stats.arcane || 0,
            Luck: stats.luck || 0,
        };

        const status: StatusState = {
            level: stats.level || 0,
            secondary: stats.runes || stats.souls || 0,
            journey: 1,
            covenant: data.equipment?.covenant ? 'Equipped' : '-',
            attributes: attributes,
            scadutreeBlessing: stats.scadutree_blessing,
            reveredSpiritAsh: stats.revered_spirit_ash_blessing,
            hp: stats.hp,
            maxHp: stats.max_hp,
            steamId: stats.steamId
        };

        const build: Build = {
            id: `player-${playerNum}`,
            name: data.name,
            slots: {}
        };

        return {
            name: data.name,
            status,
            build,
            isLocal: playerNum === 0,
            date: new Date().toISOString()
        };

    } catch (e) {
        console.error(`Failed to get player ${playerNum}`, e);
        return null;
    }
}

export async function writeStats(game: GameType, playerNum: number, status: StatusState) {
    const gameKey = toBackendGame(game);
    const payload = {
        level: status.level,
        runes: status.secondary,
        souls: status.secondary,
        ...status.attributes,
        shadow_of_erdtree: {
            scadutree_blessing: status.scadutreeBlessing,
            revered_spirit_ash_blessing: status.reveredSpiritAsh
        }
    };

    await fetch(`${API_BASE}/${gameKey}/players/${playerNum}/stats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stats: payload })
    });
}

// Actions
export async function quitToMenu(game: GameType) {
    await fetch(`${API_BASE}/${toBackendGame(game)}/actions/quit_to_menu`, { method: 'POST' });
}

export async function fixInfiniteLoading(game: GameType) {
    await fetch(`${API_BASE}/${toBackendGame(game)}/actions/loading_fix/start`, { method: 'POST' });
}

export async function toggleFogWall(game: GameType) {
    await fetch(`${API_BASE}/${toBackendGame(game)}/actions/fogwall`, { method: 'POST' });
}

export async function toggleCheat(game: GameType, cheat: string, enable: boolean) {
    const action = enable ? 'enable' : 'disable';
    // Backend names match frontend keys mostly, but let's map them just in case or rely on direct mapping if keys match.
    // Frontend keys: 'noDead', 'noHit', 'noWeight', 'noStamina', 'noFP', 'noGoods', 'noArrow'
    // Backend names: "NoDead", "NoDamage", "NoStaminaConsumption", "NoFPConsumption", "NoGoodsConsume", "NoArrowConsume", "NoWeight", "NoHit"

    const map: Record<string, string> = {
        'noDead': 'NoDead',
        'noDamage': 'NoDamage',
        'noStamina': 'NoStaminaConsumption',
        'noFP': 'NoFPConsumption',
        'noGoods': 'NoGoodsConsume',
        'noArrow': 'NoArrowConsume',
        'noWeight': 'NoWeight',
        'noHit': 'NoHit'
    };

    const backendName = map[cheat];
    if (!backendName) {
        console.error(`Unknown cheat key: ${cheat}`);
        return;
    }

    await fetch(`${API_BASE}/${toBackendGame(game)}/cheats/${backendName}/${action}`, { method: 'POST' });
}

export async function searchItems(game: GameType, query: string, csv?: string, limit?: number): Promise<Item[]> {
    try {
        const gameKey = toBackendGame(game);
        let url = `${API_BASE}/${gameKey}/items/search?q=${encodeURIComponent(query)}`;
        if (csv) {
            url += `&csv=${encodeURIComponent(csv)}`;
        }
        if (limit) {
            url += `&limit=${limit}`;
        }

        const res = await fetch(url);
        if (!res.ok) return [];
        const data = await res.json();

        return (data.items || []).map((d: BackendItem) => ({
            id: d.id.toString(),
            name: d.name,
            icon_id: d.icon_id?.toString() || '',
            image: (d.icon_id && Number(d.icon_id) !== 0) ? `${API_BASE}/${gameKey}/icons/${d.icon_id}` : '',
            type: getTypeForCsv(csv || ''), // Use helper here
            description: '',
            weight: 0,
            maxUpgrade: d.max_upgrade
        }));
    } catch (e) {
        console.error("Search error", e);
        return [];
    }
}

export async function listBuilds(): Promise<string[]> {
    try {
        const res = await fetch(`${API_BASE}/builds`);
        if (!res.ok) return [];
        return await res.json();
    } catch (e) {
        console.error("Failed to list builds", e);
        return [];
    }
}

export async function saveBuild(name: string, data: unknown, path?: string): Promise<{ status: string, path?: string } | false> {
    try {
        const body: Record<string, unknown> = { name, data };
        if (path) body.path = path;

        const res = await fetch(`${API_BASE}/builds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) return false;
        return await res.json();
    } catch (e) {
        console.error("Failed to save build", e);
        return false;
    }
}

export async function loadBuild(name: string): Promise<unknown> {
    try {
        const res = await fetch(`${API_BASE}/builds/${encodeURIComponent(name)}`);
        if (!res.ok) return null;
        return await res.json();
    } catch (e) {
        console.error("Failed to load build", e);
        return null;
    }
}

export async function deleteBuild(name: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_BASE}/builds/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        return res.ok;
    } catch (e) {
        console.error("Failed to delete build", e);
        return false;
    }
}

export async function writeBuild(game: GameType, playerNum: number, slots: Record<string, Item | null>, status?: StatusState) {
    const gameKey = toBackendGame(game);
    const equipment: Record<string, BuildEquipmentEntry> = {};
    const slotMapping = buildFrontendToBackendSlotMapping(game);

    for (const [feKey, beKey] of Object.entries(slotMapping)) {
        const hasSlotKey = Object.prototype.hasOwnProperty.call(slots, feKey);
        const item = slots[feKey];
        if (item && item.id) {
            let finalId = parseInt(item.id);

            // Re-calculate ID if upgrade is present to ensure we use Modified ID
            if (item.maxUpgrade && item.maxUpgrade > 0 && typeof item.upgrade === 'number') {
                if (game === 'ELDEN_RING') {
                    // Heuristic: Base ID is floored to 100.
                    const base = finalId - (finalId % 100);
                    finalId = base + item.upgrade;
                } else if (game === 'DARK_SOULS_3') {
                    // Heuristic: Base ID is floored to 10.
                    const base = finalId - (finalId % 10);
                    finalId = base + item.upgrade;
                }
            }

            // Quantity handling:
            // - Ammo defaults to 99 if not specified (expected behavior).
            // - Quick items: ONLY include count if explicitly set by user/build file.
            //   This avoids unintentionally reducing flasks/pots from current amount -> 1.
            const finalCount = feKey.startsWith('ammo')
                ? (item.count ?? DEFAULT_AMMO_COUNT)
                : (feKey.startsWith('quick') ? item.count : undefined);

            if ((isWeaponBackendSlot(beKey) && item.gemId) || finalCount !== undefined) {
                const entry: { id: number; ash_of_war?: number; count?: number } = {
                    id: finalId,
                    ash_of_war: isWeaponBackendSlot(beKey) ? item.gemId : undefined,
                    count: finalCount
                };
                // Clean up undefined keys if needed for explicit clean obj
                if (!entry.ash_of_war) delete entry.ash_of_war;
                if (entry.count === undefined) delete entry.count;

                equipment[beKey] = entry;
            } else {
                equipment[beKey] = finalId;
            }
        } else if (hasSlotKey) {
            // Only send explicit empties for slots that are present in the build state.
            // This makes "Clear Slot" work, but avoids mass-unequipping every slot on Apply.
            equipment[beKey] = EMPTY_EQUIP_ID;
        }
    }

    const payload: Record<string, unknown> = { equipment };
    if (status) {
        const stats: Record<string, number | null> = {};
        const attrs = status.attributes || {};

        // Helper to ensure we don't send NaN to backend
        const num = (v: unknown) => (typeof v === 'number' && !isNaN(v)) ? v : 0;

        if (attrs.Vigor !== undefined) stats.vigor = num(attrs.Vigor);
        if (attrs.Mind !== undefined) stats.mind = num(attrs.Mind);
        if (attrs.Endurance !== undefined) stats.endurance = num(attrs.Endurance);
        if (attrs.Strength !== undefined) stats.strength = num(attrs.Strength);
        if (attrs.Dexterity !== undefined) stats.dexterity = num(attrs.Dexterity);
        if (attrs.Intelligence !== undefined) stats.intelligence = num(attrs.Intelligence);
        if (attrs.Faith !== undefined) stats.faith = num(attrs.Faith);
        if (attrs.Arcane !== undefined) stats.arcane = num(attrs.Arcane);
        if (attrs.Vitality !== undefined) stats.vitality = num(attrs.Vitality);
        if (attrs.Attunement !== undefined) stats.attunement = num(attrs.Attunement);
        if (attrs.Luck !== undefined) stats.luck = num(attrs.Luck);

        if (status.level !== undefined) stats.level = num(status.level);
        if (status.secondary !== undefined) {
            stats.runes = num(status.secondary);
            stats.souls = num(status.secondary);
        }

        payload.stats = stats;

        if (game === 'ELDEN_RING' && (status.scadutreeBlessing !== undefined || status.reveredSpiritAsh !== undefined)) {
            payload.shadow_of_erdtree = {
                scadutree_blessing: num(status.scadutreeBlessing),
                revered_spirit_ash_blessing: num(status.reveredSpiritAsh)
            };
        }
    }

    console.log("Applying build payload:", JSON.stringify(payload, null, 2));

    const res = await fetch(`${API_BASE}/${gameKey}/players/${playerNum}/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.error("Build Application Failed", err);
        throw new Error(`Server returned ${res.status}: ${JSON.stringify(err)}`);
    }
}

export async function inspectBuild(game: GameType, equipment: Record<string, unknown>): Promise<Record<string, BackendItem | null>> {
    const gameKey = toBackendGame(game);
    try {
        const res = await fetch(`${API_BASE}/${gameKey}/items/inspect_build`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ equipment })
        });
        if (!res.ok) return {};
        const data = await res.json();
        return data.equipment;
    } catch (e) {
        console.error("Inspect Build failed", e);
        return {};
    }
}

export function mapBackendToFrontendSlots(game: GameType, backendEq: Record<string, BackendItem | null>): Record<string, Item | null> {
    const slots: Record<string, Item | null> = {};
    const gameKey = toBackendGame(game);

    const mapSlot = (beKey: string, feKey: string) => {
        const itemData = backendEq[beKey];
        // Preserve explicit empties (nulls) so a loaded build can clear those slots on Apply.
        if (itemData === null) {
            slots[feKey] = null;
            return;
        }
        if (!itemData || !itemData.id) return;

        // Treat sentinel placeholders as empty.
        // 0x0FFFFFFF is commonly used in older build formats to represent "empty".
        if (itemData.id === 0x0FFFFFFF || itemData.id === 0xFFFFFFFF || itemData.id === -1) {
            slots[feKey] = null;
            return;
        }

        // Calculate upgrade level from ID modulo logic or rely on max_upgrade
        let upgrade = 0;
        if (itemData.max_upgrade) {
            const mod = (itemData.max_upgrade === 10 || itemData.max_upgrade === 25) ? (game === 'ELDEN_RING' ? 100 : 10) : 1;
            if (mod > 1) {
                upgrade = itemData.id % mod;
            }
        }

        const displayName = upgrade ? `${itemData.name} +${upgrade}` : itemData.name;

        // Treat "Unarmed" as an empty slot when loading builds, same as live player mapping.
        // (Some build JSONs store unarmed/unusable placeholders in ammo/weapon slots.)
        if (displayName.toLowerCase().includes('unarmed')) {
            slots[feKey] = null;
            return;
        }

        // Suppress images for Unarmed/Unknown or ID 0 as requested
        const showImage = itemData.icon_id && Number(itemData.icon_id) !== 0 && !displayName.toLowerCase().includes('unarmed') && !displayName.toLowerCase().includes('unknown');

        const itemType = getTypeForBackendKey(beKey);

        slots[feKey] = {
            id: itemData.id.toString(),
            name: displayName,
            image: showImage ? `${API_BASE}/${gameKey}/icons/${itemData.icon_id}` : '',
            type: itemType,
            description: '',
            weight: 0,
            upgrade: upgrade,
            maxUpgrade: itemData.max_upgrade,
            gemId: itemData.gem_id || undefined,
            count: itemData.count
        };
    };

    mapSlot("primary_right_wep", "weapon_r_1");
    mapSlot("secondary_right_wep", "weapon_r_2");
    mapSlot("tertiary_right_wep", "weapon_r_3");
    mapSlot("primary_left_wep", "weapon_l_1");
    mapSlot("secondary_left_wep", "weapon_l_2");
    mapSlot("tertiary_left_wep", "weapon_l_3");
    mapSlot("helmet", "head");
    mapSlot("armor", "chest");
    mapSlot("gauntlet", "hands");
    mapSlot("leggings", "legs");

    if (game === 'DARK_SOULS_3') {
        // Legacy support
        mapSlot("accessory_1", "ring_1");
        mapSlot("accessory_2", "ring_2");
        mapSlot("accessory_3", "ring_3");
        mapSlot("accessory_4", "ring_4");

        mapSlot("ring_1", "ring_1");
        mapSlot("ring_2", "ring_2");
        mapSlot("ring_3", "ring_3");
        mapSlot("ring_4", "ring_4");
        mapSlot("covenant", "covenant");
        mapSlot("primary_arrow", "ammo_arrow_1");
        mapSlot("secondary_arrow", "ammo_arrow_2");
        mapSlot("primary_bolt", "ammo_bolt_1");
        mapSlot("secondary_bolt", "ammo_bolt_2");
    } else {
        mapSlot("accessory_1", "talisman_1");
        mapSlot("accessory_2", "talisman_2");
        mapSlot("accessory_3", "talisman_3");
        mapSlot("accessory_4", "talisman_4");
        mapSlot("primary_arrow", "ammo_1_1");
        mapSlot("secondary_arrow", "ammo_1_2");
        mapSlot("primary_bolt", "ammo_2_1");
        mapSlot("secondary_bolt", "ammo_2_2");
    }

    for (let i = 1; i <= 10; i++) {
        const fePrefix = i <= 5 ? 'quick_1' : 'quick_2';
        mapSlot(`quick_item_${i}`, `${fePrefix}_${i}`);
    }
    for (let i = 0; i < 14; i++) {
        mapSlot(`magic_slot_${i}`, `spell_${i + 1}`);
    }

    return slots;
}

/**
 * Convert frontend build state to the standardized backend save format.
 * This uses the same slot mapping as writeBuild to ensure save/load compatibility.
 */
export function convertBuildToSaveFormat(game: GameType, slots: Record<string, Item | null>, status?: StatusState): Record<string, unknown> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const equipment: { [key: string]: any } = {};
    const slotMapping = buildFrontendToBackendSlotMapping(game);

    const ashOfWars: { [key: string]: number } = {};

    for (const [feKey, beKey] of Object.entries(slotMapping)) {
        const item = slots[feKey];
        if (item && item.id) {
            let finalId = parseInt(item.id);

            // Re-calculate ID if upgrade is present
            if (item.maxUpgrade && item.maxUpgrade > 0 && typeof item.upgrade === 'number') {
                if (game === 'ELDEN_RING') {
                    const base = finalId - (finalId % 100);
                    finalId = base + item.upgrade;
                } else if (game === 'DARK_SOULS_3') {
                    const base = finalId - (finalId % 10);
                    finalId = base + item.upgrade;
                }
            }

            // Save files:
            // - Include `count` for quick items + ammo
            // - Include `ash_of_war` metadata for weapons when present
            const finalCount = feKey.startsWith('ammo')
                ? (item.count ?? DEFAULT_AMMO_COUNT)
                : (feKey.startsWith('quick') ? item.count : undefined);

            if ((isWeaponBackendSlot(beKey) && item.gemId) || finalCount !== undefined) {
                equipment[beKey] = {
                    id: finalId,
                    ash_of_war: isWeaponBackendSlot(beKey) ? item.gemId : undefined,
                    count: finalCount,
                };
                if (!item.gemId) delete equipment[beKey].ash_of_war;
                if (finalCount === undefined) delete equipment[beKey].count;

                if (item.gemId) ashOfWars[beKey] = item.gemId;
            } else {
                equipment[beKey] = finalId;
            }
        } else {
            // IMPORTANT: write explicit empties so the JSON fully describes the build.
            equipment[beKey] = EMPTY_EQUIP_ID;
        }
    }

    // Build the save object
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const saveData: Record<string, any> = {
        equipment
    };

    // Stats from status
    if (status) {
        const stats: Record<string, number> = {};
        const attrs = status.attributes || {};
        if (attrs.Vigor !== undefined) stats.vigor = attrs.Vigor;
        if (attrs.Mind !== undefined) stats.mind = attrs.Mind;
        if (attrs.Endurance !== undefined) stats.endurance = attrs.Endurance;
        if (attrs.Strength !== undefined) stats.strength = attrs.Strength;
        if (attrs.Dexterity !== undefined) stats.dexterity = attrs.Dexterity;
        if (attrs.Intelligence !== undefined) stats.intelligence = attrs.Intelligence;
        if (attrs.Faith !== undefined) stats.faith = attrs.Faith;
        if (attrs.Arcane !== undefined) stats.arcane = attrs.Arcane;
        if (status.level !== undefined) stats.level = status.level;
        if (status.maxHp !== undefined) stats.max_hp = status.maxHp;
        if (Object.keys(stats).length > 0) saveData.stats = stats;

        // Shadow of Erdtree stats
        if (game === 'ELDEN_RING' && (status.scadutreeBlessing !== undefined || status.reveredSpiritAsh !== undefined)) {
            saveData.shadow_of_erdtree = {};
            if (status.scadutreeBlessing !== undefined) saveData.shadow_of_erdtree.scadutree_blessing = status.scadutreeBlessing;
            if (status.reveredSpiritAsh !== undefined) saveData.shadow_of_erdtree.revered_spirit_ash_blessing = status.reveredSpiritAsh;
        }
    }

    // Ash of wars collection
    if (Object.keys(ashOfWars).length > 0) {
        saveData.ash_of_wars = ashOfWars;
    }

    return saveData;
}

// =================== Backup API ===================

import type { BackupSettings, BackupEntry } from './types';

export async function getBackupSettings(game: string = ''): Promise<BackupSettings> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/settings?game=${encodeURIComponent(gameKey)}`);
    if (!res.ok) throw new Error('Failed to get backup settings');
    return res.json();
}

export async function saveBackupSettings(settings: BackupSettings, game: string = ''): Promise<void> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...settings, game: gameKey }),
    });
    if (!res.ok) throw new Error('Failed to save backup settings');
}

export async function autoFindSavePaths(game: string = ''): Promise<{ paths: { path: string; game: string; steam_id: string }[] }> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/auto-find?game=${encodeURIComponent(gameKey)}`);
    if (!res.ok) throw new Error('Failed to auto-find save paths');
    return res.json();
}

export async function listSaveFiles(saveDir: string, ext: string): Promise<{ files: string[] }> {
    const res = await fetch(`${API_BASE}/backup/save-files?save_dir=${encodeURIComponent(saveDir)}&ext=${encodeURIComponent(ext)}`);
    if (!res.ok) throw new Error('Failed to list save files');
    return res.json();
}

export async function listBackups(game: string = ''): Promise<{ pinned: BackupEntry[]; regular: BackupEntry[] }> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/list?game=${encodeURIComponent(gameKey)}`);
    if (!res.ok) throw new Error('Failed to list backups');
    return res.json();
}

export async function createBackup(game: string = '', requestSave: boolean = true): Promise<{ name: string; path: string }> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game: gameKey, request_save: requestSave }),
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || 'Failed to create backup');
    }
    return res.json();
}

export async function loadBackup(name: string, game: string = ''): Promise<void> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/load?name=${encodeURIComponent(name)}&game=${encodeURIComponent(gameKey)}`, {
        method: 'POST',
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || 'Failed to load backup');
    }
}

export async function deleteBackup(name: string, game: string = ''): Promise<void> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/${encodeURIComponent(name)}?game=${encodeURIComponent(gameKey)}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete backup');
}

export async function pinBackup(name: string, pin: boolean, game: string = ''): Promise<void> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/pin/${encodeURIComponent(name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin, game: gameKey }),
    });
    if (!res.ok) throw new Error('Failed to pin/unpin backup');
}

export async function renameBackup(oldName: string, newName: string, game: string = ''): Promise<void> {
    const gameKey = toBackendGame(game);
    const res = await fetch(`${API_BASE}/backup/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_name: oldName, new_name: newName, game: gameKey }),
    });
    if (!res.ok) throw new Error('Failed to rename backup');
}

export function getScreenshotUrl(name: string, game: string = ''): string {
    const gameKey = toBackendGame(game);
    return `${API_BASE}/backup/screenshot/${encodeURIComponent(name)}?game=${encodeURIComponent(gameKey)}`;
}

export async function startAutoBackup(game: string = ''): Promise<void> {
    const res = await fetch(`${API_BASE}/backup/auto/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game }),
    });
    if (!res.ok) throw new Error('Failed to start auto backup');
}

export async function stopAutoBackup(): Promise<void> {
    const res = await fetch(`${API_BASE}/backup/auto/stop`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to stop auto backup');
}

export async function getAutoBackupStatus(): Promise<{ running: boolean }> {
    const res = await fetch(`${API_BASE}/backup/auto/status`);
    if (!res.ok) throw new Error('Failed to get auto backup status');
    return res.json();
}

export async function browseDirectory(initialDir: string = ''): Promise<string | null> {
    try {
        const res = await fetch(`${API_BASE}/system/browse_directory?initial_dir=${encodeURIComponent(initialDir)}`);
        const data = await res.json();
        return data.path;
    } catch (e) {
        console.warn('Failed to browse directory', e);
        return null;
    }
}

export async function listDirs(path: string = ''): Promise<{ path: string; dirs: string[]; parent: string | null }> {
    const res = await fetch(`${API_BASE}/system/list_dirs?path=${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error('Failed to list dirs');
    return res.json();
}
