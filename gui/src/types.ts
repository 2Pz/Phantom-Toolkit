
export enum SlotType {
  WEAPON_R = 'WEAPON_R',
  WEAPON_L = 'WEAPON_L',
  AMMO_ARROW = 'AMMO_ARROW',
  AMMO_BOLT = 'AMMO_BOLT',
  ARMOR_HEAD = 'ARMOR_HEAD',
  ARMOR_CHEST = 'ARMOR_CHEST',
  ARMOR_HANDS = 'ARMOR_HANDS',
  ARMOR_LEGS = 'ARMOR_LEGS',
  RING = 'RING',
  TALISMAN = 'TALISMAN',
  QUICK_ITEM = 'QUICK_ITEM',
  COVENANT = 'COVENANT',
  SPELL = 'SPELL',
  PHYSICK = 'PHYSICK',
  GREAT_RUNE = 'GREAT_RUNE'
}

export type GameType = 'ELDEN_RING' | 'DARK_SOULS_3';

export interface Item {
  id: string;
  name: string;
  image: string;
  type: SlotType;
  description: string;
  count?: number;
  weight?: number;
  upgrade?: number;
  maxUpgrade?: number;
  gemId?: number;
  category?: string;
  baseId?: string;
  baseName?: string;
  variants?: { id: number; name: string }[];
}

export interface BackendItem {
  id: number;
  name: string;
  icon_id: string | null;
  max_upgrade: number;
  category?: string;
  gem_id?: number;
  count?: number;
  base_id?: number;
  base_name?: string;
  variants?: { id: number; name: string }[] | null;
}

export interface AppConfig {
  language: string;
  autoCalcLevel?: boolean;
}

export interface Build {
  id: string;
  name: string;
  slots: Record<string, Item | null>;
}

export interface StatusState {
  level: number;
  secondary: number; // Souls (DS3) or Runes (ER)
  journey: number;
  steamId?: string;
  covenant?: string;
  attributes: Record<string, number>;
  scadutreeBlessing?: number;
  reveredSpiritAsh?: number;
  hp?: number;
  maxHp?: number;
}

export interface PlayerData {
  name: string;
  status: StatusState;
  build: Build;
  date?: string;
  isLocal?: boolean;
}

export interface BackupEntry {
  id: string;
  name: string;
  date: string;
  sourceFiles?: string;
  size: number;
  isPinned?: boolean;
  hasScreenshot?: boolean;
}

export interface BackupSettings {
  save_directory: string;
  backup_directory: string;
  save_file_type: string;
  save_file_name: string;
  backup_method: number;  // 0 = interval, 1 = file_watcher
  auto_backup_interval: number;
  sleep_between_saves: number;
  max_backups: number;
  quit_to_menu_before_load: boolean;
  notification_volume: number;
  keybind_save: string;
  keybind_load: string;
  keybind_auto_start: string;
  keybind_auto_stop: string;
}
