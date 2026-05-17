import React from 'react';
import { Item } from '../types';

interface SpiritSummonConfigProps {
    item: Item;
    onUpdate: (updated: Item) => void;
}

const SpiritSummonConfig: React.FC<SpiritSummonConfigProps> = ({ item, onUpdate }) => {
    if (!item.variants || item.variants.length === 0) return null;

    const handleVariantChange = (variant: { id: number; name: string }) => {
        onUpdate({ ...item, id: variant.id.toString(), name: variant.name });
    };

    return (
        <div className="p-4 bg-black/60 border border-[#bfa571]/30 rounded mt-4 backdrop-blur-sm">
            <h3 className="text-lg font-bold text-[#bfa571] mb-2 font-serif">Configure Spirit Summon</h3>
            {item.variants.length > 0 && (
                <div className="mb-4">
                    <label className="block text-gray-300 text-sm mb-1">Upgrade Level</label>
                    <select
                        value={item.id}
                        onChange={(e) => {
                            if (e.target.value === item.baseId) {
                                handleVariantChange({ id: parseInt(item.baseId!), name: item.baseName || item.name });
                            } else {
                                const variant = item.variants!.find(v => v.id.toString() === e.target.value);
                                if (variant) handleVariantChange(variant);
                            }
                        }}
                        className="w-full bg-black/80 border border-white/20 text-white p-2 rounded focus:border-[#bfa571] outline-none text-sm"
                    >
                        <option value={item.baseId}>+0</option>
                        {item.variants.map(v => (
                            <option key={v.id} value={v.id}>{v.name.replace(item.baseName || item.name, '').trim() || `+${v.id % 1000}`}</option>
                        ))}
                    </select>
                </div>
            )}
        </div>
    );
};

export default SpiritSummonConfig;
