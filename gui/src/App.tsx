
import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Item } from './types';
import type { Build, GameType, StatusState, PlayerData } from './types';
import { SLOT_CSV_MAPPING } from './constants';
import EquipmentGrid from './components/EquipmentGrid';
import { AlertModal } from './components/Modal';
import BackupTab from './components/BackupTab';
import { detectGame, getPlayers, getRecentPlayers, quitToMenu, fixInfiniteLoading, toggleFogWall, writeStats, toggleCheat as apiToggleCheat, searchItems, writeBuild, inspectBuild, mapBackendToFrontendSlots, convertBuildToSaveFormat, saveBuild, browseSaveFile, getConfig, getMetadata } from './api';
import type { AppMetadata } from './api';
import WeaponConfig from './components/WeaponConfig';
import { LanguageSelector } from './components/LanguageSelector';

const ER_ATTRIBUTES = ['Vigor', 'Mind', 'Endurance', 'Strength', 'Dexterity', 'Intelligence', 'Faith', 'Arcane'];
const DS3_ATTRIBUTES = ['Vigor', 'Attunement', 'Endurance', 'Vitality', 'Strength', 'Dexterity', 'Intelligence', 'Faith', 'Luck'];

interface CheatsState {
  noWeight: boolean;
  noDead: boolean;
  noDamage: boolean;
  noHit: boolean;
  noStamina: boolean;
  noFP: boolean;
  noGoods: boolean;
  noArrow: boolean;
}

interface StatusPanelProps {
  playerName: string;
  status: StatusState;
  game: GameType;
  onStatusChange: (path: string, value: string | number | boolean) => void;
  onAttributeChange: (name: string, value: number) => void;
  isReadOnly: boolean;
  onCopy: () => void;
}

const StatusPanel: React.FC<StatusPanelProps> = ({ playerName, status, game, onStatusChange, onAttributeChange, isReadOnly, onCopy }) => {
  const attributes = game === 'ELDEN_RING' ? ER_ATTRIBUTES : DS3_ATTRIBUTES;

  const inputClasses = `bg-transparent text-right font-bold text-gray-100 outline-none w-20 inter-font text-base [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none hover:bg-white/5 focus:bg-[#bfa571]/15 px-2 py-0.5 rounded transition-all ${isReadOnly ? 'pointer-events-none' : 'border border-transparent focus:border-[#bfa571]/50'}`;

  const labelClasses = "text-xs fantasy-font text-gray-400 uppercase tracking-widest font-medium";
  const groupTitleClasses = "text-xs fantasy-font text-[#bfa571] uppercase tracking-[0.25em] mb-4 flex items-center gap-3 border-b border-[#bfa571]/20 pb-2";

  return (
    <div className="w-[320px] flex flex-col p-6 h-full overflow-y-auto custom-scrollbar border-r border-[#2a2a2a] bg-black/40">
      {/* Header Section */}
      <div className="mb-6">
        <div className="flex justify-between items-start mb-2 px-1">
          <div className="flex flex-col gap-1">
            <h2 className="text-xl fantasy-font text-gray-100 tracking-widest leading-none">
              {playerName}
            </h2>
            {status.steamId && (
              <a
                href={`https://steamcommunity.com/profiles/${status.steamId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 w-fit text-[10px] text-[#bfa571]/80 hover:text-[#bfa571] hover:bg-white/5 px-1.5 py-0.5 rounded transition-all mb-1 border border-transparent hover:border-[#bfa571]/30"
                title={`Open Steam Profile: ${status.steamId}`}
              >
                <span className="font-mono tracking-wider">{status.steamId}</span>
                <span className="text-[12px] leading-none mb-0.5">↗</span>
              </a>
            )}
          </div>

          {isReadOnly && (
            <button
              onClick={onCopy}
              className="text-[9px] border border-[#bfa571]/60 text-[#bfa571] px-2 py-1 rounded-sm hover:bg-[#bfa571] hover:text-black transition-all fantasy-font tracking-widest font-bold"
            >
              COPY BUILD
            </button>
          )}
        </div>
        <div className="status-header-line opacity-80"></div>
      </div>

      {/* Group 1: Identity */}
      <div className="mb-8">
        <h3 className={groupTitleClasses}>
          Identity
        </h3>
        <div className="status-line flex flex-col gap-2">
          <div className="flex justify-between items-center pr-2">
            <span className={labelClasses}>Level</span>
            <input
              type="number"
              value={playerName ? (status.level ?? '') : ''}
              onChange={(e) => onStatusChange('level', parseInt(e.target.value) || 0)}
              className={inputClasses}
              readOnly={isReadOnly}
            />
          </div>
          <div className="flex justify-between items-center pr-2">
            <span className={labelClasses}>Journey</span>
            <input
              type="number"
              value={playerName ? (status.journey ?? '') : ''}
              onChange={(e) => onStatusChange('journey', parseInt(e.target.value) || 1)}
              className={inputClasses}
              readOnly={isReadOnly}
            />
          </div>
        </div>
      </div>

      {/* Group 2: Growth */}
      <div className="mb-8">
        <h3 className={groupTitleClasses}>
          Growth
        </h3>
        <div className="status-line flex flex-col gap-2">
          <div className="flex justify-between items-center pr-2">
            <span className={labelClasses}>{game === 'ELDEN_RING' ? 'Runes' : 'Souls'}</span>
            <input
              type="number"
              value={playerName ? (status.secondary ?? '') : ''}
              onChange={(e) => onStatusChange('secondary', parseInt(e.target.value) || 0)}
              className={inputClasses}
              readOnly={isReadOnly}
            />
          </div>

          {game === 'ELDEN_RING' && (
            <div className="flex flex-col gap-2 mt-1">
              <div className="flex justify-between items-center pr-2">
                <span className={labelClasses}>Scadutree Blessing</span>
                <input
                  type="number"
                  value={playerName ? (status.scadutreeBlessing ?? '') : ''}
                  onChange={(e) => onStatusChange('scadutreeBlessing', parseInt(e.target.value) || 0)}
                  className={`${inputClasses} text-[#bfa571]`}
                  readOnly={isReadOnly}
                />
              </div>
              <div className="flex justify-between items-center pr-2">
                <span className={labelClasses}>Spirit Blessing</span>
                <input
                  type="number"
                  value={playerName ? (status.reveredSpiritAsh ?? '') : ''}
                  onChange={(e) => onStatusChange('reveredSpiritAsh', parseInt(e.target.value) || 0)}
                  className={`${inputClasses} text-[#bfa571]`}
                  readOnly={isReadOnly}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Group 3: Core Attributes */}
      <div className="flex-1 pb-10">
        <h3 className={groupTitleClasses}>
          Attributes
        </h3>
        <div className="status-line flex flex-col gap-2">
          {attributes.map((key) => (
            <div key={key} className="flex justify-between items-center pr-2">
              <span className="text-base text-gray-200 Cormorant font-semibold tracking-wide">{key}</span>
              <input
                type="number"
                value={playerName ? (status.attributes[key] ?? '') : ''}
                onChange={(e) => onAttributeChange(key, parseInt(e.target.value) || 0)}
                className={inputClasses}
                readOnly={isReadOnly}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const ToolkitTab: React.FC<{ cheats: CheatsState, onToggle: (key: keyof CheatsState) => void, selectedGame: GameType }> = ({ cheats, onToggle, selectedGame }) => {
  const cheatList = [
    { key: 'noDead', label: 'No Dead', icon: '🛡️' },
    { key: 'noDamage', label: 'No Damage', icon: '❤️' },
    { key: 'noHit', label: 'No Hit', icon: '💨', disabledOn: 'DARK_SOULS_3' },
    { key: 'noWeight', label: 'No Weight', icon: '⚖️' },
    { key: 'noStamina', label: 'No Stamina Consumption', icon: '⚡' },
    { key: 'noFP', label: 'No FP Consumption', icon: '🔮' },
    { key: 'noGoods', label: 'No Goods Consumption', icon: '🧪' },
    { key: 'noArrow', label: 'No Arrow Consumption', icon: '🏹' },
  ] as const;

  return (
    <div className="flex-1 p-8 flex flex-col gap-6 inter-font overflow-y-auto custom-scrollbar">
      <div className="mb-2">
        <h2 className="text-2xl fantasy-font text-[#bfa571] uppercase tracking-widest">Phantom Toolkit</h2>
        <p className="text-gray-500 text-sm mt-1 Cormorant font-light">Global session modifiers and toolkit utilities.</p>
        <div className="status-header-line w-full"></div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cheatList.map((cheat) => {
          const isDisabled = cheat.key === 'noHit' && selectedGame === 'DARK_SOULS_3';

          return (
            <div
              key={cheat.key}
              onClick={() => !isDisabled && onToggle(cheat.key)}
              className={`
                p-6 border flex items-center justify-between transition-all duration-300 group relative overflow-hidden
                ${isDisabled
                  ? 'bg-black/20 border-white/5 opacity-50 cursor-not-allowed'
                  : cheats[cheat.key]
                    ? 'bg-[#bfa571]/10 border-[#bfa571] shadow-[0_0_20px_rgba(191,165,113,0.1)] cursor-pointer'
                    : 'bg-black/40 border-white/5 hover:border-white/20 cursor-pointer'}
              `}
            >
              <div className="flex gap-6 items-center">
                <span className={`text-3xl filter brightness-125 transition-all ${isDisabled ? 'grayscale' : 'grayscale group-hover:grayscale-0'}`}>{cheat.icon}</span>
                <div className="flex flex-col">
                  <h4 className={`fantasy-font uppercase tracking-wider text-xl ${cheats[cheat.key] && !isDisabled ? 'text-[#bfa571]' : 'text-gray-100'}`}>
                    {cheat.label}
                  </h4>
                  {isDisabled && (
                    <span className="text-[10px] fantasy-font text-[#bfa571] tracking-widest mt-0.5">NOT SUPPORTED YET</span>
                  )}
                </div>
              </div>

              {!isDisabled && (
                <div className={`
                  w-12 h-6 rounded-full p-1 transition-colors duration-300 relative
                  ${cheats[cheat.key] ? 'bg-[#bfa571]' : 'bg-gray-800'}
                `}>
                  <div className={`
                    w-4 h-4 bg-white rounded-full transition-transform duration-300
                    ${cheats[cheat.key] ? 'translate-x-6' : 'translate-x-0'}
                  `} />
                </div>
              )}
            </div>
          );
        })}
      </div>


    </div>
  );
};

const MainTab: React.FC<{
  currentInspectedName: string;
  onInspect: (player: PlayerData) => void;
  sessionPlayers: PlayerData[];
  recentPlayers: PlayerData[];
  localPlayer: PlayerData;
  selectedGame: GameType;
}> = ({ currentInspectedName, onInspect, sessionPlayers, recentPlayers, localPlayer, selectedGame }) => {
  return (
    <div className="flex-1 flex flex-col p-6 inter-font gap-8 overflow-y-auto custom-scrollbar">
      <section>
        <h2 className="text-gray-200 font-bold mb-4">Current Players</h2>
        <div className="border border-[#333] bg-[#1e1e1e] overflow-x-auto custom-scrollbar">
          <table className="session-table min-w-[600px]">
            <thead>
              <tr>
                <th className="w-1/3">Username</th>
                <th className="w-1/3">Level</th>
                <th className="w-1/3">HP</th>
              </tr>
            </thead>
            <tbody>
              <tr
                className={`cursor-pointer transition-colors ${currentInspectedName === localPlayer.name ? 'player-row-current' : 'hover:bg-white/5'}`}
                onClick={() => onInspect(localPlayer)}
              >
                <td>{localPlayer.name}</td>
                <td>{localPlayer.name ? localPlayer.status.level : ''}</td>
                <td>
                  {localPlayer.name && (
                    <div className="hp-bar-container">
                      <div className="hp-bar-fill" style={{ width: `${((localPlayer.status.hp || 0) / (localPlayer.status.maxHp || 1)) * 100}%` }}></div>
                      <span className="hp-text">
                        {localPlayer.status.hp} / {localPlayer.status.maxHp} ({Math.round(((localPlayer.status.hp || 0) / (localPlayer.status.maxHp || 1)) * 100)}%)
                      </span>
                    </div>
                  )}
                </td>
              </tr>
              {sessionPlayers.map((player, i) => (
                <tr
                  key={i}
                  className={`cursor-pointer transition-colors ${currentInspectedName === player.name ? 'player-row-current' : 'hover:bg-white/5'}`}
                  onClick={() => onInspect(player)}
                >
                  <td>{player.name}</td>
                  <td>{player.name ? player.status.level : ''}</td>
                  <td>
                    {player.name && (
                      <div className="hp-bar-container">
                        <div className="hp-bar-fill" style={{ width: `${((player.status.hp || 0) / (player.status.maxHp || 1)) * 100}%` }}></div>
                        <span className="hp-text">
                          {player.status.hp || 0} / {player.status.maxHp || 1} ({Math.round(((player.status.hp || 0) / (player.status.maxHp || 1)) * 100)}%)
                        </span>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section >

      <section>
        <h2 className="text-gray-200 font-bold mb-4">Recent Players</h2>
        <div className="border border-[#333] bg-[#1e1e1e] overflow-x-auto custom-scrollbar">
          <table className="session-table min-w-[600px]">
            <thead>
              <tr>
                <th className="w-1/3">Username</th>
                <th className="w-1/3">Level</th>
                <th className="w-1/3">Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {recentPlayers.length === 0 && (
                <tr>
                  <td colSpan={3} className="text-center text-gray-500 py-4">No recent players tracked yet.</td>
                </tr>
              )}
              {recentPlayers.map((player, i) => {
                const dateObj = new Date(player.date);
                const dateStr = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                return (
                  <tr
                    key={i}
                    className={`cursor-pointer transition-colors ${currentInspectedName === player.name ? 'player-row-current' : 'hover:bg-white/5'}`}
                    onClick={() => onInspect(player)}
                  >
                    <td>{player.name}</td>
                    <td>{player.name ? player.status.level : ''}</td>
                    <td className="text-xs text-gray-400">{dateStr}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section >

      <div className={`grid ${selectedGame === 'ELDEN_RING' ? 'grid-cols-3' : 'grid-cols-2'} gap-4`}>
        {selectedGame === 'ELDEN_RING' && (
          <button
            className="action-btn"
            onClick={() => fixInfiniteLoading(selectedGame)}
          >
            Fix Infinite Loading Screen
          </button>
        )}
        <button
          className="action-btn"
          onClick={() => quitToMenu(selectedGame)}
        >
          Quit To Main Menu
        </button>
        <button
          className="action-btn"
          onClick={() => toggleFogWall(selectedGame)}
        >
          Fog Wall Anim
        </button>
      </div>
    </div >
  );
};

function getCategoryForSlot(game: GameType, slotId: string): string | undefined {
  const mapping = SLOT_CSV_MAPPING[game];
  if (!mapping) return undefined;

  let type: string | undefined;

  const s = slotId.toLowerCase();

  if (s.startsWith('weapon_r')) type = 'WEAPON_R';
  else if (s.startsWith('weapon_l')) type = 'WEAPON_L';
  else if (s.startsWith('ammo_arrow') || s.startsWith('ammo_1')) type = 'AMMO_ARROW';
  else if (s.startsWith('ammo_bolt') || s.startsWith('ammo_2')) type = 'AMMO_BOLT';
  else if (s === 'head') type = 'ARMOR_HEAD';
  else if (s === 'chest') type = 'ARMOR_CHEST';
  else if (s === 'hands') type = 'ARMOR_HANDS';
  else if (s === 'legs') type = 'ARMOR_LEGS';
  else if (s.startsWith('ring')) type = 'RING';
  else if (s.startsWith('talisman')) type = 'TALISMAN';
  else if (s === 'covenant') type = 'COVENANT';
  else if (s.startsWith('quick')) type = 'QUICK_ITEM';
  else if (s.startsWith('spell')) type = 'SPELL';
  else if (s.startsWith('physick')) type = 'PHYSICK';

  return type ? mapping[type] : undefined;
}

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'main' | 'build' | 'toolkit' | 'backup'>('main');
  const [selectedGame, setSelectedGame] = useState<GameType>('ELDEN_RING');
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [hoveredSlot, setHoveredSlot] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loadWithStats, setLoadWithStats] = useState(true);
  const [language, setLanguage] = useState('en');

  const [metadata, setMetadata] = useState<AppMetadata | null>(null);

  // Load config and metadata on mount
  useEffect(() => {
    getConfig().then(cfg => {
      if (cfg.language) setLanguage(cfg.language);
    });
    getMetadata().then(setMetadata);
  }, []);

  const [localBuild, setLocalBuild] = useState<Build>({
    id: '',
    name: '',
    slots: {}
  });

  const [localStatus, setLocalStatus] = useState<StatusState>({
    level: 0,
    secondary: 0,
    journey: 0,
    covenant: '-',
    scadutreeBlessing: 0,
    reveredSpiritAsh: 0,
    attributes: {}
  });

  const [cheats, setCheats] = useState<CheatsState>({
    noWeight: false,
    noDead: false,
    noDamage: false,
    noHit: false,
    noStamina: false,
    noFP: false,
    noGoods: false,
    noArrow: false,
  });

  const [localName, setLocalName] = useState('');
  const [viewedName, setViewedName] = useState('');
  const [inspectedPlayer, setInspectedPlayer] = useState<PlayerData | null>(null);

  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  // Derived State
  const viewedStatus = (viewedName === localName || viewedName === '') ? localStatus : (inspectedPlayer?.status || localStatus);
  const viewedBuild = (viewedName === localName || viewedName === '') ? localBuild : (inspectedPlayer?.build || localBuild);

  // Search State
  const [searchResults, setSearchResults] = useState<Item[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  const [sessionPlayers, setSessionPlayers] = useState<PlayerData[]>([]);
  const [recentPlayers, setRecentPlayers] = useState<PlayerData[]>([]);
  const [pendingItem, setPendingItem] = useState<Item | null>(null);

  const [isGameDetected, setIsGameDetected] = useState(false);

  // Game Detection & Data Polling
  useEffect(() => {
    const interval = setInterval(async () => {
      const game = await detectGame();
      setIsGameDetected(!!game);

      if (game && game !== selectedGame) {
        setSelectedGame(game);
      }

      if (game) {
        // Efficiently fetch all players with full details in one request
        const allPlayers = await getPlayers(game);

        // Update Local Player from the list
        const local = allPlayers.find(p => p.isLocal);
        if (local) {
          // Sync name if uninitialized
          if (localName === '') {
            setLocalName(local.name);
            setViewedName(local.name);
          } else if (localName !== local.name) {
            setLocalName(local.name);
            if (viewedName === localName) setViewedName(local.name);
          }

          // Sync build and status ONLY if we are NOT in the build tab (prevent overwriting edits)
          if (activeTab !== 'build') {
            setLocalStatus(local.status);
            setLocalBuild(local.build);
          }
        } else {
          setLocalName('');
        }

        // Update Session Players
        const others = allPlayers.filter(p => !p.isLocal);
        setSessionPlayers(others);

        const recent = await getRecentPlayers(game);
        setRecentPlayers(recent);

      } else {
        setSessionPlayers([]);
        setRecentPlayers([]);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [selectedGame, activeTab, localName, viewedName]);

  // File Input for Load
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  // Prevent multiple save-file dialogs from opening due to click races.
  const saveBuildPickingRef = React.useRef(false);
  const [saveBuildPicking, setSaveBuildPicking] = useState(false);

  // Search Effect
  useEffect(() => {
    const doSearch = async () => {
      // If no slot selected or looking at another player, clear results
      if (!selectedSlot || (viewedName !== localName && viewedName !== '')) {
        setSearchResults([]);
        return;
      }

      const category = getCategoryForSlot(selectedGame, selectedSlot);
      if (!category) {
        setSearchResults([]);
        return;
      }

      setIsSearching(true);

      // Search with empty query implies "list all" (or first N) for that category
      const query = searchQuery;
      // Backend handles empty q + valid csv
      const results = await searchItems(selectedGame, query, category, 50);
      setSearchResults(results);
      setIsSearching(false);
    };

    // Debounce only if there is a query, otherwise load immediate? 
    // Actually debounce is fine, but maybe shorter for empty query?
    // Let's keep it simple: 300ms debounce is fine.
    const timeout = setTimeout(doSearch, 300);
    return () => clearTimeout(timeout);
  }, [searchQuery, selectedSlot, selectedGame, viewedName, localName]);



  const localPlayer: PlayerData = {
    name: localName,
    status: localStatus,
    build: localBuild,
    isLocal: true
  };

  const handleInspect = (player: PlayerData) => {
    if (player.isLocal) {
      // If inspecting self, reset to local view state (editable)
      setViewedName(localName);
      setInspectedPlayer(null); // Clear inspected player so we fall back to local state
    } else {
      setViewedName(player.name);
      setInspectedPlayer(player);
    }
    setActiveTab('build');
  };

  const handleCopyBuild = () => {
    if (loadWithStats) {
      setLocalStatus(viewedStatus);
    }
    setLocalBuild({ ...viewedBuild, id: 'local-build', name: 'Imported Build' });

    // Switch to local view to see the copied build
    setViewedName(localName);
    setInspectedPlayer(null);
  };

  const isLocalView = viewedName === localName || viewedName === '' || (inspectedPlayer?.isLocal ?? false);

  const handleStatusChange = (path: string, value: string | number | boolean) => {
    if (!isLocalView) return;
    const newStatus = { ...localStatus, [path]: value };
    setLocalStatus(newStatus);
    // Fire and forget write (debounce would be better for prod but this is local)
    writeStats(selectedGame, 0, newStatus);
  };

  const handleAttributeChange = (name: string, value: number) => {
    if (!isLocalView) return;
    const newStatus = {
      ...localStatus,
      attributes: { ...localStatus.attributes, [name]: value }
    };
    setLocalStatus(newStatus);
    writeStats(selectedGame, 0, newStatus);
  };

  const toggleCheat = (key: keyof CheatsState) => {
    const newState = !cheats[key];
    setCheats(prev => ({ ...prev, [key]: newState }));
    apiToggleCheat(selectedGame, key, newState);
  };

  const handleSelectItem = (item: Item) => {
    if (!selectedSlot || !isLocalView) return;

    // Only ammo gets a safe default count; quick items default to "keep current quantity"
    // unless the user explicitly adjusts the slider (sets `count`).
    const newItem = selectedSlot.startsWith('ammo')
      ? { ...item, count: item.count ?? 99 }
      : { ...item };

    // Keep it as pending to allow customization (upgrades, etc.)
    setPendingItem(newItem);
    setSearchQuery('');
  };


  const handleSaveBuild = async () => {
    if (saveBuildPickingRef.current) return;
    saveBuildPickingRef.current = true;
    setSaveBuildPicking(true);
    try {
      // Open system file dialog
      const path = await browseSaveFile(localBuild.name || "my_build");
      if (!path) return; // User cancelled

      // Get the name from path for UI/internal naming if needed, though backend uses path
      // We can extract filename from path for the internal name if we want, but localBuild.name is current name
      // actually, let's keep localBuild.name as is or update it?
      // user might have typed a new name in the dialog.
      // For now, just save.

      const saveData = convertBuildToSaveFormat(selectedGame, localBuild.slots, localStatus);

      // We need to pass the path to the backend
      const name = localBuild.name || "build";
      const result = await saveBuild(name, saveData, path);

      if (result) {
        setAlertMsg(`Build saved to: ${path}`);
      } else {
        setAlertMsg("Failed to save build");
      }
    } finally {
      saveBuildPickingRef.current = false;
      setSaveBuildPicking(false);
    }
  };

  const handleLoadBuild = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const json = JSON.parse(e.target?.result as string);
        // Support both structure formats if accidentally nested or not
        // Support both structure formats if accidentally nested or not
        // unused 'content' var was here, effectively we just used json directly below or need content usage?
        // The original code used json.build checks. 
        // Let's see: if (!json.build && !json.equipment), maybe content logic was intended but unused.
        // I will keep the logic but remove unused assignment if possible. 
        // Actually, looking at original code: const content = ...; then if (json.build) ...
        // 'content' IS unused.

        if (json.build) {
          setLocalBuild(json.build);
          if (json.status) setLocalStatus(json.status);
          if (json.game) setSelectedGame(json.game);
          setAlertMsg(`Loaded build: ${file.name}`);
        } else if (json.equipment) {
          // Load External/Partial Build (e.g. Seamless Co-op or new save format)
          const enriched = await inspectBuild(selectedGame, json.equipment);
          const mappedSlots = mapBackendToFrontendSlots(selectedGame, enriched);

          setLocalBuild(prev => ({
            ...prev,
            slots: mappedSlots
          }));

          // Load stats from new format if present AND loadWithStats is checked
          if (json.stats && loadWithStats) {
            setLocalStatus(prev => ({
              ...prev,
              level: json.stats.level ?? prev.level,
              maxHp: json.stats.max_hp ?? prev.maxHp,
              scadutreeBlessing: json.shadow_of_erdtree?.scadutree_blessing ?? prev.scadutreeBlessing,
              reveredSpiritAsh: json.shadow_of_erdtree?.revered_spirit_ash_blessing ?? prev.reveredSpiritAsh,
              attributes: {
                ...prev.attributes,
                Vigor: json.stats.vigor ?? prev.attributes?.Vigor ?? 10,
                Mind: json.stats.mind ?? prev.attributes?.Mind ?? 10,
                Endurance: json.stats.endurance ?? prev.attributes?.Endurance ?? 10,
                Strength: json.stats.strength ?? prev.attributes?.Strength ?? 10,
                Dexterity: json.stats.dexterity ?? prev.attributes?.Dexterity ?? 10,
                Intelligence: json.stats.intelligence ?? prev.attributes?.Intelligence ?? 10,
                Faith: json.stats.faith ?? prev.attributes?.Faith ?? 10,
                Arcane: json.stats.arcane ?? prev.attributes?.Arcane ?? 10,
              }
            }));
          }

          setAlertMsg(`Loaded build: ${file.name}\nReview slots and click 'Apply Build' to commit.`);
        } else {
          setAlertMsg("Invalid build file format.");
        }
      } catch (err) {
        console.error(err);
        setAlertMsg("Failed to parse build file.");
      }
    };
    reader.readAsText(file);
    // Reset
    event.target.value = '';
  };

  const handleApplyBuild = async () => {
    try {
      // IMPORTANT: Apply only the diffs vs current in-game equipment.
      // This avoids mass "unequip" calls (from saved builds that include many explicit empty slots),
      // which can crash the game.
      const players = await getPlayers(selectedGame);
      const currentLocal = players.find(p => p.isLocal);
      const currentSlots = currentLocal?.build?.slots || {};

      const slotsToApply: Record<string, Item | null> = {};
      const desiredSlots = localBuild.slots || {};

      const effectiveId = (it: Item | null | undefined): number | null => {
        if (!it?.id) return null;
        const raw = parseInt(it.id);
        if (Number.isNaN(raw) || raw <= 0) return null;

        // Normalize to the same "final id" that `writeBuild()` will send to the backend.
        // This prevents false diffs between:
        // - current equipped item IDs (often already include upgrade)
        // - chosen items from search (often base ID) + separate `upgrade` field
        if (typeof it.upgrade === 'number') {
          const mod = selectedGame === 'ELDEN_RING' ? 100 : 10;
          const base = raw - (raw % mod);
          return base + it.upgrade;
        }
        return raw;
      };

      const isSameItem = (a: Item | null | undefined, b: Item | null | undefined) => {
        if (!a && !b) return true;
        if (!a || !b) return false;
        const aId = effectiveId(a);
        const bId = effectiveId(b);
        return aId === bId &&
          (a.gemId ?? 0) === (b.gemId ?? 0) &&
          (a.count ?? 1) === (b.count ?? 1);
      };

      // Only consider keys explicitly present in the desired build state.
      // (Loaded build JSONs may contain null keys for every empty slot.)
      for (const feKey of Object.keys(desiredSlots)) {
        const want = desiredSlots[feKey];
        const cur = currentSlots[feKey] ?? null;
        if (!isSameItem(want, cur)) {
          slotsToApply[feKey] = want ?? null;
        }
      }

      await writeBuild(selectedGame, 0, slotsToApply, localStatus);
      setAlertMsg('Build applied to active session!');
    } catch (e) {
      console.error('Failed to apply build', e);
      setAlertMsg('Failed to apply build.');
    }
  };

  const currentSelectedItem = useMemo(() => {
    if (!selectedSlot) return null;
    return viewedBuild.slots[selectedSlot] || null;
  }, [selectedSlot, viewedBuild.slots]);

  const configItem = pendingItem || currentSelectedItem;

  const handleClearSlot = useCallback((feKey: string) => {
    if (!isLocalView) return;
    setLocalBuild(prev => ({
      ...prev,
      slots: { ...prev.slots, [feKey]: null }
    }));
    if (feKey === 'covenant') {
      setLocalStatus(prev => ({ ...prev, covenant: '-' }));
    }
  }, [isLocalView]);

  const handleConfirmEquip = () => {
    if (!pendingItem || !selectedSlot) return;
    setLocalBuild(prev => ({
      ...prev,
      slots: { ...prev.slots, [selectedSlot]: pendingItem }
    }));
    setPendingItem(null);
    setSearchQuery(''); // Close search results or clear query?
    // Optionally switch focus?
    setActiveTab('build'); // Ensure we are here.
  };

  // Listen for "R" key to clear slot
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (activeTab === 'build' && isLocalView) {
        if (e.code === 'KeyR') {
          if (hoveredSlot) {
            handleClearSlot(hoveredSlot);
          } else if (selectedSlot) {
            handleClearSlot(selectedSlot);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, isLocalView, selectedSlot, hoveredSlot, handleClearSlot]); // Dependencies for closure freshness

  return (
    <div className="min-h-screen textured-bg flex flex-col overflow-hidden">
      <header className="min-h-16 flex items-center justify-between px-8 bg-black/80 border-b border-[#2a2a2a] shrink-0 z-50 flex-wrap gap-y-4 py-2">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-[#bfa571]/20 border border-[#bfa571]/50 rounded-full flex items-center justify-center shrink-0">
              <span className="text-[#bfa571] font-bold text-xl fantasy-font">P</span>
            </div>
            <h1 className="text-xl md:text-2xl font-bold tracking-[0.2em] uppercase text-gray-100 fantasy-font whitespace-nowrap">Phantom Toolkit</h1>
          </div>
        </div>

        <div className="flex bg-black/40 border border-white/10 rounded-sm p-0.5 shrink-0 items-center gap-2">
          <LanguageSelector
            currentLanguage={language}
            onLanguageChange={(lang) => setLanguage(lang)}
          />
          <div className="w-px h-4 bg-white/10 mx-1"></div>
          {(['DARK_SOULS_3', 'ELDEN_RING'] as GameType[]).map(g => (
            <button
              key={g}
              onClick={() => setSelectedGame(g)}
              className={`px-3 py-1 text-[10px] fantasy-font tracking-widest uppercase transition-all ${selectedGame === g ? 'bg-[#bfa571] text-black' : 'text-gray-500 hover:text-gray-300'}`}
            >
              {g.replace('_', ' ')}
            </button>
          ))}
        </div>

        <nav className="flex gap-1 overflow-x-auto no-scrollbar">
          <button onClick={() => setActiveTab('main')} className={`px-4 py-2 transition-all fantasy-font uppercase tracking-widest text-xs border-b-2 whitespace-nowrap ${activeTab === 'main' ? 'text-[#bfa571] border-[#bfa571]' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>Main</button>
          <button onClick={() => setActiveTab('build')} className={`px-4 py-2 transition-all fantasy-font uppercase tracking-widest text-xs border-b-2 whitespace-nowrap ${activeTab === 'build' ? 'text-[#bfa571] border-[#bfa571]' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>Creation</button>
          <button onClick={() => setActiveTab('toolkit')} className={`px-4 py-2 transition-all fantasy-font uppercase tracking-widest text-xs border-b-2 whitespace-nowrap ${activeTab === 'toolkit' ? 'text-[#bfa571] border-[#bfa571]' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>Toolkit</button>
          <button onClick={() => setActiveTab('backup')} className={`px-4 py-2 transition-all fantasy-font uppercase tracking-widest text-xs border-b-2 whitespace-nowrap ${activeTab === 'backup' ? 'text-[#bfa571] border-[#bfa571]' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>Backup</button>
        </nav>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className={`shrink - 0 h - full transition - all duration - 300 ${activeTab === 'backup' ? 'w-0 overflow-hidden opacity-0' : 'w-[320px] opacity-100'} `}>
          <StatusPanel
            playerName={viewedName}
            status={viewedStatus}
            game={selectedGame}
            onStatusChange={handleStatusChange}
            onAttributeChange={handleAttributeChange}
            isReadOnly={!isLocalView}
            onCopy={handleCopyBuild}
          />
        </aside>

        {activeTab === 'main' && (
          <MainTab
            currentInspectedName={viewedName}
            onInspect={handleInspect}
            sessionPlayers={sessionPlayers}
            recentPlayers={recentPlayers}
            localPlayer={localPlayer}
            selectedGame={selectedGame}
          />
        )}

        {activeTab === 'toolkit' && (
          <ToolkitTab cheats={cheats} onToggle={toggleCheat} selectedGame={selectedGame} />
        )}

        {activeTab === 'backup' && (
          <BackupTab game={selectedGame === 'ELDEN_RING' ? 'eldenring' : 'ds3'} />
        )}

        {activeTab === 'build' && (
          <>
            <section className="flex-1 flex flex-col items-center justify-center p-8 overflow-y-auto custom-scrollbar">
              <div className="mb-6 w-full max-w-2xl flex flex-col items-center">
                <h2 className="text-xl fantasy-font text-[#bfa571] uppercase tracking-widest text-center">
                  {isLocalView ? 'Equipment' : `${viewedName}'s Build`}
                </h2 >
                <div className="status-header-line w-64 mx-auto"></div>

                {
                  (isLocalView) && (
                    <div className="flex flex-col items-center gap-4 mt-2 mb-4 bg-black/20 p-4 border border-white/5 rounded backdrop-blur-sm">
                      <div className="flex items-center gap-4">
                        <button
                          onClick={handleApplyBuild}
                          className="px-8 py-2 bg-[#bfa571] border border-[#bfa571] text-black fantasy-font uppercase text-xs tracking-[0.2em] hover:brightness-110 transition-all font-bold shadow-[0_0_15px_rgba(191,165,113,0.3)]"
                        >
                          Apply Build
                        </button>
                        <button
                          onClick={handleSaveBuild}
                          disabled={saveBuildPicking}
                          className="px-6 py-2 bg-[#bfa571]/10 border border-[#bfa571] text-[#bfa571] fantasy-font uppercase text-xs tracking-widest hover:bg-[#bfa571] hover:text-black transition-all font-bold disabled:opacity-50 disabled:hover:bg-[#bfa571]/10 disabled:hover:text-[#bfa571]"
                        >
                          Save Build
                        </button>
                        <button
                          onClick={handleLoadBuild}
                          className="px-6 py-2 bg-white/5 border border-white/20 text-gray-300 fantasy-font uppercase text-xs tracking-widest hover:bg-white/10 hover:border-white/40 transition-all font-bold"
                        >
                          Load Build
                        </button>
                      </div>

                      <label className="flex items-center gap-3 cursor-pointer group">
                        <div className="relative w-5 h-5">
                          <input
                            type="checkbox"
                            checked={loadWithStats}
                            onChange={(e) => setLoadWithStats(e.target.checked)}
                            className="sr-only"
                          />
                          <div className={`w-5 h-5 border transition-all ${loadWithStats ? 'border-[#bfa571] bg-[#bfa571]/20' : 'border-white/20 bg-transparent'}`}>
                            {loadWithStats && (
                              <div className="absolute inset-0 flex items-center justify-center">
                                <div className="w-2 h-2 bg-[#bfa571] rotate-45" />
                              </div>
                            )}
                          </div>
                        </div>
                        <span className="text-[10px] fantasy-font text-gray-400 group-hover:text-gray-200 uppercase tracking-widest transition-colors font-bold">Load with stats</span>
                      </label>
                    </div>
                  )
                }
              </div >

              <EquipmentGrid
                slots={viewedBuild.slots}
                selectedSlot={selectedSlot}
                onHoverSlot={setHoveredSlot}
                game={selectedGame}
                onSelectSlot={(id) => { setSelectedSlot(id); setSearchQuery(''); setPendingItem(null); }}
              />
            </section >

            <aside className="w-[420px] shrink-0 flex flex-col border-l border-[#2a2a2a] bg-black/40">
              {/* TOP: Configuration Panel (if pending or configuring equipped) */}
              {(configItem) && (
                <div className="h-auto shrink-0 border-b border-[#2a2a2a] bg-black/60 p-4">
                  <div className="flex flex-col gap-4">
                    {/* Configuration / Preview Header */}
                    <div className="flex gap-4">
                      <div className="w-20 h-20 soulslike-slot item-glow flex items-center justify-center flex-shrink-0 active">
                        {configItem.image && <img src={configItem.image} className="w-16 h-16 object-contain" />}
                      </div>
                      <div className="flex-1">
                        <h4 className="fantasy-font text-gray-100 uppercase text-base leading-tight">
                          {configItem.name} {configItem.upgrade && !configItem.name.includes('+') ? `+${configItem.upgrade}` : ''}
                        </h4>

                        {/* Stats */}
                        <div className="flex justify-between items-center mt-2 border-b border-white/5 pb-1">
                          <span className="text-[10px] text-gray-500 uppercase tracking-widest">ID</span>
                          <span className="text-xs text-[#bfa571] font-bold">{configItem.id || '--'}</span>
                        </div>
                      </div>
                    </div>

                    {/* Pending Config Logic */}
                    {pendingItem ? (
                      <>
                        <WeaponConfig
                          game={selectedGame}
                          item={configItem}
                          onUpdate={(updated) => {
                            setPendingItem(updated);
                            if (selectedSlot) {
                              setLocalBuild(prev => ({
                                ...prev,
                                slots: { ...prev.slots, [selectedSlot]: updated }
                              }));
                            }
                          }}
                        />
                        {selectedSlot && (selectedSlot.startsWith('quick') || selectedSlot.startsWith('ammo')) && (
                          <div className="p-4 bg-black/60 border border-[#bfa571]/30 rounded mt-4 backdrop-blur-sm">
                            <h3 className="text-lg font-bold text-[#bfa571] mb-2 font-serif">Configure Quantity</h3>
                            <div className="flex justify-between mb-1">
                              <label className="text-gray-300 text-sm">Quantity</label>
                              <span className="text-[#bfa571] font-bold font-mono">
                                {configItem.count ?? (selectedSlot?.startsWith('ammo') ? 99 : 'KEEP')}
                              </span>
                            </div>
                            <input
                              type="range"
                              min="1"
                              max="99"
                              value={configItem.count ?? (selectedSlot?.startsWith('ammo') ? 99 : 1)}
                              onChange={(e) => {
                                const newCount = parseInt(e.target.value);
                                const updated = { ...configItem, count: newCount };
                                setPendingItem(updated);
                                if (selectedSlot) {
                                  setLocalBuild(prev => ({
                                    ...prev,
                                    slots: { ...prev.slots, [selectedSlot]: updated }
                                  }));
                                }
                              }}
                              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-[#bfa571]"
                            />
                            <div className="flex justify-between text-xs text-gray-500 mt-1">
                              <span>1</span>
                              <span>99</span>
                            </div>
                          </div>
                        )}

                        <div className="flex gap-2 w-full mt-2">
                          <button
                            onClick={handleConfirmEquip}
                            className="flex-1 py-2 bg-[#bfa571] text-black fantasy-font uppercase tracking-widest text-xs font-bold hover:brightness-110"
                          >
                            Confirm & Equip
                          </button>
                          <button
                            onClick={() => {
                              setPendingItem(null);
                            }}
                            className="flex-1 py-2 bg-white/10 text-gray-300 fantasy-font uppercase tracking-widest text-xs font-bold hover:bg-white/20"
                          >
                            Dismiss
                          </button>
                        </div>
                      </>
                    ) : (
                      /* Edit Button for Equipped Items */
                      (isLocalView) && configItem.maxUpgrade && configItem.maxUpgrade > 0 && (
                        <button
                          onClick={() => setPendingItem({ ...configItem })}
                          className="w-full mt-4 py-2 bg-white/5 border border-white/10 text-gray-300 fantasy-font uppercase tracking-widest text-xs font-bold hover:bg-white/10 hover:text-[#bfa571] hover:border-[#bfa571]/50 transition-all flex items-center justify-center gap-2"
                        >
                          <span>⚙</span> Customize Weapon
                        </button>
                      )
                    )}

                    {!pendingItem && <p className="text-xs text-gray-400 italic leading-relaxed max-h-20 overflow-y-auto">{configItem.description}</p>}
                  </div>
                </div>
              )}

              <div className="p-4 bg-black/60 border-b border-[#2a2a2a]">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="fantasy-font text-[#bfa571] uppercase tracking-widest text-sm">
                    {selectedSlot ? selectedSlot.replace(/_/g, ' ') : 'Select a Slot'}
                  </h3>
                  {selectedSlot && (isLocalView) && (
                    <button onClick={() => handleClearSlot(selectedSlot)} className="text-[10px] uppercase text-gray-500 hover:text-white transition-colors border border-white/10 px-2 py-1">Clear Slot</button>
                  )}
                </div>
                <input
                  type="text"
                  placeholder={isLocalView ? "SEARCH ITEM..." : "READ ONLY MODE"}
                  disabled={!isLocalView}
                  className={`w-full search-input py-2 px-4 text-xs tracking-widest uppercase fantasy-font bg-white/5 border border-white/10 outline-none focus:border-[#bfa571] transition-colors ${!isLocalView ? 'opacity-50 cursor-not-allowed' : ''}`}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
                {isSearching ? (
                  <div className="h-full flex flex-col items-center justify-center opacity-50">
                    <p className="text-xs fantasy-font uppercase tracking-widest">Searching...</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-5 gap-1.5">
                    {searchResults.map((item) => {
                      const isSelectedInSlot = currentSelectedItem?.id === item.id;
                      return (
                        <div
                          key={item.id}
                          onClick={() => (isLocalView) && handleSelectItem(item)}
                          className={`aspect-square soulslike-slot flex items-center justify-center transition-all relative ${isSelectedInSlot ? 'item-glow active' : ''} ${(isLocalView) ? 'cursor-pointer hover:selected-highlight' : 'opacity-80 cursor-default'}`}
                          title={item.name}
                        >
                          {item.image ? (
                            <img src={item.image} alt={item.name} className={`w-[85%] h-[85%] object-contain p-1 transition-all ${isSelectedInSlot ? 'scale-110' : ''}`} />
                          ) : (
                            <span className="text-[9px] text-center text-gray-500">{item.name}</span>
                          )}
                        </div>
                      );
                    })}
                    {searchResults.length === 0 && searchQuery && (
                      <div className="col-span-5 text-center mt-10 opacity-50 text-xs text-gray-400">
                        NO ITEMS FOUND
                      </div>
                    )}
                  </div>
                )}
              </div>
            </aside>
          </>
        )}
      </main >
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        accept=".json"
        className="hidden"
      />
      <AlertModal
        open={!!alertMsg}
        message={alertMsg || ''}
        onClose={() => setAlertMsg(null)}
      />

      {/* Footer */}
      <div className="border-t border-[#333] bg-[#0c0c0c] px-4 py-2 flex justify-between items-center text-[10px] text-gray-600 inter-font select-none">
        <div className="flex gap-4">
          <span>{metadata?.name} v{metadata?.version}</span>
          {metadata?.authors?.length > 0 && (
            <span>by {metadata.authors.join(', ')}</span>
          )}
        </div>
        <div className="flex gap-4 items-center">
          {isGameDetected ? (
            <>
              <span className="text-emerald-700/80">●</span>
              <span>Attached to {selectedGame === 'ELDEN_RING' ? 'Elden Ring' : 'Dark Souls 3'}</span>
              <span className="text-gray-700">|</span>
              <span>{localName || 'Main Menu'}</span>
            </>
          ) : (
            <>
              <span className="text-red-900/50">●</span>
              <span>Waiting for {selectedGame === 'ELDEN_RING' ? 'Elden Ring' : 'Dark Souls 3'}...</span>
            </>
          )}
        </div>
      </div>
    </div >
  );
};

export default App;
