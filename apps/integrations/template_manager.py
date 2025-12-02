"""Template workflow management utilities."""
from __future__ import annotations

import json
import os
import logging
from typing import Dict, Any, List
from pathlib import Path

from conf.enhanced_logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

class WorkflowTemplate:
    """Represents a workflow template."""
    
    def __init__(self, name: str, file_path: str, description: str = ""):
        self.name = name
        self.file_path = file_path
        self.description = description
        self._data = None
    
    @property
    def data(self) -> Dict[str, Any]:
        """Load and return template data."""
        if self._data is None:
            self._load_template()
        return self._data
    
    def _load_template(self) -> None:
        """Load template from file."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
            logger.debug("Template loaded successfully", extra={
                "template_name": self.name,
                "file_path": self.file_path
            })
        except Exception as exc:
            logger.error("Failed to load template", extra={
                "template_name": self.name,
                "file_path": self.file_path,
                "error": str(exc)
            })
            self._data = {}
    
    def prepare_for_user(self, user_email: str) -> Dict[str, Any]:
        """
        Prepare template workflow data for a specific user.
        This removes user-specific credentials and configurations.
        """
        workflow_data = self.data.copy()
        
        # Remove specific credentials and user-specific data
        if "nodes" in workflow_data:
            for node in workflow_data["nodes"]:
                # Remove existing credential references
                if "credentials" in node:
                    del node["credentials"]
                
                # Clear webhook IDs to generate new ones
                if "webhookId" in node:
                    del node["webhookId"]
                
                # Remove user-specific calendar references
                if node.get("type") in ["n8n-nodes-base.googleCalendarTool", "n8n-nodes-base.googleCalendar"]:
                    if "parameters" in node and "calendar" in node["parameters"]:
                        # Reset calendar to require user configuration
                        node["parameters"]["calendar"] = {
                            "__rl": True,
                            "value": "",
                            "mode": "list"
                        }
        
        # Remove user-specific metadata
        if "meta" in workflow_data:
            workflow_data["meta"] = {
                "templateCredsSetupCompleted": False
            }
        
        # Clear tags or set default ones
        workflow_data["tags"] = []
        
        # Make workflow inactive by default so user can configure it
        workflow_data["active"] = False
        
        # Update name to indicate it's a template
        original_name = workflow_data.get("name", "Workflow")
        workflow_data["name"] = f"{original_name} (Template)"
        
        logger.info("Template prepared for user", extra={
            "template_name": self.name,
            "user_email": user_email,
            "workflow_name": workflow_data["name"]
        })
        
        return workflow_data


class TemplateManager:
    """Manages workflow templates."""
    
    def __init__(self):
        self.templates: Dict[str, WorkflowTemplate] = {}
        self._discover_templates()
    
    def _discover_templates(self) -> None:
        """Discover all available templates."""
        if not TEMPLATES_DIR.exists():
            logger.warning("Templates directory not found", extra={
                "templates_dir": str(TEMPLATES_DIR)
            })
            return
        
        for file_path in TEMPLATES_DIR.glob("*.json"):
            try:
                template_name = file_path.stem
                description = self._extract_description(file_path)
                
                template = WorkflowTemplate(
                    name=template_name,
                    file_path=str(file_path),
                    description=description
                )
                
                self.templates[template_name] = template
                
                logger.debug("Template discovered", extra={
                    "template_name": template_name,
                    "file_path": str(file_path)
                })
                
            except Exception as exc:
                logger.error("Failed to load template", extra={
                    "file_path": str(file_path),
                    "error": str(exc)
                })
    
    def _extract_description(self, file_path: Path) -> str:
        """Extract description from template file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("name", file_path.stem)
        except Exception:
            return file_path.stem
    
    def get_template(self, name: str) -> WorkflowTemplate | None:
        """Get a template by name."""
        return self.templates.get(name)
    
    def list_templates(self) -> List[WorkflowTemplate]:
        """List all available templates."""
        return list(self.templates.values())
    
    def get_default_template(self) -> WorkflowTemplate | None:
        """Get the default template for new users."""
        # First try to get the Google Calendar & Telegram template
        default_template = self.get_template("02-Google-Calendar&Telegram")
        
        if default_template:
            return default_template
        
        # Fallback to any available template
        templates = self.list_templates()
        if templates:
            return templates[0]
        
        return None


# Global template manager instance
_template_manager = None

def get_template_manager() -> TemplateManager:
    """Get the global template manager instance."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager