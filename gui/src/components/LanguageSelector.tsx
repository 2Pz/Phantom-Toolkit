import { useState, useEffect, useRef } from 'react';
import { updateConfig } from '../api';

interface LanguageSelectorProps {
    currentLanguage: string;
    onLanguageChange: (lang: string) => void;
}

const LANGUAGES = [
    { code: 'en', label: 'English' },
    { code: 'ar', label: 'Arabic' },
    { code: 'de', label: 'German' },
    { code: 'es_es', label: 'Spanish (Spain)' },
    { code: 'es_li', label: 'Spanish (Latin America)' },
    { code: 'fr', label: 'French' },
    { code: 'it', label: 'Italian' },
    { code: 'ja', label: 'Japanese' },
    { code: 'ko', label: 'Korean' },
    { code: 'pl', label: 'Polish' },
    { code: 'porbr', label: 'Portuguese (Brazil)' },
    { code: 'ru', label: 'Russian' },
    { code: 'th', label: 'Thai' },
    { code: 'zh_CN', label: 'Chinese (Simplified)' },
    { code: 'zh_TW', label: 'Chinese (Traditional)' },
];

export function LanguageSelector({ currentLanguage, onLanguageChange }: LanguageSelectorProps) {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    const selectedLabel = LANGUAGES.find(l => l.code === currentLanguage)?.label || currentLanguage;

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleSelect = async (code: string) => {
        onLanguageChange(code);
        await updateConfig({ language: code });
        setIsOpen(false);
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-3 py-1 hover:bg-white/5 transition-colors group min-w-[120px] justify-between rounded-sm"
                title="Select Language"
            >
                <span className="text-[10px] fantasy-font tracking-widest uppercase text-gray-400 group-hover:text-gray-200">
                    {selectedLabel}
                </span>
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`text-gray-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                >
                    <path d="m6 9 6 6 6-6" />
                </svg>
            </button>

            {isOpen && (
                <div className="absolute top-full right-0 mt-1 w-48 max-h-64 overflow-y-auto bg-black/90 border border-[#bfa571]/30 rounded-sm shadow-xl z-50 backdrop-blur-sm custom-scrollbar">
                    {LANGUAGES.map((lang) => (
                        <button
                            key={lang.code}
                            onClick={() => handleSelect(lang.code)}
                            className={`w-full text-left px-3 py-2 text-[10px] fantasy-font tracking-widest uppercase transition-colors
                ${currentLanguage === lang.code
                                    ? 'text-[#bfa571] bg-[#bfa571]/10'
                                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                                }`}
                        >
                            {lang.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
