
import React from 'react';
import { Item, SlotType } from '../types';
import { SLOT_ICONS } from '../constants';

interface InventorySlotProps {
  item: Item | null;
  type: SlotType;
  isActive?: boolean;
  onClick?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  className?: string;
}

const InventorySlot: React.FC<InventorySlotProps> = ({
  item,
  type,
  isActive,
  onClick,
  onMouseEnter,
  onMouseLeave,
  className
}) => {
  return (
    <div
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={`
        relative soulslike-slot cursor-pointer flex items-center justify-center transition-all duration-200
        ${className || 'w-16 h-16 md:w-20 md:h-20'}
        ${isActive ? 'active z-10 scale-105' : 'hover:scale-102'}
      `}
    >
      {/* Background Icon/Placeholder */}
      {(!item || !item.image) && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none text-[#555]">
          {SLOT_ICONS[type] || <div className="w-8 h-8 bg-white/5 rounded-sm opacity-10" />}
        </div>
      )}

      {/* Item Image */}
      {item && item.image && (
        <img
          src={item.image}
          alt={item.name}
          className="w-[85%] h-[85%] object-cover brightness-90 contrast-110 border border-white/5 z-10"
        />
      )}

      {/* Item Count */}
      {item && item.count !== undefined && item.count > 1 && (
        <span className="absolute bottom-1 right-2 text-xs md:text-sm font-bold text-gray-300 item-count z-20 font-mono">
          {item.count}
        </span>
      )}

      {/* Upgrade Level */}
      {item && item.upgrade !== undefined && item.upgrade > 0 && (
        <span className="absolute bottom-1 right-1 text-xs md:text-sm font-bold text-cyan-200 drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)] z-20 font-mono bg-black/40 px-1 rounded-sm">
          +{item.upgrade}
        </span>
      )}

      {/* Item Detail Hover or Indicator */}
      {isActive && (
        <div className="absolute inset-0 border border-[#bfa571]/50 z-30 pointer-events-none">
          <div className="absolute -top-1 -left-1 w-4 h-4 border-t-2 border-l-2 border-[#bfa571]" />
          <div className="absolute -bottom-1 -right-1 w-4 h-4 border-b-2 border-r-2 border-[#bfa571]" />
        </div>
      )}
    </div>
  );
};

export default InventorySlot;
