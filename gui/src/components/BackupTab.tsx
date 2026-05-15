import React, { useState, useEffect, useRef, useCallback } from 'react';
import { BackupEntry, BackupSettings } from '../types';
import {
  getBackupSettings, saveBackupSettings, autoFindSavePaths,
  listBackups, createBackup, loadBackup, deleteBackup,
  pinBackup, renameBackup, getScreenshotUrl,
  startAutoBackup, stopAutoBackup, getAutoBackupStatus,
  listSaveFiles, browseDirectory, setActiveBackup,
} from '../api';
import { ConfirmationModal, InputModal } from './Modal';
import { TabActionButton } from '../App';

interface Props {
  game?: string;
}

const KeybindInput: React.FC<{
  label: string;
  value: string;
  onChange: (val: string) => void;
}> = ({ label, value, onChange }) => {
  const [recording, setRecording] = useState(false);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!recording) return;
    e.preventDefault();
    e.stopPropagation();

    if (e.key === 'Escape') {
      setRecording(false);
      return;
    }

    if (e.key === 'Backspace' || e.key === 'Delete') {
      onChange('');
      setRecording(false);
      return;
    }

    const modifiers = [];
    if (e.ctrlKey) modifiers.push('ctrl');
    if (e.shiftKey) modifiers.push('shift');
    if (e.altKey) modifiers.push('alt');

    let key = e.key.toLowerCase();
    if (key === 'control' || key === 'shift' || key === 'alt') return; 

    if (key === ' ') key = 'space';

    const combo = [...modifiers, key].join('+');
    onChange(combo);
    setRecording(false);
  };

  return (
    <div className="flex flex-col">
      <label className="text-[10px] text-gray-500 mb-1 uppercase tracking-widest fantasy-font font-bold">{label}</label>
      <div className="flex gap-2">
        <input
          type="text"
          value={recording ? 'PRESS KEYS...' : (value || 'NONE')}
          readOnly
          className={`flex-1 bg-black/40 border ${recording ? 'border-[#bfa571]' : 'border-white/10'} rounded-sm px-3 py-2 text-xs text-gray-200 focus:outline-none cursor-pointer fantasy-font tracking-widest transition-all`}
          onClick={() => setRecording(true)}
          onKeyDown={handleKeyDown}
          onBlur={() => setRecording(false)}
        />
        {value && (
          <button
            onClick={() => onChange('')}
            className="px-2 bg-white/5 border border-white/10 rounded-sm text-gray-500 hover:text-red-400 transition-colors"
            title="Clear"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
};

const BackupTab: React.FC<Props> = ({ game = '' }) => {
  // Settings
  const [settings, setSettings] = useState<BackupSettings>({
    save_directory: '',
    backup_directory: '',
    save_file_type: '.sl2',
    save_file_name: '',
    backup_method: 0,
    auto_backup_interval: 5,
    sleep_between_saves: 10,
    max_backups: 20,
    quit_to_menu_before_load: false,
    notification_volume: 50,
    keybind_save: '',
    keybind_load: '',
    keybind_auto_start: '',
    keybind_auto_stop: '',
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Backups
  const [pinnedBackups, setPinnedBackups] = useState<BackupEntry[]>([]);
  const [regularBackups, setRegularBackups] = useState<BackupEntry[]>([]);
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null);

  // Screenshot preview
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);

  // Auto-backup
  const [autoRunning, setAutoRunning] = useState(false);
  const lastNewestRef = useRef<string | null>(null);

  // Status
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  // Directory browser modal
  const [dirPicking, setDirPicking] = useState(false);
  const dirPickingRef = useRef(false);

  // Auto-find & save files
  const [autoFindResults, setAutoFindResults] = useState<{ path: string; game: string; steam_id: string }[] | null>(null);
  const [availableSaveFiles, setAvailableSaveFiles] = useState<string[]>([]);

  // Context menu
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; item: BackupEntry } | null>(null);

  // Modals
  const [confirmModal, setConfirmModal] = useState<{ open: boolean; title: string; message: string; isDanger?: boolean; onConfirm: () => void } | null>(null);
  const [inputModal, setInputModal] = useState<{ open: boolean; title: string; initialValue: string; label?: string; onConfirm: (val: string) => void } | null>(null);

  // ---- API ----
  const loadSettingsFromBackend = useCallback(async () => {
    try {
      const s = await getBackupSettings(game);
      setSettings(s);
    } catch { /* ignore */ }
  }, [game]);

  const fetchSaveFiles = useCallback(async (dir: string, ext: string) => {
    try {
      const data = await listSaveFiles(dir, ext);
      setAvailableSaveFiles(data.files);
      setSettings(s => {
        if (data.files.length > 0 && (!s.save_file_name || !data.files.includes(s.save_file_name))) {
          return { ...s, save_file_name: data.files[0], save_file_type: '*' };
        }
        return s;
      });
    } catch { setAvailableSaveFiles([]); }
  }, []);

  const checkAutoStatus = useCallback(async () => {
    try {
      const data = await getAutoBackupStatus();
      setAutoRunning(data.running);
    } catch { /* ignore */ }
  }, []);

  const refreshBackups = useCallback(async () => {
    try {
      const data = await listBackups(game);
      if (data.regular.length > 0) {
        const newestRegular = data.regular[0].name;
        if (lastNewestRef.current !== newestRegular) {
          setSelectedBackup(newestRegular);
        }
        lastNewestRef.current = newestRegular;
      }
      setPinnedBackups(data.pinned.map((b, i) => ({ ...b, id: `p${i}` })));
      setRegularBackups(data.regular.map((b, i) => ({ ...b, id: `r${i}` })));
    } catch { /* ignore */ }
  }, [game]);

  // ---- Init ----
  useEffect(() => {
    loadSettingsFromBackend();
    refreshBackups();
    checkAutoStatus();
  }, [game, loadSettingsFromBackend, refreshBackups, checkAutoStatus]);

  useEffect(() => {
    if (settings.save_directory) {
      fetchSaveFiles(settings.save_directory, '*');
    } else {
      setAvailableSaveFiles([]);
    }
  }, [settings.save_directory, fetchSaveFiles]);

  useEffect(() => {
    const h = () => setCtxMenu(null);
    window.addEventListener('click', h);
    return () => window.removeEventListener('click', h);
  }, []);

  // SNR-Snappy UI Refresh: Sync with game saves and background activity
  useEffect(() => {
    refreshBackups(); // Initial fetch
    const interval = setInterval(() => {
      refreshBackups();
      checkAutoStatus();
    }, 800);
    return () => clearInterval(interval);
  }, [game, refreshBackups, checkAutoStatus]);

  useEffect(() => {
    if (!selectedBackup) { setScreenshotUrl(null); return; }
    const all = [...pinnedBackups, ...regularBackups];
    const entry = all.find(b => b.name === selectedBackup);
    if (entry?.hasScreenshot) {
      setScreenshotUrl(getScreenshotUrl(entry.name, game));
    } else {
      setScreenshotUrl(null);
    }
  }, [selectedBackup, pinnedBackups, regularBackups, game]);

  // Sync active selection to backend for global hotkeys
  useEffect(() => {
    if (selectedBackup) {
      setActiveBackup(selectedBackup, game).catch(() => { });
    }
  }, [selectedBackup, game]);
  const handleSaveSettings = async () => {
    try {
      await saveBackupSettings(settings, game);
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch { setStatusMsg('Failed to save settings'); }
  };

  const handleAutoFind = async () => {
    try {
      const data = await autoFindSavePaths(game);
      if (data.paths.length === 0) { setStatusMsg('No save locations found'); return; }
      if (data.paths.length === 1) {
        setSettings(s => ({ ...s, save_directory: data.paths[0].path }));
        setStatusMsg(`Found: ${data.paths[0].path}`);
      } else {
        setAutoFindResults(data.paths);
      }
    } catch { setStatusMsg('Auto-find failed'); }
  };

  const handleBrowse = async (field: 'save' | 'backup') => {
    if (dirPickingRef.current) return;
    dirPickingRef.current = true;
    setDirPicking(true);
    try {
      const initial = field === 'save' ? settings.save_directory : settings.backup_directory;
      const path = await browseDirectory(initial);
      if (!path) return;
      setSettings(s => ({
        ...s,
        [field === 'save' ? 'save_directory' : 'backup_directory']: path
      }));
    } catch { /* ignore */ } finally {
      dirPickingRef.current = false;
      setDirPicking(false);
    }
  };

  const handleCreate = async () => {
    setLoading(true);
    setStatusMsg('Creating backup...');
    try {
      const result = await createBackup(game, true);
      setStatusMsg(`Backup created: ${result.name}`);
      await refreshBackups();
      setSelectedBackup(result.name);
    } catch (e) {
      const err = e as Error;
      setStatusMsg(`Error: ${err.message}`);
    } finally { setLoading(false); }
  };

  const handleLoad = async () => {
    if (!selectedBackup) return;
    // Centralized logic is now in the backend. 
    // If "Safe Load" is enabled, the backend will trigger quitToMenu() and wait 1s.
    const isSafeLoad = settings.quit_to_menu_before_load;
    
    setConfirmModal({
      open: true,
      title: isSafeLoad ? 'Safe Load' : 'Load Backup',
      message: isSafeLoad 
        ? `Safe Load Active: This will return you to the Main Menu and restore "${selectedBackup}".\n\nContinue?`
        : `WARNING: You should be in the Main Menu before loading a save!\n\nRestore "${selectedBackup}" now?`,
      isDanger: !isSafeLoad,
      onConfirm: async () => {
        setConfirmModal(null);
        setLoading(true);
        try {
          if (isSafeLoad) setStatusMsg('Quitting & Restoring...');
          else setStatusMsg(`Restoring: ${selectedBackup}...`);
          
          await loadBackup(selectedBackup, game);
          setStatusMsg(`Restored: ${selectedBackup}`);
        } catch (e) {
          const err = e as Error;
          setStatusMsg(`Error: ${err.message}`);
        } finally { setLoading(false); }
      }
    });
  };

  const handleDelete = async (name?: string) => {
    const target = name || selectedBackup;
    if (!target) return;
    setConfirmModal({
      open: true,
      title: 'Delete Backup',
      message: `Are you sure you want to delete "${target}"?`,
      isDanger: true,
      onConfirm: async () => {
        setConfirmModal(null);
        try {
          await deleteBackup(target, game);
          if (selectedBackup === target) setSelectedBackup(null);
          setStatusMsg(`Deleted: ${target}`);
          await refreshBackups();
        } catch (e) {
          const err = e as Error;
          setStatusMsg(`Error: ${err.message}`);
        }
      }
    });
  };

  const handlePin = async (name: string, pin: boolean) => {
    try { await pinBackup(name, pin, game); await refreshBackups(); }
    catch (e) {
      const err = e as Error;
      setStatusMsg(`Error: ${err.message}`);
    }
  };

  const handleRename = async (name: string) => {
    setInputModal({
      open: true,
      title: 'Rename Backup',
      initialValue: name.replace('.zip', ''),
      label: 'New Name:',
      onConfirm: async (newName) => {
        setInputModal(null);
        if (!newName || newName === name.replace('.zip', '')) return;
        try { await renameBackup(name, newName, game); await refreshBackups(); setSelectedBackup(newName.endsWith('.zip') ? newName : `${newName}.zip`); }
        catch (e) {
          const err = e as Error;
          setStatusMsg(`Error: ${err.message}`);
        }
      }
    });
  };

  const handleStartAuto = async () => {
    try {
      await startAutoBackup(game);
      setAutoRunning(true);
      setStatusMsg('Auto-backup started');
    } catch (e) {
      const err = e as Error;
      setStatusMsg(`Error: ${err.message}`);
    }
  };

  const handleStopAuto = async () => {
    try {
      await stopAutoBackup();
      setAutoRunning(false);
      setStatusMsg('Auto-backup stopped');
    } catch (e) {
      const err = e as Error;
      setStatusMsg(`Error: ${err.message}`);
    }
  };

  // ---- Sub-components ----

  const BackupCard: React.FC<{ entry: BackupEntry, isPinned: boolean }> = ({ entry, isPinned }) => {
    const isSelected = selectedBackup === entry.name;
    return (
      <div
        onClick={() => setSelectedBackup(entry.name)}
        onContextMenu={(e) => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, item: entry }); }}
        className={`
          group relative rounded border mb-3 transition-all duration-300 cursor-pointer overflow-hidden
          ${isSelected 
            ? 'border-[#bfa571] shadow-[0_5px_15px_rgba(191,165,113,0.2)] bg-[#bfa571]/5' 
            : 'border-white/5 hover:border-white/10 bg-black/20'}
        `}
      >
        <div className="h-[100px] w-full bg-black/60 relative">
          {entry.hasScreenshot ? (
            <img 
              src={getScreenshotUrl(entry.name, game)} 
              alt={entry.name} 
              className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" 
              loading="lazy"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-[10px] fantasy-font text-gray-700 tracking-widest">
              NO PREVIEW
            </div>
          )}
          
          {/* Overlay Info */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent flex flex-col justify-end p-2">
            <div className="flex justify-between items-end gap-2">
              <div className="flex-1 min-w-0">
                <h4 className={`text-[10px] fantasy-font tracking-[0.2em] truncate uppercase mb-0.5 ${isSelected ? 'text-[#bfa571]' : 'text-gray-300'}`}>
                  {entry.name.replace('.zip', '')}
                </h4>
                <span className="text-[8px] text-gray-500 uppercase tracking-widest block">{entry.date}</span>
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); handlePin(entry.name, !isPinned); }}
                className={`transition-all p-1 text-xs ${isPinned ? 'text-[#bfa571]' : 'text-gray-600 hover:text-white opacity-40 hover:opacity-100'}`}
              >
                {isPinned ? '★' : '☆'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };


  return (
    <div className="flex-1 h-full flex flex-col overflow-hidden inter-font p-6" style={{ fontFamily: "'Inter', sans-serif" }}>
      
      {/* Header Info Bar */}
      <div className="flex justify-between items-center mb-6 px-2">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <h2 className="text-xl fantasy-font text-gray-100 tracking-[0.2em] uppercase">Backup Archives</h2>
            <div className="status-header-line w-24 mb-0 opacity-50"></div>
          </div>
          
          <div className={`flex items-center gap-2 px-3 py-1 rounded-full border ${autoRunning ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
            <div className={`w-2 h-2 rounded-full ${autoRunning ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
            <span className={`text-[10px] fantasy-font tracking-widest uppercase font-bold ${autoRunning ? 'text-emerald-400' : 'text-red-400'}`}>
              Auto-Backup {autoRunning ? 'Active' : 'Inactive'}
            </span>
          </div>
        </div>
        
        {statusMsg && (
          <div className="text-[10px] fantasy-font tracking-widest text-[#bfa571] animate-pulse bg-white/5 px-4 py-1 border border-[#bfa571]/20 rounded-sm italic">
            {statusMsg}
          </div>
        )}
      </div>

      <div className="flex-1 flex gap-8 overflow-hidden min-h-0">
        
        {/* Left Pane: Visual Archive Gallery */}
        <div className="w-[350px] flex flex-col min-h-0 relative">
          <div className="mb-4 flex gap-2">
             <button 
                onClick={() => setSettingsOpen(!settingsOpen)} 
                className={`flex-1 py-2 text-[10px] fantasy-font tracking-[0.2em] uppercase border transition-all ${settingsOpen ? 'bg-[#bfa571] text-black border-[#bfa571]' : 'bg-black/40 text-gray-500 border-white/5 hover:border-white/20 hover:text-gray-300'}`}
             >
               {settingsOpen ? 'Close Settings' : 'Settings'}
             </button>
             <button 
                onClick={refreshBackups} 
                className="px-4 py-2 text-[10px] fantasy-font border border-white/5 text-gray-500 hover:text-white hover:bg-white/5 transition-all"
             >
               ↻
             </button>
          </div>

          {/* Pinned section stays at top (not scrollable unless it's huge) */}
          {pinnedBackups.length > 0 && (
            <div className="shrink-0 mb-6">
              <h3 className="text-[11px] fantasy-font text-[#bfa571] tracking-[0.3em] uppercase mb-4 px-1 flex items-center gap-3">
                <span className="font-bold">Pinned Favorites</span>
                <div className="flex-1 h-px bg-[#bfa571]/20" />
              </h3>
              <div className="space-y-3 max-h-[300px] overflow-y-auto custom-scrollbar pr-2">
                {pinnedBackups.map((entry) => (
                  <BackupCard key={entry.name} entry={entry} isPinned={true} />
                ))}
              </div>
            </div>
          )}

          {/* Recent Archives section scrolls INDEPENDENTLY */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <h3 className="text-[11px] fantasy-font text-gray-500 tracking-[0.3em] uppercase mb-4 px-1 flex items-center gap-3 shrink-0">
              <span className="opacity-50 font-bold">Recent Archives</span>
              <div className="flex-1 h-px bg-white/5" />
            </h3>
            
            <div className="flex-1 overflow-y-auto custom-scrollbar pr-3 space-y-3 pb-4">
              {regularBackups.length > 0 ? regularBackups.map((entry) => (
                <BackupCard key={entry.name} entry={entry} isPinned={false} />
              )) : (
                <div className="p-10 text-center border border-dashed border-white/5 rounded-lg">
                  <p className="text-gray-600 text-sm italic">No archives found.</p>
                </div>
              )}
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-2">
            <TabActionButton 
              label={loading ? "Archiving..." : "Create New Backup"} 
              onClick={handleCreate} 
              disabled={loading}
            />
            <TabActionButton 
              label={autoRunning ? "Stop Auto" : "Start Auto"} 
              onClick={autoRunning ? handleStopAuto : handleStartAuto}
              variant={autoRunning ? 'outline' : 'primary'}
            />
          </div>
        </div>

        {/* Right Pane: Selected Backup Details */}
        <div className="flex-1 flex flex-col min-h-0 gap-2 relative">
          
          {/* Settings Overlay Layer */}
          {settingsOpen && (
            <div className="absolute inset-0 z-20 bg-black/90 backdrop-blur-md border border-white/10 p-8 overflow-y-auto custom-scrollbar flex flex-col gap-8">
              <div className="flex justify-between items-center border-b border-[#bfa571]/30 pb-4">
                <h3 className="text-xl fantasy-font text-[#bfa571] tracking-[0.2em] uppercase">Configuration</h3>
                <button onClick={() => setSettingsOpen(false)} className="text-gray-500 hover:text-white transition-colors">✕</button>
              </div>

              {/* Path Settings */}
              <div className="space-y-4">
                <h4 className="text-xs fantasy-font text-gray-500 tracking-[0.2em] uppercase mb-4 border-l-2 border-[#bfa571] pl-3">Directories</h4>
                <div className="grid gap-4">
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-2 uppercase tracking-widest fantasy-font font-bold">Save File Location</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={settings.save_directory}
                        onChange={e => setSettings(s => ({ ...s, save_directory: e.target.value }))}
                        className="flex-1 bg-black/40 border border-white/10 rounded-sm px-4 py-2 text-sm text-gray-200 focus:border-[#bfa571]/50 outline-none transition-all"
                        placeholder="Path to game saves..."
                      />
                      <button onClick={handleAutoFind} className="px-4 bg-white/5 border border-white/10 text-[10px] fantasy-font hover:text-[#bfa571] hover:border-[#bfa571]/30 transition-all uppercase tracking-widest">Find</button>
                      <button 
                        onClick={() => handleBrowse('save')} 
                        disabled={dirPicking}
                        className="px-4 bg-white/5 border border-white/10 text-[10px] fantasy-font hover:text-[#bfa571] hover:border-[#bfa571]/30 transition-all uppercase tracking-widest disabled:opacity-50"
                      >
                        Browse
                      </button>
                    </div>
                    {autoFindResults && (
                      <div className="mt-2 border border-white/10 bg-black/60 rounded-sm overflow-hidden divide-y divide-white/5">
                        {autoFindResults.map((r, i) => (
                          <button 
                            key={i} 
                            className="w-full text-left px-4 py-2 hover:bg-[#bfa571]/10 text-xs text-gray-400 hover:text-[#bfa571] transition-all flex items-center gap-2"
                            onClick={() => { setSettings(s => ({ ...s, save_directory: r.path })); setAutoFindResults(null); }}
                          >
                            <span className="text-[#bfa571] font-bold">{r.game}</span> {r.path}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-2 uppercase tracking-widest fantasy-font font-bold">Backup Archive Path</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={settings.backup_directory}
                        onChange={e => setSettings(s => ({ ...s, backup_directory: e.target.value }))}
                        className="flex-1 bg-black/40 border border-white/10 rounded-sm px-4 py-2 text-sm text-gray-200 focus:border-[#bfa571]/50 outline-none transition-all"
                        placeholder="Path to backup storage..."
                      />
                      <button 
                        onClick={() => handleBrowse('backup')} 
                        disabled={dirPicking}
                        className="px-4 bg-white/5 border border-white/10 text-[10px] fantasy-font hover:text-[#bfa571] hover:border-[#bfa571]/30 transition-all uppercase tracking-widest disabled:opacity-50"
                      >
                        Browse
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Behavior Settings */}
              <div className="grid grid-cols-2 gap-8">
                 <div className="space-y-4">
                    <h4 className="text-xs fantasy-font text-gray-500 tracking-[0.2em] uppercase mb-4 border-l-2 border-[#bfa571] pl-3">Archive Behavior</h4>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-[10px] text-gray-500 mb-2 uppercase tracking-widest fantasy-font font-bold">Active Save File</label>
                        <select
                          value={settings.save_file_name}
                          onChange={e => setSettings(s => ({ ...s, save_file_name: e.target.value }))}
                          className="w-full bg-black/40 border border-white/10 rounded-sm px-3 py-2 text-sm text-gray-300 outline-none focus:border-[#bfa571]/50"
                        >
                          {availableSaveFiles.map(f => <option key={f} value={f}>{f}</option>)}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-[10px] text-gray-500 mb-2 uppercase tracking-widest fantasy-font font-bold">Method</label>
                          <select 
                            value={settings.backup_method}
                            onChange={e => setSettings(s => ({ ...s, backup_method: parseInt(e.target.value) }))}
                            className="w-full bg-black/40 border border-white/10 rounded-sm px-3 py-2 text-sm text-gray-300 outline-none focus:border-[#bfa571]/50"
                          >
                            <option value={0}>Interval</option>
                            <option value={1}>Watcher</option>
                          </select>
                        </div>
                        <div>
                           <label className="block text-[10px] text-gray-500 mb-2 uppercase tracking-widest fantasy-font font-bold">{settings.backup_method === 0 ? 'Mins' : 'Sleep'}</label>
                           <input 
                             type="number" 
                             value={settings.backup_method === 0 ? settings.auto_backup_interval : settings.sleep_between_saves}
                             onChange={e => setSettings(s => ({ ...s, [settings.backup_method === 0 ? 'auto_backup_interval' : 'sleep_between_saves']: parseInt(e.target.value) }))}
                             className="w-full bg-black/40 border border-white/10 rounded-sm px-3 py-2 text-sm text-gray-300"
                           />
                        </div>
                      </div>

                      {/* Max Backups Slider */}
                      <div>
                        <div className="flex justify-between mb-2">
                          <label className="block text-[10px] text-gray-500 uppercase tracking-widest fantasy-font font-bold">Max Recent Archives</label>
                          <span className="text-xs text-[#bfa571] font-bold">{settings.max_backups}</span>
                        </div>
                        <input
                          type="range"
                          min="5"
                          max="100"
                          step="5"
                          value={settings.max_backups}
                          onChange={e => setSettings(s => ({ ...s, max_backups: parseInt(e.target.value) }))}
                          className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[#bfa571]"
                        />
                      </div>

                      {/* Notification Volume Slider */}
                      <div>
                        <div className="flex justify-between mb-2">
                          <label className="block text-[10px] text-gray-500 uppercase tracking-widest fantasy-font font-bold">Notification Volume</label>
                          <span className="text-xs text-[#bfa571] font-bold">{settings.notification_volume}%</span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={settings.notification_volume}
                          onChange={e => setSettings(s => ({ ...s, notification_volume: parseInt(e.target.value) }))}
                          className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[#bfa571]"
                        />
                      </div>

                      <div className="flex items-center gap-3 p-3 bg-white/5 border border-white/5 rounded-sm">
                        <input
                          type="checkbox"
                          id="safeLoad"
                          checked={settings.quit_to_menu_before_load}
                          onChange={e => setSettings(s => ({ ...s, quit_to_menu_before_load: e.target.checked }))}
                          className="w-4 h-4 bg-black border-white/20 text-[#bfa571] rounded focus:ring-0"
                        />
                        <label htmlFor="safeLoad" className="text-xs fantasy-font tracking-widest text-gray-300 cursor-pointer uppercase">
                          Safe Load (Return to Menu)
                        </label>
                      </div>
                    </div>
                 </div>

                 <div className="space-y-4">
                    <h4 className="text-xs fantasy-font text-gray-500 tracking-[0.2em] uppercase mb-4 border-l-2 border-[#bfa571] pl-3">Global Hotkeys</h4>
                    <div className="grid grid-cols-1 gap-4">
                      <KeybindInput label="Create Archive" value={settings.keybind_save} onChange={v => setSettings(s => ({ ...s, keybind_save: v }))} />
                      <KeybindInput label="Restore Latest" value={settings.keybind_load} onChange={v => setSettings(s => ({ ...s, keybind_load: v }))} />
                      <KeybindInput label="Start Auto" value={settings.keybind_auto_start} onChange={v => setSettings(s => ({ ...s, keybind_auto_start: v }))} />
                      <KeybindInput label="Stop Auto" value={settings.keybind_auto_stop} onChange={v => setSettings(s => ({ ...s, keybind_auto_stop: v }))} />
                    </div>
                 </div>
              </div>

              <div className="mt-auto pt-8 border-t border-white/10 flex justify-end">
                <button 
                  onClick={handleSaveSettings}
                  className={`px-10 py-3 fantasy-font tracking-[0.2em] uppercase text-xs font-bold transition-all border ${settingsSaved ? 'bg-emerald-900/40 text-emerald-400 border-emerald-500' : 'bg-[#bfa571] text-black border-[#bfa571] hover:brightness-110'}`}
                >
                  {settingsSaved ? 'Settings Saved' : 'Commit Changes'}
                </button>
              </div>
            </div>
          )}

          {/* Main Detail View */}
          {selectedBackup ? (
            <>
              {/* Screenshot Frame - Maximized to fill space */}
              <div className="relative group rounded-lg overflow-hidden border border-[#bfa571]/20 shadow-2xl bg-black/50 aspect-video flex-1 min-h-0">
                {screenshotUrl ? (
                  <img src={screenshotUrl} alt="Preview" className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" onError={() => setScreenshotUrl(null)} />
                ) : (
                  <div className="absolute inset-0 flex flex-col items-center justify-center opacity-20">
                    <span className="text-6xl mb-4">🖼️</span>
                    <span className="fantasy-font tracking-[0.4em] uppercase text-sm">No Preview Captured</span>
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className="absolute bottom-6 left-6 opacity-0 group-hover:opacity-100 transition-all translate-y-4 group-hover:translate-y-0">
                   <h3 className="text-2xl fantasy-font text-[#bfa571] tracking-widest uppercase mb-1 drop-shadow-lg">
                     {selectedBackup.replace('.zip', '')}
                   </h3>
                   <p className="text-sm text-gray-300 tracking-[0.1em]">
                     {[...pinnedBackups, ...regularBackups].find(b => b.name === selectedBackup)?.date || ''}
                   </p>
                </div>
              </div>

              {/* Action Grid - Pushed to bottom with minimal gap */}
              <div className="mt-4 shrink-0">
                <div className="grid grid-cols-2 gap-3">
                  <TabActionButton 
                    label="Restore Selected" 
                    onClick={handleLoad} 
                    disabled={loading} 
                  />
                  <TabActionButton 
                    label="Rename" 
                    onClick={() => handleRename(selectedBackup)} 
                    variant="outline"
                  />
                  <TabActionButton 
                    label="Toggle Pin" 
                    onClick={() => handlePin(selectedBackup, !pinnedBackups.some(b => b.name === selectedBackup))} 
                    variant="outline"
                  />
                  <TabActionButton 
                    label="Delete" 
                    onClick={() => handleDelete()} 
                    variant="danger"
                  />
                </div>
              </div>

            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center opacity-30 border border-dashed border-white/10 rounded-lg bg-black/20">
               <div className="w-16 h-16 border-2 border-[#bfa571]/30 rounded-full flex items-center justify-center mb-6">
                 <div className="w-8 h-8 bg-[#bfa571]/20 rotate-45" />
               </div>
               <h3 className="fantasy-font text-xl tracking-[0.3em] uppercase mb-2">Awaiting Selection</h3>
               <p className="text-xs tracking-widest uppercase">Select an archive from the left to manage</p>
            </div>
          )}
        </div>
      </div>

      {/* Context Menu */}
      {ctxMenu && (
        <div className="fixed z-50 rounded border border-white/10 bg-[#0c0c0c] shadow-[0_10px_40px_rgba(0,0,0,0.8)] overflow-hidden min-w-[180px] backdrop-blur-xl"
          style={{ left: ctxMenu.x, top: ctxMenu.y }}
          onClick={e => e.stopPropagation()}>
          <button className="w-full text-left px-5 py-3 text-xs fantasy-font tracking-widest uppercase text-gray-400 hover:bg-[#bfa571]/10 hover:text-[#bfa571] transition-all flex items-center gap-3"
            onClick={() => { handlePin(ctxMenu.item.name, !ctxMenu.item.isPinned); setCtxMenu(null); }}>
            {ctxMenu.item.isPinned ? 'Unpin Archive' : 'Pin Archive'}
          </button>
          <button className="w-full text-left px-5 py-3 text-xs fantasy-font tracking-widest uppercase text-gray-400 hover:bg-[#bfa571]/10 hover:text-[#bfa571] transition-all flex items-center gap-3"
            onClick={() => { handleRename(ctxMenu.item.name); setCtxMenu(null); }}>
            Rename Archive
          </button>
          <button className="w-full text-left px-5 py-3 text-xs fantasy-font tracking-widest uppercase text-gray-400 hover:bg-emerald-500/10 hover:text-emerald-400 transition-all flex items-center gap-3 border-t border-white/5"
            onClick={() => { setSelectedBackup(ctxMenu.item.name); handleLoad(); setCtxMenu(null); }}>
            Restore Now
          </button>
          <div className="border-t border-white/5" />
          <button className="w-full text-left px-5 py-3 text-xs fantasy-font tracking-widest uppercase text-red-400 hover:bg-red-500/10 transition-all flex items-center gap-3"
            onClick={() => { handleDelete(ctxMenu.item.name); setCtxMenu(null); }}>
            Delete Forever
          </button>
        </div>
      )}

      {confirmModal && (
        <ConfirmationModal
          open={confirmModal.open}
          title={confirmModal.title}
          message={confirmModal.message}
          isDanger={confirmModal.isDanger}
          onConfirm={confirmModal.onConfirm}
          onCancel={() => setConfirmModal(null)}
        />
      )}

      {inputModal && (
        <InputModal
          key={inputModal.initialValue}
          open={inputModal.open}
          title={inputModal.title}
          initialValue={inputModal.initialValue}
          label={inputModal.label}
          onConfirm={inputModal.onConfirm}
          onCancel={() => setInputModal(null)}
        />
      )}
    </div>
  );
};

export default BackupTab;
