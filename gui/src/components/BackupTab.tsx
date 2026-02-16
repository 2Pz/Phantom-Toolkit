
import React, { useState, useEffect, useRef } from 'react';
import { BackupEntry, BackupSettings } from '../types';
import {
  getBackupSettings, saveBackupSettings, autoFindSavePaths,
  listBackups, createBackup, loadBackup, deleteBackup,
  pinBackup, renameBackup, getScreenshotUrl,
  startAutoBackup, stopAutoBackup, getAutoBackupStatus,
  listSaveFiles, quitToMenu, toFrontendGame, browseDirectory,
} from '../api';
import { ConfirmationModal, InputModal } from './Modal';

interface Props {
  game?: string;
}

const SAVE_FILE_OPTIONS = ['.sl2', '.co2'];

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
    if (key === 'control' || key === 'shift' || key === 'alt') return; // wait for non-modifier

    // Map some keys to match 'keyboard' lib expectations if needed
    if (key === ' ') key = 'space';

    const combo = [...modifiers, key].join('+');
    onChange(combo);
    setRecording(false);
  };

  return (
    <div className="flex flex-col">
      <label className="text-xs text-gray-400 mb-1 uppercase tracking-wider">{label}</label>
      <div className="flex gap-2">
        <input
          type="text"
          value={recording ? 'Press keys...' : (value || 'None')}
          readOnly
          className={`flex-1 bg-[#1a1a1a] border ${recording ? 'border-[#bfa571]' : 'border-[#333]'} rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none cursor-pointer`}
          onClick={() => setRecording(true)}
          onKeyDown={handleKeyDown}
          onBlur={() => setRecording(false)}
        />
        {value && (
          <button
            onClick={() => onChange('')}
            className="px-2 bg-[#2a2a2a] border border-[#333] rounded text-gray-400 hover:text-red-400"
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
  const pollRef = useRef<number | null>(null);
  const lastNewestRef = useRef<string | null>(null);

  // Status
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  // Directory browser modal
  const [dirPicking, setDirPicking] = useState(false);
  // useState updates are async; useRef prevents click-race double opens.
  const dirPickingRef = useRef(false);


  // Auto-find & save files
  const [autoFindResults, setAutoFindResults] = useState<{ path: string; game: string; steam_id: string }[] | null>(null);
  const [availableSaveFiles, setAvailableSaveFiles] = useState<string[]>([]);

  // Context menu
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; item: BackupEntry } | null>(null);

  // Modals
  const [confirmModal, setConfirmModal] = useState<{ open: boolean; title: string; message: string; isDanger?: boolean; onConfirm: () => void } | null>(null);
  const [inputModal, setInputModal] = useState<{ open: boolean; title: string; initialValue: string; label?: string; onConfirm: (val: string) => void } | null>(null);

  // ---- Init ----
  useEffect(() => {
    loadSettingsFromBackend();
    refreshBackups();
    checkAutoStatus();
  }, [game]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch save files on dir/ext change
  useEffect(() => {
    if (settings.save_directory) {
      fetchSaveFiles(settings.save_directory, settings.save_file_type);
    } else {
      setAvailableSaveFiles([]);
    }
  }, [settings.save_directory, settings.save_file_type]);

  // Close context menu on click
  useEffect(() => {
    const h = () => setCtxMenu(null);
    window.addEventListener('click', h);
    return () => window.removeEventListener('click', h);
  }, []);

  // Poll while auto-backup running
  useEffect(() => {
    if (autoRunning) {
      pollRef.current = window.setInterval(() => {
        checkAutoStatus();
        refreshBackups();
      }, 5000);
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [autoRunning]); // eslint-disable-line react-hooks/exhaustive-deps

  // Global polling for manual/hotkey backups (every 2s)
  useEffect(() => {
    const interval = setInterval(() => {
      refreshBackups();
    }, 2000);
    return () => clearInterval(interval);
  }, [game]); // eslint-disable-line react-hooks/exhaustive-deps

  // Screenshot preview
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

  // ---- API ----
  const loadSettingsFromBackend = async () => {
    try {
      const s = await getBackupSettings(game);
      setSettings(s);
      // If we just loaded settings for a new game, we might need to clear current available saves 
      // if the dir changed, but the useEffect on [settings.save_directory] handles that.
      // However, we should be careful about race conditions if game changes quickly.
    } catch {
      // ignore
    }
  };

  const fetchSaveFiles = async (dir: string, ext: string) => {
    try {
      const data = await listSaveFiles(dir, ext);
      setAvailableSaveFiles(data.files);
    } catch { setAvailableSaveFiles([]); }
  };

  const refreshBackups = async () => {
    try {
      const data = await listBackups(game);

      // Auto-select logic: if top REGULAR backup changed, select it
      // This handles the case where pinned items mask the new backup in a combined list
      if (data.regular.length > 0) {
        const newestRegular = data.regular[0].name;
        // If newest changed, OR if we had no previous newest (empty list), select it
        if (lastNewestRef.current !== newestRegular) {
          setSelectedBackup(newestRegular);
        }
        lastNewestRef.current = newestRegular;
      }

      setPinnedBackups(data.pinned.map((b, i) => ({ ...b, id: `p${i}` })));
      setRegularBackups(data.regular.map((b, i) => ({ ...b, id: `r${i}` })));
    } catch {
      // ignore
    }
  };

  const checkAutoStatus = async () => {
    try {
      const data = await getAutoBackupStatus();
      setAutoRunning(data.running);
    } catch {
      // ignore
    }
  };

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
      if (!path) return; // user cancelled
      setSettings(s => ({
        ...s,
        [field === 'save' ? 'save_directory' : 'backup_directory']: path
      }));
    } catch {
      // ignore
    } finally {
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
    } catch (e) {
      const err = e as Error;
      setStatusMsg(`Error: ${err.message}`);
    }
    finally { setLoading(false); }
  };

  const handleLoad = async () => {
    if (!selectedBackup) return;

    if (settings.quit_to_menu_before_load) {
      setConfirmModal({
        open: true,
        title: 'Safe Load Confirmation',
        message: `"Safe Load" is ENABLED.\n\nThis will:\n1. Quit to Main Menu\n2. Wait 5 seconds\n3. Restore "${selectedBackup}"\n\nContinue?`,
        onConfirm: async () => {
          setConfirmModal(null);
          setLoading(true);
          try {
            setStatusMsg('Quitting to Main Menu...');
            const gameType = toFrontendGame(game);
            if (gameType) {
              await quitToMenu(gameType);
              setStatusMsg('Waiting for menu (5s)...');
              await new Promise(r => setTimeout(r, 5000));
            } else {
              console.warn("Could not determine game type for quitToMenu");
            }

            setStatusMsg(`Restoring: ${selectedBackup}...`);
            await loadBackup(selectedBackup, game);
            setStatusMsg(`Restored: ${selectedBackup}`);
          } catch (e) {
            const err = e as Error;
            setStatusMsg(`Error: ${err.message}`);
          } finally { setLoading(false); }
        }
      });
    } else {
      setConfirmModal({
        open: true,
        title: 'Load Backup',
        message: `WARNING: You should be in the Main Menu before loading a save!\n\nRestore "${selectedBackup}" now?`,
        isDanger: true,
        onConfirm: async () => {
          setConfirmModal(null);
          setLoading(true);
          try {
            await loadBackup(selectedBackup, game);
            setStatusMsg(`Restored: ${selectedBackup}`);
          } catch (e) {
            const err = e as Error;
            setStatusMsg(`Error: ${err.message}`);
          } finally { setLoading(false); }
        }
      });
    }
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
        try { await renameBackup(name, newName, game); await refreshBackups(); }
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

  // ---- Render ----
  const renderRow = (entry: BackupEntry, idx: number) => {
    const selected = selectedBackup === entry.name;
    return (
      <tr
        key={entry.name}
        className={`cursor-pointer transition-colors ${selected ? 'bg-[#3a3a6a]' : 'hover:bg-[#252535]'}`}
        onClick={() => setSelectedBackup(entry.name)}
        onContextMenu={(e) => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, item: entry }); }}
      >
        <td className="px-3 py-1.5 text-gray-500 w-8">{idx + 1}</td>
        <td className="px-3 py-1.5 text-blue-400 hover:underline">{entry.name}</td>
        <td className="px-3 py-1.5 text-green-400">{entry.date}</td>
      </tr>
    );
  };

  const renderTable = (title: string, entries: BackupEntry[]) => (
    <div className="mb-4">
      <h3 className="font-bold text-sm uppercase tracking-wider text-[#bfa571] mb-2" style={{ fontVariant: 'small-caps', fontSize: '14px' }}>
        {title}
      </h3>
      <div className="border border-[#333] rounded overflow-x-auto custom-scrollbar">
        <table className="w-full text-sm min-w-[500px]" style={{ fontFamily: "'Inter', sans-serif" }}>
          <thead>
            <tr className="bg-[#1a1a2a] text-gray-400 text-xs uppercase">
              <th className="px-3 py-2 text-left w-8">#</th>
              <th className="px-3 py-2 text-left">Backup Name</th>
              <th className="px-3 py-2 text-left">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#222]">
            {entries.length > 0 ? entries.map((e, i) => renderRow(e, i)) : (
              <tr><td colSpan={3} className="px-3 py-3 text-center text-gray-600 italic">No backups</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  const btnClass = "flex-1 py-2.5 px-4 text-sm font-semibold rounded transition-all text-white";

  return (
    <div className="w-full h-full flex flex-col overflow-y-auto custom-scrollbar" style={{ fontFamily: "'Cormorant Garamond', serif" }}>

      {/* Game Preview / Screenshot */}
      <div className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg overflow-hidden mb-3">
        {screenshotUrl ? (
          <img
            src={screenshotUrl}
            alt="Game Preview"
            className="w-full block object-cover"
            style={{ maxHeight: '35vh' }}
            onError={() => setScreenshotUrl(null)}
          />
        ) : (
          <div className="flex items-center justify-center text-gray-600 text-sm italic" style={{ height: '200px' }}>
            🖼️ Game Preview
          </div>
        )}
      </div>

      {/* Auto Backup Status */}
      <div className="mb-3 px-1">
        <span className={`text-sm font-bold ${autoRunning ? 'text-green-400' : 'text-red-400'}`}>
          Auto Backup: {autoRunning
            ? `Running (${settings.backup_method === 0 ? `every ${settings.auto_backup_interval}m` : 'file watcher'})`
            : 'Not Running'}
        </span>
        {statusMsg && <span className="text-gray-500 text-xs ml-4">{statusMsg}</span>}
      </div>

      {/* Settings Toggle */}
      <button
        className="mb-3 px-3 py-1.5 text-xs text-gray-400 hover:text-[#bfa571] border border-[#333] rounded hover:border-[#555] transition-colors self-start flex items-center gap-1"
        onClick={() => setSettingsOpen(!settingsOpen)}
        style={{ fontFamily: "'Inter', sans-serif" }}
      >
        ⚙️ Settings {settingsOpen ? '▲' : '▼'}
      </button>

      {/* Settings Panel */}
      {settingsOpen && (
        <div className="mb-4 p-4 border border-[#333] rounded-lg bg-[#111118] space-y-3" style={{ fontFamily: "'Inter', sans-serif" }}>
          {/* Save Directory */}
          <div>
            <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Save Directory</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={settings.save_directory}
                onChange={e => setSettings(s => ({ ...s, save_directory: e.target.value }))}
                className="flex-1 bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none"
                placeholder="/path/to/save/files"
              />
              <button onClick={handleAutoFind} className="px-3 py-1.5 bg-[#2a2a2a] border border-[#444] rounded text-xs text-gray-300 hover:bg-[#333] hover:text-[#bfa571] transition-colors">
                Auto Find
              </button>
              <button
                onClick={() => handleBrowse('save')}
                disabled={dirPicking}
                className="px-3 py-1.5 bg-[#2a2a2a] border border-[#444] rounded text-xs text-gray-300 hover:bg-[#333] hover:text-[#bfa571] transition-colors disabled:opacity-50"
              >
                Browse
              </button>
            </div>
            {autoFindResults && (
              <div className="mt-2 border border-[#444] rounded bg-[#1a1a1a] overflow-hidden">
                {autoFindResults.map((r, i) => (
                  <button key={i} className="w-full text-left px-3 py-1.5 hover:bg-[#2a2520] text-sm text-gray-300 hover:text-[#bfa571] transition-colors border-b border-[#222] last:border-b-0"
                    onClick={() => { setSettings(s => ({ ...s, save_directory: r.path })); setAutoFindResults(null); }}>
                    <span className="text-[#bfa571] text-xs mr-2">{r.game}</span> {r.path}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Backup Directory */}
          <div className="relative">
            <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Backup Directory</label>
            <input
              type="text"
              value={settings.backup_directory}
              onChange={e => setSettings(s => ({ ...s, backup_directory: e.target.value }))}
              className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none"
              placeholder="/path/to/backups"
            />
            <button
              onClick={() => handleBrowse('backup')}
              disabled={dirPicking}
              className="absolute right-1 top-6 bottom-1 px-3 bg-[#2a2a2a] border-l border-[#444] rounded-r text-xs text-gray-300 hover:bg-[#333] hover:text-[#bfa571] transition-colors disabled:opacity-50"
            >
              Browse
            </button>
          </div>

          {/* Extension + Save File + Method */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Extension</label>
              <select value={settings.save_file_type}
                onChange={e => setSettings(s => ({ ...s, save_file_type: e.target.value, save_file_name: '' }))}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none">
                {SAVE_FILE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Save File</label>
              <select value={settings.save_file_name}
                onChange={e => setSettings(s => ({ ...s, save_file_name: e.target.value }))}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none">
                <option value="">All {settings.save_file_type} files</option>
                {availableSaveFiles.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Backup Method</label>
              <select value={settings.backup_method}
                onChange={e => setSettings(s => ({ ...s, backup_method: parseInt(e.target.value) }))}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none">
                <option value={0}>Interval (every N min)</option>
                <option value={1}>File Watcher (on save)</option>
              </select>
            </div>
          </div>

          {/* Interval/Sleep + Max Backups + Volume + Save */}
          <div className="grid grid-cols-3 gap-3">
            {settings.backup_method === 0 ? (
              <div>
                <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Interval (min)</label>
                <input type="number" min={1} value={settings.auto_backup_interval}
                  onChange={e => setSettings(s => ({ ...s, auto_backup_interval: parseInt(e.target.value) || 1 }))}
                  className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none" />
              </div>
            ) : (
              <div>
                <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Sleep (sec)</label>
                <input type="number" min={1} value={settings.sleep_between_saves}
                  onChange={e => setSettings(s => ({ ...s, sleep_between_saves: parseInt(e.target.value) || 1 }))}
                  className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none" />
              </div>
            )}
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Max Backups</label>
              <input type="number" min={1} value={settings.max_backups}
                onChange={e => setSettings(s => ({ ...s, max_backups: parseInt(e.target.value) || 1 }))}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-gray-200 focus:border-[#bfa571] focus:outline-none" />
            </div>

            {/* Volume Slider */}
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wider">Notification Vol: {settings.notification_volume}%</label>
              <input
                type="range"
                min="0"
                max="100"
                value={settings.notification_volume}
                onChange={e => setSettings(s => ({ ...s, notification_volume: parseInt(e.target.value) }))}
                className="w-full h-2 bg-[#333] rounded-lg appearance-none cursor-pointer accent-[#bfa571]"
              />
            </div>

            {/* Global Hotkeys */}
            <div className="col-span-3 mt-2 pt-2 border-t border-[#333]">
              <h4 className="text-xs font-bold text-[#bfa571] uppercase tracking-wider mb-2">Global Hotkeys</h4>
              <div className="grid grid-cols-2 gap-3">
                <KeybindInput
                  label="Create Backup"
                  value={settings.keybind_save}
                  onChange={v => setSettings(s => ({ ...s, keybind_save: v }))}
                />
                <KeybindInput
                  label="Load Latest Backup"
                  value={settings.keybind_load}
                  onChange={v => setSettings(s => ({ ...s, keybind_load: v }))}
                />
                <KeybindInput
                  label="Start Auto Backup"
                  value={settings.keybind_auto_start}
                  onChange={v => setSettings(s => ({ ...s, keybind_auto_start: v }))}
                />
                <KeybindInput
                  label="Stop Auto Backup"
                  value={settings.keybind_auto_stop}
                  onChange={v => setSettings(s => ({ ...s, keybind_auto_stop: v }))}
                />
              </div>
            </div>

            <div className="col-span-3 flex items-center justify-between mt-2 pt-2 border-t border-[#333]">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="safeLoad"
                  checked={settings.quit_to_menu_before_load}
                  onChange={e => setSettings(s => ({ ...s, quit_to_menu_before_load: e.target.checked }))}
                  className="rounded border-[#333] bg-[#1a1a1a] text-[#bfa571] focus:ring-0 focus:ring-offset-0"
                />
                <label htmlFor="safeLoad" className="text-xs text-gray-400 uppercase tracking-wider cursor-pointer select-none">
                  Safe Load (Quit first)
                </label>
              </div>

              <button onClick={handleSaveSettings}
                className={`py-1.5 px-6 rounded text-sm font-semibold border transition-all ${settingsSaved ? 'bg-green-800 border-green-600 text-green-300' : 'bg-[#2a2a3a] border-[#444] text-gray-300 hover:text-[#bfa571]'}`}>
                {settingsSaved ? '✓ Saved' : 'Save Settings'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Pinned Backups */}
      <div className="flex-1 min-h-0">
        {renderTable('Pinned Backups', pinnedBackups)}
        {renderTable('Regular Backups', regularBackups)}
      </div>

      {/* Bottom Buttons - Row 1 */}
      <div className="flex gap-2 mt-3">
        <button onClick={handleCreate} disabled={loading}
          className={`${btnClass} bg-[#4a4a8a] hover:bg-[#5a5a9a] disabled:opacity-40`}>
          {loading ? '...' : 'Save Backup'}
        </button>
        <button onClick={handleLoad} disabled={!selectedBackup || loading}
          className={`${btnClass} bg-[#4a4a8a] hover:bg-[#5a5a9a] disabled:opacity-40`}>
          Load Backup
        </button>
        <button onClick={refreshBackups}
          className={`${btnClass} bg-[#4a4a8a] hover:bg-[#5a5a9a]`}>
          Refresh
        </button>
        <button onClick={() => handleDelete()} disabled={!selectedBackup}
          className={`${btnClass} bg-[#4a4a8a] hover:bg-[#5a5a9a] disabled:opacity-40`}>
          Delete
        </button>
      </div>

      {/* Bottom Buttons - Row 2 */}
      <div className="flex gap-2 mt-2 mb-2">
        <button onClick={handleStartAuto} disabled={autoRunning}
          className={`${btnClass} bg-[#2a6a2a] hover:bg-[#3a8a3a] disabled:opacity-40`}>
          Start Auto Backup
        </button>
        <button onClick={handleStopAuto} disabled={!autoRunning}
          className={`${btnClass} bg-[#333] hover:bg-[#444] disabled:opacity-40`}>
          Stop Auto Backup
        </button>
      </div>

      {/* Context Menu */}
      {ctxMenu && (
        <div className="fixed z-50 rounded border border-[#444] bg-[#1e1e1e] shadow-2xl overflow-hidden min-w-[150px]"
          style={{ left: ctxMenu.x, top: ctxMenu.y, fontFamily: "'Inter', sans-serif" }}
          onClick={e => e.stopPropagation()}>
          <button className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-[#2a2520] hover:text-[#bfa571] transition-colors"
            onClick={() => { handlePin(ctxMenu.item.name, !ctxMenu.item.isPinned); setCtxMenu(null); }}>
            📌 {ctxMenu.item.isPinned ? 'Unpin' : 'Pin'}
          </button>
          <button className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-[#2a2520] hover:text-[#bfa571] transition-colors"
            onClick={() => { handleRename(ctxMenu.item.name); setCtxMenu(null); }}>
            ✏️ Rename
          </button>
          <button className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-[#1e2e1e] hover:text-green-400 transition-colors"
            onClick={() => { setSelectedBackup(ctxMenu.item.name); handleLoad(); setCtxMenu(null); }}>
            📂 Load
          </button>
          <div className="border-t border-[#333]" />
          <button className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-[#2a1515] transition-colors"
            onClick={() => { handleDelete(ctxMenu.item.name); setCtxMenu(null); }}>
            🗑️ Delete
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
          key={inputModal.initialValue} // Force re-mount to reset value
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
