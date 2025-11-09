# transport_registry.py - Auto-discovery and registration for transport protocols

import importlib
import inspect
import pkgutil
from typing import Dict, Type, Optional
from pathlib import Path
from transport import TransportProtocol


class TransportRegistry:
    """
    Auto-discovers and registers transport implementations.
    
    Automatically finds all Python files starting with "transport_" in the
    same directory, imports them, and registers TransportProtocol subclasses.
    
    This allows adding new transports by simply creating a new file:
    1. Create transport_myservice.py
    2. Define a class that inherits from TransportProtocol
    3. Done - it's automatically available
    """
    
    def __init__(self):
        self._transports: Dict[str, Type[TransportProtocol]] = {}
        self._discover_transports()
    
    def _discover_transports(self):
        """
        Auto-discover transport implementations.
        
        Searches for all modules starting with "transport_" in the current
        directory and registers TransportProtocol subclasses.
        """
        # Get the directory containing this file
        registry_dir = Path(__file__).parent
        
        # Find all transport_*.py files
        for file_path in registry_dir.glob("transport_*.py"):
            module_name = file_path.stem  # Filename without .py
            
            try:
                # Import the module
                module = importlib.import_module(module_name)
                
                # Find all classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if it's a TransportProtocol subclass (but not the base)
                    if (issubclass(obj, TransportProtocol) and 
                        obj is not TransportProtocol and
                        obj.__module__ == module_name):
                        
                        # Register using the class name
                        self._transports[name] = obj
                        
            except Exception as e:
                print(f"Warning: Failed to import {module_name}: {e}")
    
    def get(self, transport_name: str) -> Optional[Type[TransportProtocol]]:
        """
        Get a transport class by name.
        
        Args:
            transport_name: Name of the transport class (e.g., "OllamaTransport")
        
        Returns:
            Transport class or None if not found
        """
        return self._transports.get(transport_name)
    
    def get_by_provider(self, provider: str) -> Optional[Type[TransportProtocol]]:
        """
        Get a transport class by provider name.
        
        Maps common provider names to transport classes:
        - "ollama" -> OllamaTransport
        - "huggingface" or "hf" -> HuggingFaceTransport
        - "openai" -> OpenAITransport
        - etc.
        
        Args:
            provider: Provider name (case-insensitive)
        
        Returns:
            Transport class or None if not found
        """
        provider = provider.lower()
        
        # Common mappings
        mappings = {
            "ollama": "OllamaTransport",
            "huggingface": "HuggingFaceTransport",
            "hf": "HuggingFaceTransport",
            "openai": "OpenAITransport",
            "anthropic": "AnthropicTransport",
            "claude": "AnthropicTransport",
            "google": "GoogleGeminiTransport",
            "gemini": "GoogleGeminiTransport",
            "external": "ExternalAPITransport",
        }
        
        transport_name = mappings.get(provider)
        if transport_name:
            return self._transports.get(transport_name)
        
        # Try case-insensitive search
        for name, transport_class in self._transports.items():
            if provider in name.lower():
                return transport_class
        
        return None
    
    def list_available(self) -> list[str]:
        """Return list of all registered transport class names."""
        return sorted(self._transports.keys())
    
    def create(
        self,
        transport_name: str,
        **kwargs
    ) -> Optional[TransportProtocol]:
        """
        Create a transport instance by name.
        
        Args:
            transport_name: Name of the transport class
            **kwargs: Arguments to pass to the transport constructor
        
        Returns:
            Transport instance or None if not found
        
        Example:
            registry = TransportRegistry()
            ollama = registry.create("OllamaTransport", base_url="http://localhost:11434")
        """
        transport_class = self.get(transport_name)
        if transport_class:
            return transport_class(**kwargs)
        return None
    
    def create_by_provider(
        self,
        provider: str,
        **kwargs
    ) -> Optional[TransportProtocol]:
        """
        Create a transport instance by provider name.
        
        Args:
            provider: Provider name (case-insensitive)
            **kwargs: Arguments to pass to the transport constructor
        
        Returns:
            Transport instance or None if not found
        
        Example:
            registry = TransportRegistry()
            ollama = registry.create_by_provider("ollama", base_url="http://localhost:11434")
        """
        transport_class = self.get_by_provider(provider)
        if transport_class:
            return transport_class(**kwargs)
        return None


# Global registry instance
_global_registry = None

def get_transport_registry() -> TransportRegistry:
    """Get the global transport registry (singleton pattern)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TransportRegistry()
    return _global_registry


# Convenience functions
def list_transports() -> list[str]:
    """List all available transport names."""
    return get_transport_registry().list_available()


def create_transport(transport_name: str, **kwargs) -> Optional[TransportProtocol]:
    """Create a transport by name."""
    return get_transport_registry().create(transport_name, **kwargs)


def create_transport_by_provider(provider: str, **kwargs) -> Optional[TransportProtocol]:
    """Create a transport by provider name."""
    return get_transport_registry().create_by_provider(provider, **kwargs)
