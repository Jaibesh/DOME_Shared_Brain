"""
DOME 2.0 - Version Tracker Module
==================================
Tracks versions of all framework components:
- Directives (SOPs)
- Prompt templates
- Tool registrations
- Clinic/tenant configurations
- Runtime policies

Version: 1.0.0
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from pydantic import BaseModel, Field

from execution.contracts import VersionInfo

# Setup Logging
try:
    from execution import utils
    logger = utils.setup_logging("version_tracker", "brain/logs/version_tracker.log")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("version_tracker")


# =============================================================================
# CONFIGURATION
# =============================================================================

VERSION_REGISTRY_PATH = "brain/version_registry.json"
DIRECTIVES_PATH = "directives"


# =============================================================================
# VERSION MODELS
# =============================================================================

class ComponentVersion(BaseModel):
    """Version metadata for a single component."""
    component_type: str  # directive, prompt, tool, config, policy
    component_id: str  # Unique identifier
    version: str
    content_hash: str  # MD5 hash of content for change detection
    file_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    changelog: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VersionRegistry(BaseModel):
    """Central registry of all component versions."""
    registry_version: str = "1.0.0"
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    components: Dict[str, ComponentVersion] = Field(default_factory=dict)


# =============================================================================
# VERSION TRACKER CLASS
# =============================================================================

class VersionTracker:
    """
    Tracks versions of all framework components.
    Provides versioning, change detection, and rollback capabilities.
    """

    _instance: Optional['VersionTracker'] = None

    def __init__(self, registry_path: str = VERSION_REGISTRY_PATH):
        self.registry_path = registry_path
        self.registry = self._load_registry()

    @classmethod
    def get_instance(cls) -> 'VersionTracker':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = VersionTracker()
        return cls._instance

    def _load_registry(self) -> VersionRegistry:
        """Load version registry from disk."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return VersionRegistry.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to load version registry: {e}")
        return VersionRegistry()

    def _save_registry(self):
        """Save version registry to disk."""
        try:
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(self.registry.model_dump(mode="json"), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save version registry: {e}")

    def _compute_hash(self, content: str) -> str:
        """Compute MD5 hash of content."""
        return hashlib.md5(content.encode()).hexdigest()

    def _parse_version(self, version: str) -> tuple[int, int, int]:
        """Parse version string into tuple."""
        parts = version.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    def _increment_version(
        self,
        current: str,
        level: str = "patch"
    ) -> str:
        """Increment version number."""
        major, minor, patch = self._parse_version(current)
        if level == "major":
            return f"{major + 1}.0.0"
        elif level == "minor":
            return f"{major}.{minor + 1}.0"
        else:  # patch
            return f"{major}.{minor}.{patch + 1}"

    def _make_key(self, component_type: str, component_id: str) -> str:
        """Create registry key for component."""
        return f"{component_type}:{component_id}"

    # -------------------------------------------------------------------------
    # REGISTRATION
    # -------------------------------------------------------------------------

    def register(
        self,
        component_type: str,
        component_id: str,
        content: str,
        file_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        version_override: Optional[str] = None
    ) -> ComponentVersion:
        """
        Register or update a component version.

        Args:
            component_type: Type of component (directive, prompt, tool, config, policy)
            component_id: Unique identifier
            content: Component content (for hash computation)
            file_path: Optional file path
            metadata: Optional metadata
            version_override: Override automatic version increment

        Returns:
            ComponentVersion with updated version info
        """
        key = self._make_key(component_type, component_id)
        content_hash = self._compute_hash(content)

        existing = self.registry.components.get(key)

        if existing:
            # Check if content changed
            if existing.content_hash == content_hash:
                logger.debug(f"No changes detected for {key}")
                return existing

            # Content changed, increment version
            new_version = version_override or self._increment_version(existing.version)
            changelog_entry = f"Updated from {existing.version} to {new_version} at {datetime.utcnow().isoformat()}"

            component = ComponentVersion(
                component_type=component_type,
                component_id=component_id,
                version=new_version,
                content_hash=content_hash,
                file_path=file_path,
                created_at=existing.created_at,
                updated_at=datetime.utcnow(),
                changelog=existing.changelog + [changelog_entry],
                metadata=metadata or existing.metadata
            )
            logger.info(f"Updated {key} from {existing.version} to {new_version}")

        else:
            # New component
            version = version_override or "1.0.0"
            component = ComponentVersion(
                component_type=component_type,
                component_id=component_id,
                version=version,
                content_hash=content_hash,
                file_path=file_path,
                metadata=metadata or {}
            )
            logger.info(f"Registered new component {key} at version {version}")

        self.registry.components[key] = component
        self.registry.last_updated = datetime.utcnow()
        self._save_registry()

        return component

    def get(
        self,
        component_type: str,
        component_id: str
    ) -> Optional[ComponentVersion]:
        """Get version info for a component."""
        key = self._make_key(component_type, component_id)
        return self.registry.components.get(key)

    def get_version(
        self,
        component_type: str,
        component_id: str
    ) -> str:
        """Get just the version string for a component."""
        component = self.get(component_type, component_id)
        return component.version if component else "0.0.0"

    def list_components(
        self,
        component_type: Optional[str] = None
    ) -> List[ComponentVersion]:
        """List all components, optionally filtered by type."""
        components = self.registry.components.values()
        if component_type:
            components = [c for c in components if c.component_type == component_type]
        return list(components)

    # -------------------------------------------------------------------------
    # DIRECTIVE SCANNING
    # -------------------------------------------------------------------------

    def scan_directives(self, directives_path: str = DIRECTIVES_PATH) -> Dict[str, ComponentVersion]:
        """
        Scan directives directory and register all directive files.

        Args:
            directives_path: Path to directives directory

        Returns:
            Dictionary of directive_id -> ComponentVersion
        """
        directives = {}

        if not os.path.exists(directives_path):
            logger.warning(f"Directives path not found: {directives_path}")
            return directives

        for filename in os.listdir(directives_path):
            if not filename.endswith(".md"):
                continue

            file_path = os.path.join(directives_path, filename)
            directive_id = filename.replace(".md", "")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                version = self.register(
                    component_type="directive",
                    component_id=directive_id,
                    content=content,
                    file_path=file_path,
                    metadata={"filename": filename}
                )
                directives[directive_id] = version

            except Exception as e:
                logger.warning(f"Failed to scan directive {filename}: {e}")

        logger.info(f"Scanned {len(directives)} directives")
        return directives

    # -------------------------------------------------------------------------
    # TOOL REGISTRATION
    # -------------------------------------------------------------------------

    def register_tool(
        self,
        tool_name: str,
        tool_function: Any,
        description: Optional[str] = None
    ) -> ComponentVersion:
        """
        Register a tool version.

        Args:
            tool_name: Tool name
            tool_function: The tool function
            description: Optional description

        Returns:
            ComponentVersion
        """
        # Create content string from function signature and docstring
        import inspect
        signature = str(inspect.signature(tool_function))
        docstring = inspect.getdoc(tool_function) or ""
        content = f"{signature}\n{docstring}"

        return self.register(
            component_type="tool",
            component_id=tool_name,
            content=content,
            metadata={
                "description": description or docstring[:100],
                "module": getattr(tool_function, "__module__", "unknown")
            }
        )

    def register_tools_from_registry(self, tool_registry: Dict[str, Any]) -> Dict[str, str]:
        """
        Register all tools from a tool registry.

        Args:
            tool_registry: Dictionary of tool_name -> tool_function

        Returns:
            Dictionary of tool_name -> version
        """
        versions = {}
        for name, tool in tool_registry.items():
            if callable(tool):
                version = self.register_tool(name, tool)
                versions[name] = version.version
        return versions

    # -------------------------------------------------------------------------
    # VERSION INFO EXPORT
    # -------------------------------------------------------------------------

    def get_version_info(self) -> VersionInfo:
        """
        Get VersionInfo object for use in contracts.

        Returns:
            VersionInfo populated with current versions
        """
        # Get directive versions
        directive_components = self.list_components("directive")
        directive_version = "1.0.0"
        if directive_components:
            # Use highest version among directives
            max_version = max(c.version for c in directive_components)
            directive_version = max_version

        # Get prompt versions
        prompt_components = self.list_components("prompt")
        prompt_version = "1.0.0"
        if prompt_components:
            max_version = max(c.version for c in prompt_components)
            prompt_version = max_version

        # Get tool versions
        tool_versions = {}
        for c in self.list_components("tool"):
            tool_versions[c.component_id] = c.version

        # Get policy version
        policy_components = self.list_components("policy")
        policy_version = "1.0.0"
        if policy_components:
            max_version = max(c.version for c in policy_components)
            policy_version = max_version

        # Get config version
        config_components = self.list_components("config")
        config_version = "1.0.0"
        if config_components:
            max_version = max(c.version for c in config_components)
            config_version = max_version

        return VersionInfo(
            directive_version=directive_version,
            prompt_version=prompt_version,
            tool_versions=tool_versions,
            policy_version=policy_version,
            config_version=config_version
        )

    def log_versions(self) -> Dict[str, str]:
        """
        Get a flat dictionary of all versions for logging.

        Returns:
            Dictionary of component keys -> versions
        """
        return {
            key: comp.version
            for key, comp in self.registry.components.items()
        }


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

def get_version_tracker() -> VersionTracker:
    """Get the singleton VersionTracker instance."""
    return VersionTracker.get_instance()


def get_current_versions() -> VersionInfo:
    """Convenience function to get current VersionInfo."""
    return get_version_tracker().get_version_info()


def register_directive(directive_id: str, content: str, file_path: Optional[str] = None) -> str:
    """Convenience function to register a directive."""
    version = get_version_tracker().register(
        component_type="directive",
        component_id=directive_id,
        content=content,
        file_path=file_path
    )
    return version.version


def register_prompt(prompt_id: str, content: str) -> str:
    """Convenience function to register a prompt template."""
    version = get_version_tracker().register(
        component_type="prompt",
        component_id=prompt_id,
        content=content
    )
    return version.version


def register_policy(policy_id: str, policy_config: Dict[str, Any]) -> str:
    """Convenience function to register a runtime policy."""
    version = get_version_tracker().register(
        component_type="policy",
        component_id=policy_id,
        content=json.dumps(policy_config, sort_keys=True)
    )
    return version.version


def scan_and_register_all():
    """Scan and register all directives."""
    tracker = get_version_tracker()
    tracker.scan_directives()
    logger.info("Scanned and registered all directives")
