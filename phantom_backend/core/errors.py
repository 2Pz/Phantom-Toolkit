from __future__ import annotations


class PhantomError(RuntimeError):
    """Base error for the phantom backend."""


class ProcessNotFound(PhantomError):
    def __init__(self, process_name: str):
        super().__init__(f"Process not found: {process_name}")
        self.process_name = process_name


class ModuleNotFound(PhantomError):
    def __init__(self, module_name: str):
        super().__init__(f"Module not found in process: {module_name}")
        self.module_name = module_name


class SignatureConfigError(PhantomError):
    pass


class SignatureNotFound(SignatureConfigError):
    def __init__(self, symbol: str):
        super().__init__(f"Signature not configured for symbol: {symbol}")
        self.symbol = symbol


class PatternNotUnique(PhantomError):
    def __init__(self, symbol: str, matches: int):
        super().__init__(f"AOB pattern for '{symbol}' is not unique: {matches} matches")
        self.symbol = symbol
        self.matches = matches


class PatternNotFound(PhantomError):
    def __init__(self, symbol: str):
        super().__init__(f"AOB pattern for '{symbol}' not found (0 matches)")
        self.symbol = symbol
