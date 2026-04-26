"""
DOME 2.2.2 Knowledge Migration Script
======================================
Migrates knowledge from fragmented agent workspaces to the centralized DOME_CORE knowledge hub.

This script:
1. Scans all agent workspaces for knowledge_hub folders
2. Migrates .jsonl lesson files
3. Migrates .md manifest and pattern files
4. Preserves folder structure (manifests/, lessons/, patterns/)
5. Generates migration report

Usage:
    python migrate_knowledge.py
"""

import os
import shutil
import json
from datetime import datetime
from typing import Dict, List
from pathlib import Path

# Configuration
AGENT_BASE_PATH = r"c:\Users\robis\Agentic_workflows"
DOME_CORE_PATH = r"D:\DOME_CORE"
KNOWLEDGE_HUB_PATH = os.path.join(DOME_CORE_PATH, "knowledge")

# Agent workspaces to scan
AGENTS = [
    "Alma_solutions",
    "Gabe_bidding_solution",
    "MLM_solutions",
    "Dondee_solutions",
    "Framing & Concrete_solutions",
    "test_agent"
]

class KnowledgeMigrator:
    def __init__(self):
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "agents_processed": 0,
            "files_migrated": 0,
            "bytes_migrated": 0,
            "errors": [],
            "details": {}
        }
    
    def ensure_hub_structure(self):
        """Ensure the centralized knowledge hub has the proper structure."""
        for subfolder in ["manifests", "lessons", "patterns"]:
            path = os.path.join(KNOWLEDGE_HUB_PATH, subfolder)
            os.makedirs(path, exist_ok=True)
    
    def migrate_agent_knowledge(self, agent_name: str) -> Dict:
        """Migrate knowledge from a single agent workspace."""
        agent_details = {
            "files_migrated": 0,
            "bytes_migrated": 0,
            "files": []
        }
        
        workspace_path = os.path.join(AGENT_BASE_PATH, agent_name)
        knowledge_path = os.path.join(workspace_path, "knowledge_hub")
        
        if not os.path.exists(knowledge_path):
            # Check for 'execution' folder as some agents may have knowledge there
            knowledge_path = os.path.join(workspace_path, "knowledge")
            if not os.path.exists(knowledge_path):
                print(f"  [WARNING] No knowledge folder found for {agent_name}")
                return agent_details
        
        # Process each subfolder
        for subfolder in ["manifests", "lessons", "patterns"]:
            source_folder = os.path.join(knowledge_path, subfolder)
            dest_folder = os.path.join(KNOWLEDGE_HUB_PATH, subfolder)
            
            if not os.path.exists(source_folder):
                continue
            
            # Migrate files
            for filename in os.listdir(source_folder):
                source_file = os.path.join(source_folder, filename)
                
                # Skip directories
                if os.path.isdir(source_file):
                    continue
                
                # Only migrate .jsonl and .md files
                if not (filename.endswith('.jsonl') or filename.endswith('.md')):
                    continue
                
                # Create unique filename if needed (prefix with agent name if conflict)
                dest_file = os.path.join(dest_folder, filename)
                if os.path.exists(dest_file):
                    # File exists, prefix with agent name
                    base, ext = os.path.splitext(filename)
                    new_filename = f"{agent_name}_{base}{ext}"
                    dest_file = os.path.join(dest_folder, new_filename)
                
                try:
                    # Copy file
                    shutil.copy2(source_file, dest_file)
                    file_size = os.path.getsize(source_file)
                    
                    agent_details["files_migrated"] += 1
                    agent_details["bytes_migrated"] += file_size
                    agent_details["files"].append({
                        "source": source_file,
                        "destination": dest_file,
                        "size_bytes": file_size
                    })
                    
                    print(f"    [OK] Migrated {filename} ({file_size} bytes)")
                    
                except Exception as e:
                    error_msg = f"Failed to migrate {source_file}: {str(e)}"
                    self.report["errors"].append(error_msg)
                    print(f"    [FAIL] {error_msg}")
        
        return agent_details
    
    def migrate_all(self):
        """Migrate knowledge from all agent workspaces."""
        print("=" * 60)
        print("DOME 2.2.2 Knowledge Migration")
        print("=" * 60)
        print(f"Source: {AGENT_BASE_PATH}")
        print(f"Destination: {KNOWLEDGE_HUB_PATH}")
        print("=" * 60)
        
        # Ensure hub structure exists
        self.ensure_hub_structure()
        print("[OK] Knowledge hub structure verified\n")
        
        # Migrate each agent
        for agent in AGENTS:
            print(f"Processing {agent}...")
            details = self.migrate_agent_knowledge(agent)
            
            if details["files_migrated"] > 0:
                self.report["agents_processed"] += 1
                self.report["files_migrated"] += details["files_migrated"]
                self.report["bytes_migrated"] += details["bytes_migrated"]
                self.report["details"][agent] = details
        
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        print(f"Agents processed: {self.report['agents_processed']}")
        print(f"Files migrated: {self.report['files_migrated']}")
        print(f"Bytes migrated: {self.report['bytes_migrated']:,}")
        print(f"Errors: {len(self.report['errors'])}")
        
        # Save report
        report_path = os.path.join(DOME_CORE_PATH, "logs", f"knowledge_migration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, indent=2)
        
        print(f"\nMigration report saved to: {report_path}")
        
        return self.report

if __name__ == "__main__":
    migrator = KnowledgeMigrator()
    migrator.migrate_all()
