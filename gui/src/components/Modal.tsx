import React, { useEffect, useRef, useState } from 'react';

interface ModalProps {
    open: boolean;
    title: string;
    onClose: () => void;
    children: React.ReactNode;
    footer?: React.ReactNode;
}

const BaseModal: React.FC<ModalProps> = ({ open, title, onClose, children, footer }) => {
    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm transition-opacity duration-300" onClick={onClose}>
            <div className="bg-[#0c0c0c] border border-[#bfa571]/30 rounded-lg shadow-[0_0_30px_rgba(0,0,0,0.8)] w-[450px] max-w-[90vw] animate-in fade-in zoom-in-95 duration-200 relative overflow-hidden group"
                onClick={e => e.stopPropagation()}>

                {/* Decorative corner accents */}
                <div className="absolute top-0 left-0 w-8 h-8 border-t border-l border-[#bfa571]/60 rounded-tl-lg pointer-events-none"></div>
                <div className="absolute top-0 right-0 w-8 h-8 border-t border-r border-[#bfa571]/60 rounded-tr-lg pointer-events-none"></div>
                <div className="absolute bottom-0 left-0 w-8 h-8 border-b border-l border-[#bfa571]/60 rounded-bl-lg pointer-events-none"></div>
                <div className="absolute bottom-0 right-0 w-8 h-8 border-b border-r border-[#bfa571]/60 rounded-br-lg pointer-events-none"></div>

                <div className="flex items-center justify-center pt-5 pb-3 px-6 relative">
                    {/* Header decorative line */}
                    <div className="absolute bottom-0 left-10 right-10 h-px bg-gradient-to-r from-transparent via-[#bfa571]/50 to-transparent"></div>

                    <h3 className="text-xl font-bold text-[#bfa571] fantasy-font tracking-[0.15em] uppercase text-center drop-shadow-sm">{title}</h3>

                    <button onClick={onClose} className="absolute right-4 top-4 text-gray-500 hover:text-[#bfa571] transition-colors text-2xl leading-none font-serif opacity-60 hover:opacity-100">&times;</button>
                </div>

                <div className="p-6 text-gray-300 text-lg leading-relaxed font-serif tracking-wide relative z-10">
                    {children}
                </div>

                {footer && (
                    <div className="flex items-center justify-center gap-4 px-6 py-5 bg-black/20 relative z-10">
                        {/* Footer decorative line */}
                        <div className="absolute top-0 left-10 right-10 h-px bg-gradient-to-r from-transparent via-[#bfa571]/20 to-transparent"></div>
                        {footer}
                    </div>
                )}
            </div>
        </div>
    );
};

interface ConfirmationModalProps {
    open: boolean;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    isDanger?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
    open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', isDanger = false, onConfirm, onCancel
}) => {
    return (
        <BaseModal open={open} title={title} onClose={onCancel}
            footer={
                <>
                    <button onClick={onCancel} className="px-6 py-2 bg-transparent border border-[#444] rounded text-xs text-gray-400 hover:text-white hover:border-gray-300 transition-all fantasy-font tracking-widest uppercase hover:bg-white/5">
                        {cancelLabel}
                    </button>
                    <button onClick={onConfirm} className={`px-6 py-2 border rounded text-xs font-bold transition-all fantasy-font tracking-widest uppercase shadow-[0_0_10px_rgba(0,0,0,0.5)] ${isDanger ? 'bg-red-950/40 border-red-800/80 text-red-400 hover:bg-red-900/60 hover:border-red-500 hover:text-red-200 hover:shadow-[0_0_15px_rgba(220,38,38,0.3)]' : 'bg-[#bfa571]/10 border-[#bfa571]/60 text-[#bfa571] hover:bg-[#bfa571]/20 hover:border-[#bfa571] hover:text-[#ebdcb2] hover:shadow-[0_0_15px_rgba(191,165,113,0.2)]'}`}>
                        {confirmLabel}
                    </button>
                </>
            }>
            <p className="whitespace-pre-wrap text-center font-cormorant text-gray-200/90">{message}</p>
        </BaseModal>
    );
};

interface InputModalProps {
    open: boolean;
    title: string;
    label?: string;
    initialValue?: string;
    confirmLabel?: string;
    onConfirm: (value: string) => void;
    onCancel: () => void;
}

export const InputModal: React.FC<InputModalProps> = ({
    open, title, label, initialValue = '', confirmLabel = 'Save', onConfirm, onCancel
}) => {
    const [value, setValue] = useState(initialValue);
    const inputRef = useRef<HTMLInputElement>(null);

    // Focus input on mount
    useEffect(() => {
        setTimeout(() => inputRef.current?.focus(), 50);
    }, []);

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        onConfirm(value);
    };

    return (
        <BaseModal open={open} title={title} onClose={onCancel}
            footer={
                <>
                    <button onClick={onCancel} className="px-6 py-2 bg-transparent border border-[#444] rounded text-xs text-gray-400 hover:text-white hover:border-gray-300 transition-all fantasy-font tracking-widest uppercase hover:bg-white/5">
                        Cancel
                    </button>
                    <button onClick={() => handleSubmit()} className="px-6 py-2 bg-[#bfa571]/10 border border-[#bfa571]/60 text-[#bfa571] hover:bg-[#bfa571]/20 hover:border-[#bfa571] hover:text-[#ebdcb2] hover:shadow-[0_0_15px_rgba(191,165,113,0.2)] rounded text-xs font-bold transition-all fantasy-font tracking-widest uppercase shadow-[0_0_10px_rgba(0,0,0,0.5)]">
                        {confirmLabel}
                    </button>
                </>
            }>
            <form onSubmit={handleSubmit} className="w-full">
                {label && <label className="block text-xs text-[#bfa571] mb-2 uppercase tracking-widest fantasy-font text-center opacity-80">{label}</label>}
                <input
                    ref={inputRef}
                    type="text"
                    value={value}
                    onChange={e => setValue(e.target.value)}
                    className="w-full bg-black/40 border border-[#333] rounded px-4 py-2 text-lg text-[#ebdcb2] focus:border-[#bfa571] focus:outline-none focus:shadow-[0_0_15px_rgba(191,165,113,0.1)] text-center font-serif placeholder-gray-700 transition-all"
                />
            </form>
        </BaseModal>
    );
};

interface AlertModalProps {
    open: boolean;
    title?: string;
    message: string;
    onClose: () => void;
}

export const AlertModal: React.FC<AlertModalProps> = ({
    open, title = "System Message", message, onClose
}) => {
    return (
        <BaseModal open={open} title={title} onClose={onClose}
            footer={
                <button onClick={onClose} className="px-8 py-2 bg-[#bfa571]/10 border border-[#bfa571]/60 text-[#bfa571] hover:bg-[#bfa571]/20 hover:border-[#bfa571] hover:text-[#ebdcb2] hover:shadow-[0_0_15px_rgba(191,165,113,0.2)] rounded text-xs font-bold transition-all fantasy-font tracking-widest uppercase shadow-[0_0_10px_rgba(0,0,0,0.5)]">
                    Close
                </button>
            }>
            <p className="whitespace-pre-wrap text-center font-cormorant text-gray-200/90 text-xl">{message}</p>
        </BaseModal>
    );
};
