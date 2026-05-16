
import React from 'react';
import { GameType, SlotType } from './types';

export const SLOT_ICONS: Record<string, React.ReactNode> = {
  WEAPON_R: (
    <svg className="w-14 h-14 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Detailed Crossed Axe and Sword silhouette */}
      <path d="M25,80 L80,25 M75,20 L85,30" stroke="currentColor" strokeWidth="1.5" />
      <path d="M75,75 L20,20" stroke="currentColor" strokeWidth="2.5" />
      <path d="M15,15 L35,12 L40,30 L20,35 Z" opacity="0.8" /> {/* Axe head */}
      <path d="M72,72 L85,85" stroke="currentColor" strokeWidth="4" /> {/* Sword Pommel */}
    </svg>
  ),
  WEAPON_L: (
    <svg className="w-14 h-14 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Detailed Shield silhouette */}
      <path d="M50,15 L20,28 V55 C20,78 50,88 50,88 C50,88 80,78 80,55 V28 L50,15 Z" />
      <path d="M50,22 L30,32 V55 C30,72 50,80 50,80 C50,80 70,72 70,55 V32 L50,22 Z" fill="black" opacity="0.3" />
    </svg>
  ),
  AMMO_ARROW: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Three bundled arrows silhouette */}
      <path d="M25,85 L75,15" stroke="currentColor" strokeWidth="1.5" />
      <path d="M35,85 L85,15" stroke="currentColor" strokeWidth="1.5" />
      <path d="M15,85 L65,15" stroke="currentColor" strokeWidth="1.5" />
      <path d="M60,15 L70,25 M70,15 L80,25 M50,15 L60,25" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
  AMMO_BOLT: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Three bundled bolts silhouette */}
      <rect x="25" y="20" width="8" height="65" />
      <rect x="46" y="20" width="8" height="65" />
      <rect x="67" y="20" width="8" height="65" />
    </svg>
  ),
  ARMOR_HEAD: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Knight Helm silhouette */}
      <path d="M35,25 C35,15 65,15 65,25 V45 C65,55 58,65 50,75 C42,65 35,55 35,45 V25 Z" />
      <rect x="40" y="35" width="20" height="4" rx="1" fill="black" opacity="0.4" /> {/* Visor slit */}
      <path d="M35,45 Q50,55 65,45" fill="none" stroke="black" strokeWidth="1" opacity="0.2" />
    </svg>
  ),
  ARMOR_CHEST: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Detailed Chestplate silhouette */}
      <path d="M35,15 L25,30 V45 L15,55 V85 H85 V55 L75,45 V30 L65,15 Z" />
      <path d="M50,15 V85" stroke="black" strokeWidth="1" opacity="0.2" />
      <path d="M35,15 Q50,25 65,15" fill="none" stroke="black" strokeWidth="1" opacity="0.3" />
    </svg>
  ),
  ARMOR_HANDS: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Detailed Gauntlet silhouette */}
      <path d="M35,85 V45 C35,35 45,30 50,30 C55,30 65,35 65,45 V85 H35 Z" />
      <path d="M35,55 H65 M35,70 H65" stroke="black" strokeWidth="1" opacity="0.3" />
      <path d="M45,30 V40 M55,30 V40" stroke="black" strokeWidth="1" opacity="0.3" />
    </svg>
  ),
  ARMOR_LEGS: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Detailed Leggings/Greaves silhouette */}
      <path d="M30,15 L25,75 L20,85 H45 L40,15 Z" /> {/* Left leg */}
      <path d="M70,15 L75,75 L80,85 H55 L60,15 Z" /> {/* Right leg */}
      <path d="M28,45 H42 M58,45 H72" stroke="black" strokeWidth="1" opacity="0.3" />
    </svg>
  ),
  RING: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="5">
      {/* Double Ring silhouette */}
      <circle cx="40" cy="50" r="18" />
      <circle cx="60" cy="50" r="18" />
    </svg>
  ),
  TALISMAN: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Talisman/Stone silhouette */}
      <path d="M30,30 L70,30 L80,50 L70,75 L30,75 L20,50 Z" />
      <path d="M35,35 L65,35 L72,50 L65,70 L35,70 L28,50 Z" fill="black" opacity="0.2" />
    </svg>
  ),
  QUICK_ITEM: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Flask/Estus silhouette */}
      <path d="M40,15 H60 V28 C75,35 75,75 60,85 H40 C25,75 25,35 40,28 V15 Z" />
      <rect x="42" y="18" width="16" height="6" fill="black" opacity="0.3" />
    </svg>
  ),
  COVENANT: (
    <svg className="w-14 h-14 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Diamond Covenant frame silhouette */}
      <path d="M50,10 L90,50 L50,90 L10,50 Z" />
      <path d="M50,25 L75,50 L50,75 L25,50 Z" fill="black" opacity="0.3" />
    </svg>
  ),
  SPELL: (
    <svg className="w-10 h-10 opacity-20" viewBox="0 0 100 100" fill="currentColor">
      {/* Scroll silhouette */}
      <rect x="25" y="15" width="50" height="70" rx="2" />
      <path d="M30,30 H70 M30,50 H70 M30,70 H60" stroke="black" strokeWidth="2" opacity="0.4" />
    </svg>
  ),
  PHYSICK: (
    <svg className="w-12 h-12 opacity-25" viewBox="0 0 100 100" fill="currentColor">
      {/* Tear / Flask Mixed silhouette */}
      <path d="M50,15 C50,15 30,40 30,65 C30,85 40,90 50,90 C60,90 70,85 70,65 C70,40 50,15 50,15 Z" />
      <circle cx="50" cy="65" r="10" fill="black" opacity="0.3" />
    </svg>
  )
};

interface SlotInfo {
  csv: string;
  slotKey: string;
  slotType: SlotType;
}

export const SLOT_CSV_MAPPING: Record<GameType, Record<string, SlotInfo>> = {
  ELDEN_RING: {
    WEAPON_R:   { csv: 'EquipParamWeapon.csv', slotKey: 'weapon', slotType: SlotType.WEAPON_R },
    WEAPON_L:   { csv: 'EquipParamWeapon.csv', slotKey: 'weapon', slotType: SlotType.WEAPON_L },
    AMMO_ARROW: { csv: 'EquipParamWeapon.csv', slotKey: 'arrow', slotType: SlotType.AMMO_ARROW },
    AMMO_BOLT:  { csv: 'EquipParamWeapon.csv', slotKey: 'bolt', slotType: SlotType.AMMO_BOLT },
    ARMOR_HEAD: { csv: 'EquipParamProtector.csv', slotKey: 'helmet', slotType: SlotType.ARMOR_HEAD },
    ARMOR_CHEST:{ csv: 'EquipParamProtector.csv', slotKey: 'armor', slotType: SlotType.ARMOR_CHEST },
    ARMOR_HANDS:{ csv: 'EquipParamProtector.csv', slotKey: 'gauntlet', slotType: SlotType.ARMOR_HANDS },
    ARMOR_LEGS: { csv: 'EquipParamProtector.csv', slotKey: 'leggings', slotType: SlotType.ARMOR_LEGS },
    TALISMAN:   { csv: 'EquipParamAccessory.csv', slotKey: 'talisman', slotType: SlotType.TALISMAN },
    RING:       { csv: 'EquipParamAccessory.csv', slotKey: 'ring', slotType: SlotType.RING },
    COVENANT:   { csv: 'EquipParamAccessory.csv', slotKey: 'covenant', slotType: SlotType.COVENANT },
    QUICK_ITEM: { csv: 'EquipParamGoods.csv', slotKey: 'quick', slotType: SlotType.QUICK_ITEM },
    SPELL:      { csv: 'EquipParamGoods.csv', slotKey: 'spell', slotType: SlotType.SPELL },
    PHYSICK:    { csv: 'EquipParamGoods.csv', slotKey: 'physick', slotType: SlotType.PHYSICK },
  },
  DARK_SOULS_3: {
    WEAPON_R:   { csv: 'EquipParamWeapon.csv', slotKey: 'weapon', slotType: SlotType.WEAPON_R },
    WEAPON_L:   { csv: 'EquipParamWeapon.csv', slotKey: 'weapon', slotType: SlotType.WEAPON_L },
    AMMO_ARROW: { csv: 'EquipParamWeapon.csv', slotKey: 'arrow', slotType: SlotType.AMMO_ARROW },
    AMMO_BOLT:  { csv: 'EquipParamWeapon.csv', slotKey: 'bolt', slotType: SlotType.AMMO_BOLT },
    ARMOR_HEAD: { csv: 'EquipParamProtector.csv', slotKey: 'helmet', slotType: SlotType.ARMOR_HEAD },
    ARMOR_CHEST:{ csv: 'EquipParamProtector.csv', slotKey: 'armor', slotType: SlotType.ARMOR_CHEST },
    ARMOR_HANDS:{ csv: 'EquipParamProtector.csv', slotKey: 'gauntlet', slotType: SlotType.ARMOR_HANDS },
    ARMOR_LEGS: { csv: 'EquipParamProtector.csv', slotKey: 'leggings', slotType: SlotType.ARMOR_LEGS },
    RING:       { csv: 'EquipParamAccessory.csv', slotKey: 'ring', slotType: SlotType.RING },
    TALISMAN:   { csv: 'EquipParamAccessory.csv', slotKey: 'ring', slotType: SlotType.TALISMAN },
    COVENANT:   { csv: 'EquipParamAccessory.csv', slotKey: 'covenant', slotType: SlotType.COVENANT },
    QUICK_ITEM: { csv: 'EquipParamGoods.csv', slotKey: 'quick', slotType: SlotType.QUICK_ITEM },
    SPELL:      { csv: 'EquipParamGoods.csv', slotKey: 'spell', slotType: SlotType.SPELL },
  },
};

export function getSlotInfo(game: GameType, slotId: string): SlotInfo | undefined {
  const mapping = SLOT_CSV_MAPPING[game];
  if (!mapping) return undefined;

  const s = slotId.toLowerCase();

  if (s.startsWith('weapon_r')) return mapping.WEAPON_R;
  if (s.startsWith('weapon_l')) return mapping.WEAPON_L;
  if (s.startsWith('ammo_arrow') || s.startsWith('ammo_1')) return mapping.AMMO_ARROW;
  if (s.startsWith('ammo_bolt') || s.startsWith('ammo_2')) return mapping.AMMO_BOLT;
  if (s === 'head')   return mapping.ARMOR_HEAD;
  if (s === 'chest')  return mapping.ARMOR_CHEST;
  if (s === 'hands')  return mapping.ARMOR_HANDS;
  if (s === 'legs')   return mapping.ARMOR_LEGS;
  if (s.startsWith('ring'))     return mapping.RING;
  if (s.startsWith('talisman')) return mapping.TALISMAN;
  if (s === 'covenant')         return mapping.COVENANT;
  if (s.startsWith('quick'))    return mapping.QUICK_ITEM;
  if (s.startsWith('spell'))    return mapping.SPELL;
  if (s.startsWith('physick'))  return mapping.PHYSICK;

  return undefined;
}


