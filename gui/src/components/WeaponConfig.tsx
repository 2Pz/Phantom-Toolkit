import React, { useEffect, useState } from 'react';
import { Item, GameType } from '../types';
import { searchItems } from '../api';

interface WeaponConfigProps {
    game: GameType;
    item: Item;
    onUpdate: (updated: Item) => void;
}

const WeaponConfig: React.FC<WeaponConfigProps> = ({ game, item, onUpdate }) => {
    const [gems, setGems] = useState<Item[]>([]);
    const [loadingGems, setLoadingGems] = useState(false);
    const [isGemSelectorOpen, setIsGemSelectorOpen] = useState(false);
    const [gemSearch, setGemSearch] = useState("");

    useEffect(() => {
        const isWeapon = item.type.toLowerCase().includes('weapon') || item.type.toLowerCase().includes('shield');
        if (game === 'ELDEN_RING' && (isWeapon || item.maxUpgrade! > 0)) {
            // eslint-disable-next-line
            setLoadingGems(true);
            searchItems(game, "", "EquipParamGem.csv", undefined, undefined, 1000).then(items => {
                setGems(items.sort((a, b) => a.name.localeCompare(b.name)));
            }).finally(() => setLoadingGems(false));
        }
    }, [game, item.type, item.maxUpgrade]);

    const handleUpgradeChange = (val: number) => {
        onUpdate({ ...item, upgrade: val });
    };

    const handleGemChange = (val: string | number) => {
        const numVal = typeof val === 'string' ? parseInt(val) : val;
        onUpdate({ ...item, gemId: numVal === -1 ? undefined : numVal });
        setIsGemSelectorOpen(false);
    };

    const filteredGems = gems.filter(g =>
        g.name.toLowerCase().includes(gemSearch.toLowerCase()) ||
        g.id.toString().includes(gemSearch)
    );

    const currentGem = gems.find(g => Number(g.id) === item.gemId);

    if (item.maxUpgrade === undefined || item.maxUpgrade === 0) {
        return null;
    }

    return (
        <div className="p-4 bg-black/60 border border-[#bfa571]/30 rounded mt-4 backdrop-blur-sm">
            <h3 className="text-lg font-bold text-[#bfa571] mb-2 font-serif">Configure Weapon</h3>

            {/* Upgrade Slider */}
            <div className="mb-4">
                <div className="flex justify-between mb-1">
                    <label className="text-gray-300 text-sm">Upgrade Level</label>
                    <span className="text-[#bfa571] font-bold font-mono">+{item.upgrade || 0}</span>
                </div>
                <input
                    type="range"
                    min="0"
                    max={item.maxUpgrade}
                    value={item.upgrade || 0}
                    onChange={(e) => handleUpgradeChange(parseInt(e.target.value))}
                    className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-[#bfa571]"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>+0</span>
                    <span>+{item.maxUpgrade}</span>
                </div>
            </div>

            {/* Ash of War Selection (Elden Ring only) */}
            {game === 'ELDEN_RING' && (
                <div>
                    <label className="block text-gray-300 text-sm mb-1">Ash of War</label>
                    {loadingGems ? (
                        <div className="text-gray-500 text-sm italic">Loading Gems...</div>
                    ) : (
                        <div className="relative">
                            <button
                                onClick={() => setIsGemSelectorOpen(!isGemSelectorOpen)}
                                className="w-full bg-black/80 border border-white/20 text-white p-2 rounded focus:border-[#bfa571] outline-none flex items-center justify-between hover:bg-white/5 transition-colors"
                            >
                                <span className="flex items-center gap-2">
                                    {currentGem ? (
                                        <>
                                            {currentGem.image && <img src={currentGem.image} className="w-6 h-6 object-contain" />}
                                            <span className="truncate">{currentGem.name}</span>
                                        </>
                                    ) : (
                                        <span className="text-gray-400 italic">No Ash of War</span>
                                    )}
                                </span>
                                <span className="text-xs text-[#bfa571] ml-2">
                                    {isGemSelectorOpen ? '▼' : '▶'}
                                </span>
                            </button>

                            {isGemSelectorOpen && (
                                <div className="mt-2 bg-black/90 border border-[#bfa571]/30 rounded p-2 animate-in fade-in zoom-in-95 duration-100">
                                    <input
                                        type="text"
                                        placeholder="SEARCH ASH OF WAR..."
                                        className="w-full bg-white/5 border border-white/10 text-white px-3 py-1.5 text-xs mb-2 rounded outline-none focus:border-[#bfa571] placeholder:text-gray-600 fantasy-font uppercase tracking-widest"
                                        value={gemSearch}
                                        onChange={(e) => setGemSearch(e.target.value)}
                                        autoFocus
                                    />

                                    <div className="max-h-[300px] overflow-y-auto custom-scrollbar grid grid-cols-4 gap-2">
                                        <div
                                            onClick={() => handleGemChange(-1)}
                                            className={`aspect-square border border-dashed border-white/20 hover:border-red-500/50 hover:bg-red-500/10 cursor-pointer rounded flex items-center justify-center group transition-all text-xs text-gray-500 ${!item.gemId ? 'bg-white/10' : ''}`}
                                            title="Remove Ash of War"
                                        >
                                            <span className="group-hover:text-red-400">NONE</span>
                                        </div>

                                        {filteredGems.map(gem => (
                                            <div
                                                key={gem.id}
                                                onClick={() => handleGemChange(gem.id)}
                                                className={`aspect-square bg-black/40 border border-white/10 hover:border-[#bfa571] hover:bg-[#bfa571]/10 cursor-pointer rounded flex items-center justify-center p-1 transition-all relative ${item.gemId === Number(gem.id) ? 'border-[#bfa571] bg-[#bfa571]/20' : ''}`}
                                                title={gem.name}
                                            >
                                                {gem.image ? (
                                                    <img src={gem.image} alt={gem.name} className="w-full h-full object-contain" />
                                                ) : (
                                                    <span className="text-[9px] text-center text-gray-500 leading-tight break-words">{gem.name}</span>
                                                )}
                                                {/* ID Overlay on Hover? Or just Title */}
                                            </div>
                                        ))}
                                    </div>

                                    {filteredGems.length === 0 && (
                                        <div className="text-center text-xs text-gray-500 py-4 italic">No matching Ash of War found</div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default WeaponConfig;
