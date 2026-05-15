
import React from 'react';
import { SlotType, Item, GameType } from '../types';
import InventorySlot from './InventorySlot';

interface EquipmentGridProps {
  slots: Record<string, Item | null>;
  selectedSlot: string | null;
  onSelectSlot: (slotId: string) => void;
  onHoverSlot: (slotId: string | null) => void;
  game: GameType;
}

const EquipmentGrid: React.FC<EquipmentGridProps> = ({ slots, selectedSlot, onSelectSlot, onHoverSlot, game }) => {
  const renderSlot = (id: string, type: SlotType, className?: string) => (
    <InventorySlot
      key={id}
      type={type}
      item={slots[id] || null}
      isActive={selectedSlot === id}
      onClick={() => onSelectSlot(id)}
      onMouseEnter={() => onHoverSlot(id)}
      onMouseLeave={() => onHoverSlot(null)}
      className={className}
    />
  );

  const renderSpells = () => (
    <div className="mt-4 flex flex-col items-center">
      <div className="flex gap-2 items-center mb-1">
        <div className="h-px w-4 bg-white/10" />
        <h4 className="text-[9px] fantasy-font text-gray-400 uppercase tracking-[0.2em]">Spells / Memory Slots</h4>
        <div className="h-px w-4 bg-white/10" />
      </div>
      <div className="flex flex-col gap-0.5">
        <div className="flex gap-0.5">
          {[1, 2, 3, 4, 5, 6, 7].map(i => renderSlot(`spell_${i}`, SlotType.SPELL, "w-10 h-10"))}
        </div>
        <div className="flex gap-0.5">
          {[8, 9, 10, 11, 12, 13, 14].map(i => renderSlot(`spell_${i}`, SlotType.SPELL, "w-10 h-10"))}
        </div>
      </div>
    </div>
  );

  if (game === 'DARK_SOULS_3') {
    return (
      <div className="relative flex flex-col gap-0.5 p-4 bg-[#1a1a1a]/90 backdrop-blur-md border border-white/10 rounded-md shadow-2xl">
        {/* Row 1: Right Hand Weapons + Arrows */}
        <div className="flex gap-1 items-end">
          <div className="flex gap-1">
            {[1, 2, 3].map(i => renderSlot(`weapon_r_${i}`, SlotType.WEAPON_R))}
          </div>
          <div className="w-12" /> {/* Spacer */}
          <div className="flex gap-1">
            {[1, 2].map(i => renderSlot(`ammo_arrow_${i}`, SlotType.AMMO_ARROW))}
          </div>
        </div>

        {/* Row 2: Left Hand Weapons + Bolts */}
        <div className="flex gap-1 items-start mt-1">
          <div className="flex gap-1">
            {[1, 2, 3].map(i => renderSlot(`weapon_l_${i}`, SlotType.WEAPON_L))}
          </div>
          <div className="w-12" /> {/* Spacer */}
          <div className="flex gap-1">
            {[1, 2].map(i => renderSlot(`ammo_bolt_${i}`, SlotType.AMMO_BOLT))}
          </div>
        </div>

        {/* Middle Section: Armor, Rings, and Covenant */}
        <div className="flex gap-12 mt-6">
          <div className="flex flex-col gap-2">
            {/* Armor Row */}
            <div className="flex gap-1">
              {renderSlot('head', SlotType.ARMOR_HEAD)}
              {renderSlot('chest', SlotType.ARMOR_CHEST)}
              {renderSlot('hands', SlotType.ARMOR_HANDS)}
              {renderSlot('legs', SlotType.ARMOR_LEGS)}
            </div>

            {/* Rings Row */}
            <div className="flex gap-1">
              {[1, 2, 3, 4].map(i => renderSlot(`ring_${i}`, SlotType.RING))}
            </div>
          </div>

          {/* Covenant Diamond Slot */}
          <div className="flex items-center pt-8">
            <div className="relative group">
              <div className="absolute inset-[-4px] border border-[#bfa571]/40 rotate-45 pointer-events-none group-hover:border-[#bfa571]/70 transition-colors" />
              <div className="absolute inset-[-8px] border border-[#bfa571]/10 rotate-45 pointer-events-none" />
              <div className="rotate-45 bg-black/60 overflow-hidden border border-white/5 shadow-xl">
                <div className="-rotate-45">
                  {renderSlot('covenant', SlotType.COVENANT, "w-24 h-24")}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Row 5 & 6: Quick Items */}
        <div className="flex gap-1 mt-6">
          {[1, 2, 3, 4, 5].map(i => renderSlot(`quick_1_${i}`, SlotType.QUICK_ITEM))}
        </div>
        <div className="flex gap-1">
          {[6, 7, 8, 9, 10].map(i => renderSlot(`quick_2_${i}`, SlotType.QUICK_ITEM))}
        </div>

        {/* Spells Grid (Moved below Quick Items) */}
        {renderSpells()}
      </div>
    );
  }

  // Elden Ring Layout (Default)
  return (
    <div className="flex flex-col gap-0.5 p-4 bg-[#1a1a1a]/90 backdrop-blur-md border border-white/10 rounded-md shadow-2xl">
      <div className="flex gap-1">
        <div className="flex gap-1">
          {[1, 2, 3].map(i => renderSlot(`weapon_r_${i}`, SlotType.WEAPON_R))}
        </div>
        <div className="w-12" />
        <div className="flex gap-1">
          {[1, 2].map(i => renderSlot(`ammo_1_${i}`, SlotType.AMMO_ARROW))}
        </div>
      </div>
      <div className="flex gap-1 mt-1">
        <div className="flex gap-1">
          {[1, 2, 3].map(i => renderSlot(`weapon_l_${i}`, SlotType.WEAPON_L))}
        </div>
        <div className="w-12" />
        <div className="flex gap-1">
          {[1, 2].map(i => renderSlot(`ammo_2_${i}`, SlotType.AMMO_ARROW))}
        </div>
      </div>
      <div className="flex gap-1 mt-6">
        {renderSlot('head', SlotType.ARMOR_HEAD)}
        {renderSlot('chest', SlotType.ARMOR_CHEST)}
        {renderSlot('hands', SlotType.ARMOR_HANDS)}
        {renderSlot('legs', SlotType.ARMOR_LEGS)}
      </div>
      <div className="flex gap-1 mt-2">
        {[1, 2, 3, 4].map(i => renderSlot(`talisman_${i}`, SlotType.TALISMAN))}
      </div>

      <div className="flex gap-1 mt-6">
        {[1, 2, 3, 4, 5].map(i => renderSlot(`quick_1_${i}`, SlotType.QUICK_ITEM))}
      </div>
      <div className="flex gap-1">
        {[6, 7, 8, 9, 10].map(i => renderSlot(`quick_2_${i}`, SlotType.QUICK_ITEM))}
      </div>

      <div className="mt-4 flex flex-col items-center">
        <div className="flex gap-2 items-center mb-1">
          <div className="h-px w-4 bg-white/10" />
          <h4 className="text-[9px] fantasy-font text-gray-400 uppercase tracking-[0.2em]">Wondrous Physick</h4>
          <div className="h-px w-4 bg-white/10" />
        </div>
        <div className="flex gap-2 justify-center">
          {renderSlot('physick_tear_1', SlotType.PHYSICK, "w-10 h-10")}
          {renderSlot('physick_tear_2', SlotType.PHYSICK, "w-10 h-10")}
        </div>
      </div>

      {/* Spells Grid (Moved below Quick Items) */}
      {renderSpells()}
    </div>
  );
};

export default EquipmentGrid;
