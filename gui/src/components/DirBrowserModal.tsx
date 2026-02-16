import React, { useState, useEffect } from 'react';
import { listDirs } from '../api';

interface Props {
    open: boolean;
    title?: string;
    initialPath?: string;
    onSelect: (path: string) => void;
    onCancel: () => void;
}

const DirBrowserModal: React.FC<Props> = ({ open, title = 'Select Folder', initialPath, onSelect, onCancel }) => {
    const [currentPath, setCurrentPath] = useState('/');
    const [dirs, setDirs] = useState<string[]>([]);
    const [parentPath, setParentPath] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const navigate = async (path: string) => {
        setLoading(true);
        setError('');
        try {
            const data = await listDirs(path);
            setCurrentPath(data.path);
            setDirs(data.dirs);
            setParentPath(data.parent);
        } catch {
            setError('Failed to list directory');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (open) {
            navigate(initialPath || '');
        }
    }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

    if (!open) return null;

    // Build breadcrumb parts from currentPath
    const parts = currentPath === '/' ? [''] : currentPath.split('/');

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={onCancel}>
            <div className="bg-[#111118] border border-[#333] rounded-xl shadow-2xl w-[520px] max-h-[70vh] flex flex-col"
                style={{ fontFamily: "'Inter', sans-serif" }}
                onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
                    <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
                    <button onClick={onCancel} className="text-gray-500 hover:text-gray-300 text-lg leading-none">&times;</button>
                </div>

                {/* Breadcrumb */}
                <div className="px-4 py-2 flex items-center gap-1 text-xs text-gray-400 overflow-x-auto border-b border-[#222] flex-shrink-0">
                    {parts.map((part, i) => {
                        const pathTo = i === 0 ? '/' : parts.slice(0, i + 1).join('/');
                        const label = i === 0 ? '/' : part;
                        return (
                            <React.Fragment key={i}>
                                {i > 0 && <span className="text-gray-600">/</span>}
                                <button className="hover:text-[#bfa571] transition-colors whitespace-nowrap"
                                    onClick={() => navigate(pathTo)}>
                                    {label}
                                </button>
                            </React.Fragment>
                        );
                    })}
                </div>

                {/* Current path display */}
                <div className="px-4 py-1.5 bg-[#0a0a10] text-xs text-gray-500 font-mono border-b border-[#222] flex-shrink-0">
                    {currentPath}
                </div>

                {/* Directory listing */}
                <div className="flex-1 overflow-y-auto min-h-[200px] max-h-[400px]">
                    {loading ? (
                        <div className="p-4 text-center text-gray-500 text-sm">Loading...</div>
                    ) : error ? (
                        <div className="p-4 text-center text-red-400 text-sm">{error}</div>
                    ) : (
                        <>
                            {parentPath !== null && (
                                <button
                                    className="w-full text-left px-4 py-2 text-sm text-gray-400 hover:bg-[#1a1a25] hover:text-[#bfa571] transition-colors flex items-center gap-2 border-b border-[#1a1a1a]"
                                    onClick={() => navigate(parentPath)}>
                                    <span className="opacity-60">📁</span> <span>..</span>
                                </button>
                            )}
                            {dirs.length === 0 && (
                                <div className="p-4 text-center text-gray-600 text-sm italic">No subdirectories</div>
                            )}
                            {dirs.map(dir => (
                                <button
                                    key={dir}
                                    className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-[#1a1a25] hover:text-[#bfa571] transition-colors flex items-center gap-2 border-b border-[#1a1a1a]"
                                    onClick={() => navigate(currentPath === '/' ? `/${dir}` : `${currentPath}/${dir}`)}>
                                    <span className="opacity-60">📁</span> {dir}
                                </button>
                            ))}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#333] flex-shrink-0">
                    <button onClick={onCancel}
                        className="px-4 py-1.5 bg-[#2a2a2a] border border-[#444] rounded text-xs text-gray-400 hover:bg-[#333] transition-colors">
                        Cancel
                    </button>
                    <button onClick={() => onSelect(currentPath)}
                        className="px-4 py-1.5 bg-[#2a2520] border border-[#bfa571]/30 rounded text-xs text-[#bfa571] hover:bg-[#3a3020] transition-colors font-medium">
                        Select This Folder
                    </button>
                </div>
            </div>
        </div>
    );
};

export default DirBrowserModal;
