#!/usr/bin/env python3
"""
Universal Domain Indexer & Fine-Tuning Template
Template system for creating specialized document indexing and model fine-tuning systems

Fork this template to create domain-specific versions for:
- Medical literature
- Legal documents  
- Engineering specifications
- Academic research
- Technical manuals
- etc.
"""

import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import re
import hashlib
import pickle
from abc import ABC, abstractmethod

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from queue import Queue

import requests
import faiss
import numpy as np


@dataclass 
class DomainConfig:
    """Configuration for a specific domain"""
    domain_name: str
    description: str
    file_types: List[str]
    section_patterns: List[str]  # Regex patterns for section identification
    subsection_patterns: List[str]  # Regex patterns for subsection identification
    chunk_size: int = 1000
    overlap_size: int = 200
    question_types: List[str] = None  # Types of questions to generate
    system_prompt: str = ""
    model_name: str = ""
    
    def __post_init__(self):
        if self.question_types is None:
            self.question_types = ["definition", "procedure", "specification", "comparison"]


@dataclass
class SubsectionFilter:
    """Filter for extracting specific subsections from documents"""
    name: str
    description: str
    include_patterns: List[str]  # Include sections matching these patterns
    exclude_patterns: List[str]  # Exclude sections matching these patterns
    min_length: int = 50  # Minimum character length
    max_length: int = 5000  # Maximum character length


class DocumentProcessor(ABC):
    """Abstract base class for document processors"""
    
    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """Extract raw text from document"""
        pass
    
    @abstractmethod
    def identify_sections(self, text: str, patterns: List[str]) -> List[Dict]:
        """Identify sections using patterns"""
        pass
    
    @abstractmethod
    def filter_subsections(self, sections: List[Dict], filters: List[SubsectionFilter]) -> List[Dict]:
        """Filter sections based on criteria"""
        pass


class SpecBookProcessor(DocumentProcessor):
    """Processor specifically for specification books"""
    
    def extract_text(self, file_path: str) -> str:
        """Extract text from spec books (PDF, DOCX, etc.)"""
        file_path = Path(file_path)
        
        if file_path.suffix.lower() == '.pdf':
            return self._extract_pdf_text(file_path)
        elif file_path.suffix.lower() in ['.docx', '.doc']:
            return self._extract_docx_text(file_path)
        elif file_path.suffix.lower() == '.txt':
            return file_path.read_text(encoding='utf-8')
        else:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF"""
        try:
            import PyPDF2
            text = ""
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logging.error(f"Error extracting PDF {file_path}: {e}")
            return ""
    
    def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from DOCX"""
        try:
            import docx
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logging.error(f"Error extracting DOCX {file_path}: {e}")
            return ""
    
    def identify_sections(self, text: str, patterns: List[str]) -> List[Dict]:
        """Identify sections using specification patterns"""
        sections = []
        
        # Common spec book patterns
        default_patterns = [
            r'^(\d+\.?\d*\.?\d*)\s+([A-Z][^.\n]*)',  # Numbered sections
            r'^([A-Z]{2,}[^.\n]*)',  # ALL CAPS headers
            r'^(SECTION\s+\d+[^.\n]*)',  # SECTION headers
            r'^(PART\s+\d+[^.\n]*)',  # PART headers
            r'^(DIVISION\s+\d+[^.\n]*)',  # DIVISION headers
        ]
        
        all_patterns = patterns + default_patterns
        
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if line matches a section pattern
            section_match = None
            for pattern in all_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    section_match = match
                    break
            
            if section_match:
                # Save previous section
                if current_section:
                    sections.append({
                        'title': current_section,
                        'content': '\n'.join(current_content),
                        'start_line': current_section_start,
                        'end_line': i - 1,
                        'word_count': len(' '.join(current_content).split())
                    })
                
                # Start new section
                current_section = line
                current_section_start = i
                current_content = []
            else:
                if current_section:
                    current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            sections.append({
                'title': current_section,
                'content': '\n'.join(current_content),
                'start_line': current_section_start,
                'end_line': len(lines),
                'word_count': len(' '.join(current_content).split())
            })
        
        return sections
    
    def filter_subsections(self, sections: List[Dict], filters: List[SubsectionFilter]) -> List[Dict]:
        """Filter sections based on subsection filters"""
        filtered_sections = []
        
        for section in sections:
            title = section['title']
            content = section['content']
            
            for filter_obj in filters:
                # Check include patterns
                include_match = False
                if filter_obj.include_patterns:
                    for pattern in filter_obj.include_patterns:
                        if re.search(pattern, title, re.IGNORECASE) or re.search(pattern, content, re.IGNORECASE):
                            include_match = True
                            break
                else:
                    include_match = True  # No include patterns means include all
                
                # Check exclude patterns
                exclude_match = False
                if filter_obj.exclude_patterns:
                    for pattern in filter_obj.exclude_patterns:
                        if re.search(pattern, title, re.IGNORECASE) or re.search(pattern, content, re.IGNORECASE):
                            exclude_match = True
                            break
                
                # Check length constraints
                content_length = len(content)
                length_ok = filter_obj.min_length <= content_length <= filter_obj.max_length
                
                if include_match and not exclude_match and length_ok:
                    section_copy = section.copy()
                    section_copy['filter_matched'] = filter_obj.name
                    filtered_sections.append(section_copy)
                    break  # Only match first applicable filter
        
        return filtered_sections


class TrainingDataGenerator:
    """Generates fine-tuning data from filtered sections"""
    
    def __init__(self, ollama_url: str = "http://10.0.0.36:11434", model_name: str = "qwen2.5-coder:7b"):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.session = requests.Session()
    
    def call_llm(self, prompt: str, max_retries: int = 3) -> str:
        """Call LLM via Ollama"""
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "top_p": 0.9,
                            "max_tokens": 500
                        }
                    },
                    timeout=120
                )
                response.raise_for_status()
                return response.json()["response"].strip()
            except Exception as e:
                logging.error(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return ""
    
    def generate_questions_from_section(self, section: Dict, domain_config: DomainConfig) -> List[Dict]:
        """Generate Q&A pairs from a section"""
        
        title = section['title']
        content = section['content']
        
        # Create domain-specific prompt
        prompt = f"""Based on this {domain_config.domain_name} document section, generate 2-3 high-quality question-answer pairs.

Section Title: {title}
Content: {content[:2000]}...

Focus on generating questions about:
{', '.join(domain_config.question_types)}

{domain_config.system_prompt}

Format as:
Q1: [Question]
A1: [Comprehensive answer]

Q2: [Question]
A2: [Comprehensive answer]

Q3: [Question]
A3: [Comprehensive answer]"""

        response = self.call_llm(prompt)
        return self._parse_qa_response(response, section)
    
    def _parse_qa_response(self, response: str, source_section: Dict) -> List[Dict]:
        """Parse Q&A pairs from LLM response"""
        qa_pairs = []
        
        lines = response.split('\n')
        current_q = ""
        current_a = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith(('Q1:', 'Q2:', 'Q3:', 'Question:')):
                if current_q and current_a:
                    qa_pairs.append({
                        "instruction": current_q,
                        "input": "",
                        "output": current_a,
                        "source_title": source_section.get('title', ''),
                        "source_filter": source_section.get('filter_matched', ''),
                        "metadata": {
                            "word_count": source_section.get('word_count', 0),
                            "section_type": source_section.get('filter_matched', 'unknown')
                        }
                    })
                current_q = line.split(':', 1)[1].strip()
                current_a = ""
            elif line.startswith(('A1:', 'A2:', 'A3:', 'Answer:')):
                current_a = line.split(':', 1)[1].strip()
            elif current_a and line:
                current_a += " " + line
        
        # Add final pair
        if current_q and current_a:
            qa_pairs.append({
                "instruction": current_q,
                "input": "",
                "output": current_a,
                "source_title": source_section.get('title', ''),
                "source_filter": source_section.get('filter_matched', ''),
                "metadata": {
                    "word_count": source_section.get('word_count', 0),
                    "section_type": source_section.get('filter_matched', 'unknown')
                }
            })
        
        return qa_pairs


class DomainIndexerApp:
    """Main GUI application for domain-specific indexing"""
    
    def __init__(self, config_file: str = None):
        self.root = tk.Tk()
        self.root.title("🔷 Domain Indexer & Fine-Tuning Template")
        self.root.geometry("800x600")
        
        # Load configuration
        self.config = self.load_config(config_file) if config_file else self.get_default_config()
        self.processor = SpecBookProcessor()
        self.generator = TrainingDataGenerator()
        
        # GUI Components
        self.setup_gui()
        
        # Processing state
        self.processing_queue = Queue()
        self.is_processing = False
        
    def load_config(self, config_file: str) -> DomainConfig:
        """Load domain configuration from file"""
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            return DomainConfig(**config_data)
        except Exception as e:
            messagebox.showerror("Config Error", f"Failed to load config: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> DomainConfig:
        """Get default configuration for specification books"""
        return DomainConfig(
            domain_name="Technical Specifications",
            description="Template for processing technical specification documents",
            file_types=[".pdf", ".docx", ".doc", ".txt"],
            section_patterns=[
                r'^(SECTION\s+\d+.*)',
                r'^(PART\s+[IVX\d]+.*)',
                r'^(\d+\.?\d*\.?\d*\s+[A-Z].*)',
            ],
            subsection_patterns=[
                r'^(\d+\.\d+\s+.*)',
                r'^([A-Z]\.\s+.*)',
            ],
            question_types=["definition", "procedure", "specification", "compliance"],
            system_prompt="Generate questions that test understanding of technical specifications, procedures, and compliance requirements.",
            model_name="Domain-Specific-Model"
        )
    
    def setup_gui(self):
        """Setup the GUI interface"""
        # Main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configuration tab
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.setup_config_tab(config_frame)
        
        # Filters tab
        filters_frame = ttk.Frame(notebook)
        notebook.add(filters_frame, text="Subsection Filters")
        self.setup_filters_tab(filters_frame)
        
        # Processing tab
        process_frame = ttk.Frame(notebook)
        notebook.add(process_frame, text="Document Processing")
        self.setup_process_tab(process_frame)
        
        # Results tab
        results_frame = ttk.Frame(notebook)
        notebook.add(results_frame, text="Training Data")
        self.setup_results_tab(results_frame)
    
    def setup_config_tab(self, frame):
        """Setup domain configuration tab"""
        # Domain info
        info_frame = ttk.LabelFrame(frame, text="Domain Configuration")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(info_frame, text="Domain Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.domain_name_var = tk.StringVar(value=self.config.domain_name)
        ttk.Entry(info_frame, textvariable=self.domain_name_var, width=40).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(info_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.description_var = tk.StringVar(value=self.config.description)
        ttk.Entry(info_frame, textvariable=self.description_var, width=40).grid(row=1, column=1, padx=5, pady=2)
        
        # File types
        types_frame = ttk.LabelFrame(frame, text="Supported File Types")
        types_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.file_types_var = tk.StringVar(value=", ".join(self.config.file_types))
        ttk.Entry(types_frame, textvariable=self.file_types_var, width=60).pack(padx=5, pady=5)
        
        # Model settings
        model_frame = ttk.LabelFrame(frame, text="Model Configuration")
        model_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(model_frame, text="Ollama URL:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.ollama_url_var = tk.StringVar(value="http://10.0.0.36:11434")
        ttk.Entry(model_frame, textvariable=self.ollama_url_var, width=30).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(model_frame, text="Base Model:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.base_model_var = tk.StringVar(value="qwen2.5-coder:7b")
        ttk.Entry(model_frame, textvariable=self.base_model_var, width=30).grid(row=1, column=1, padx=5, pady=2)
    
    def setup_filters_tab(self, frame):
        """Setup subsection filters tab"""
        # Filter list
        list_frame = ttk.LabelFrame(frame, text="Subsection Filters")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Filter listbox
        self.filters_listbox = tk.Listbox(list_frame, height=10)
        self.filters_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Filter buttons
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Add Filter", command=self.add_filter).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Edit Filter", command=self.edit_filter).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Delete Filter", command=self.delete_filter).pack(fill=tk.X, pady=2)
        
        # Default filters
        self.filters = [
            SubsectionFilter(
                name="Installation Procedures",
                description="Sections about installation methods and procedures",
                include_patterns=["install", "procedure", "method", "step"],
                exclude_patterns=["warranty", "contact"],
                min_length=100,
                max_length=3000
            ),
            SubsectionFilter(
                name="Technical Specifications", 
                description="Technical specifications and requirements",
                include_patterns=["specification", "requirement", "standard", "code"],
                exclude_patterns=["warranty", "legal"],
                min_length=50,
                max_length=2000
            )
        ]
        
        self.update_filters_display()
    
    def setup_process_tab(self, frame):
        """Setup document processing tab"""
        # File selection
        file_frame = ttk.LabelFrame(frame, text="Document Selection")
        file_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(file_frame, text="Select Documents", command=self.select_documents).pack(side=tk.LEFT, padx=5, pady=5)
        self.file_count_label = ttk.Label(file_frame, text="No documents selected")
        self.file_count_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Processing controls
        controls_frame = ttk.LabelFrame(frame, text="Processing Controls")
        controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.process_button = ttk.Button(controls_frame, text="Start Processing", command=self.start_processing)
        self.process_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.stop_button = ttk.Button(controls_frame, text="Stop Processing", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Progress display
        progress_frame = ttk.LabelFrame(frame, text="Processing Progress")
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, padx=5, pady=2)
        
        self.status_text = tk.Text(progress_frame, height=15, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(progress_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        self.status_text.config(yscrollcommand=scrollbar.set)
        
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Initialize
        self.selected_files = []
    
    def setup_results_tab(self, frame):
        """Setup training data results tab"""
        # Results summary
        summary_frame = ttk.LabelFrame(frame, text="Training Data Summary")
        summary_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.qa_count_label = ttk.Label(summary_frame, text="Q&A Pairs Generated: 0")
        self.qa_count_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Export controls
        export_frame = ttk.LabelFrame(frame, text="Export Training Data")
        export_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(export_frame, text="Export JSON", command=self.export_json).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(export_frame, text="Export JSONL", command=self.export_jsonl).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(export_frame, text="Create Model", command=self.create_model).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Results preview
        preview_frame = ttk.LabelFrame(frame, text="Training Data Preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.results_tree = ttk.Treeview(preview_frame, columns=("Question", "Source", "Filter"), show="tree headings")
        self.results_tree.heading("#0", text="ID")
        self.results_tree.heading("Question", text="Question")
        self.results_tree.heading("Source", text="Source Section")
        self.results_tree.heading("Filter", text="Filter Matched")
        
        self.results_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Initialize
        self.training_data = []
    
    def update_filters_display(self):
        """Update the filters listbox"""
        self.filters_listbox.delete(0, tk.END)
        for filter_obj in self.filters:
            self.filters_listbox.insert(tk.END, f"{filter_obj.name}: {filter_obj.description}")
    
    def add_filter(self):
        """Add new subsection filter"""
        dialog = FilterDialog(self.root)
        if dialog.result:
            self.filters.append(dialog.result)
            self.update_filters_display()
    
    def edit_filter(self):
        """Edit selected filter"""
        selection = self.filters_listbox.curselection()
        if selection:
            index = selection[0]
            dialog = FilterDialog(self.root, self.filters[index])
            if dialog.result:
                self.filters[index] = dialog.result
                self.update_filters_display()
    
    def delete_filter(self):
        """Delete selected filter"""
        selection = self.filters_listbox.curselection()
        if selection:
            index = selection[0]
            del self.filters[index]
            self.update_filters_display()
    
    def select_documents(self):
        """Select documents for processing"""
        filetypes = [
            ("All Supported", " ".join([f"*{ext}" for ext in self.config.file_types])),
            ("PDF files", "*.pdf"),
            ("Word documents", "*.docx *.doc"),
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Documents to Process",
            filetypes=filetypes
        )
        
        if files:
            self.selected_files = list(files)
            self.file_count_label.config(text=f"{len(files)} documents selected")
    
    def log_message(self, message: str):
        """Log message to status text widget"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update_idletasks()
    
    def start_processing(self):
        """Start document processing in background thread"""
        if not self.selected_files:
            messagebox.showwarning("No Files", "Please select documents to process first.")
            return
        
        if not self.filters:
            messagebox.showwarning("No Filters", "Please add at least one subsection filter.")
            return
        
        self.is_processing = True
        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Update generator with current settings
        self.generator.ollama_url = self.ollama_url_var.get()
        self.generator.model_name = self.base_model_var.get()
        
        # Start processing thread
        thread = threading.Thread(target=self.process_documents)
        thread.daemon = True
        thread.start()
    
    def stop_processing(self):
        """Stop document processing"""
        self.is_processing = False
        self.process_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.log_message("❌ Processing stopped by user")
    
    def process_documents(self):
        """Process documents in background thread"""
        try:
            total_files = len(self.selected_files)
            self.progress_bar['maximum'] = total_files
            self.training_data = []
            
            self.log_message(f"🚀 Starting processing of {total_files} documents")
            
            for i, file_path in enumerate(self.selected_files):
                if not self.is_processing:
                    break
                
                self.log_message(f"📄 Processing: {Path(file_path).name}")
                
                try:
                    # Extract text
                    text = self.processor.extract_text(file_path)
                    if not text:
                        self.log_message(f"⚠️  No text extracted from {Path(file_path).name}")
                        continue
                    
                    # Identify sections
                    sections = self.processor.identify_sections(text, self.config.section_patterns)
                    self.log_message(f"📋 Found {len(sections)} sections")
                    
                    # Filter subsections
                    filtered_sections = self.processor.filter_subsections(sections, self.filters)
                    self.log_message(f"🔍 {len(filtered_sections)} sections match filters")
                    
                    # Generate training data
                    for section in filtered_sections:
                        if not self.is_processing:
                            break
                        
                        qa_pairs = self.generator.generate_questions_from_section(section, self.config)
                        self.training_data.extend(qa_pairs)
                        self.log_message(f"💡 Generated {len(qa_pairs)} Q&A pairs from: {section['title'][:50]}...")
                        
                        time.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    self.log_message(f"❌ Error processing {Path(file_path).name}: {e}")
                
                # Update progress
                self.progress_bar['value'] = i + 1
                self.root.update_idletasks()
            
            self.log_message(f"✅ Processing complete! Generated {len(self.training_data)} Q&A pairs")
            self.update_results_display()
            
        except Exception as e:
            self.log_message(f"❌ Processing error: {e}")
        finally:
            self.is_processing = False
            self.process_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
    
    def update_results_display(self):
        """Update results tree with training data"""
        self.results_tree.delete(*self.results_tree.get_children())
        self.qa_count_label.config(text=f"Q&A Pairs Generated: {len(self.training_data)}")
        
        for i, qa_pair in enumerate(self.training_data):
            question = qa_pair['instruction'][:50] + "..." if len(qa_pair['instruction']) > 50 else qa_pair['instruction']
            source = qa_pair.get('source_title', 'Unknown')[:30] + "..." if len(qa_pair.get('source_title', '')) > 30 else qa_pair.get('source_title', 'Unknown')
            filter_name = qa_pair.get('source_filter', 'Unknown')
            
            self.results_tree.insert("", tk.END, text=str(i+1), values=(question, source, filter_name))
    
    def export_json(self):
        """Export training data as JSON"""
        if not self.training_data:
            messagebox.showwarning("No Data", "No training data to export.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export Training Data as JSON"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.training_data, f, indent=2)
                self.log_message(f"📄 Training data exported to: {filename}")
                messagebox.showinfo("Export Complete", f"Training data exported to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")
    
    def export_jsonl(self):
        """Export training data as JSONL"""
        if not self.training_data:
            messagebox.showwarning("No Data", "No training data to export.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".jsonl",
            filetypes=[("JSONL files", "*.jsonl"), ("All files", "*.*")],
            title="Export Training Data as JSONL"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    for qa_pair in self.training_data:
                        f.write(json.dumps(qa_pair) + '\n')
                self.log_message(f"📄 Training data exported to: {filename}")
                messagebox.showinfo("Export Complete", f"Training data exported to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export: {e}")
    
    def create_model(self):
        """Create fine-tuned model from training data"""
        if not self.training_data:
            messagebox.showwarning("No Data", "No training data available for model creation.")
            return
        
        # This would integrate with your model creation pipeline
        messagebox.showinfo("Model Creation", "Model creation feature would integrate with your Ollama fine-tuning pipeline here.")
    
    def run(self):
        """Run the application"""
        self.root.mainloop()


class FilterDialog:
    """Dialog for adding/editing subsection filters"""
    
    def __init__(self, parent, filter_obj: SubsectionFilter = None):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Subsection Filter")
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center the dialog
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.setup_dialog(filter_obj)
        
        # Wait for dialog to close
        self.dialog.wait_window()
    
    def setup_dialog(self, filter_obj):
        """Setup dialog widgets"""
        # Basic info
        info_frame = ttk.LabelFrame(self.dialog, text="Filter Information")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(info_frame, text="Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.name_var = tk.StringVar(value=filter_obj.name if filter_obj else "")
        ttk.Entry(info_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(info_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.desc_var = tk.StringVar(value=filter_obj.description if filter_obj else "")
        ttk.Entry(info_frame, textvariable=self.desc_var, width=40).grid(row=1, column=1, padx=5, pady=2)
        
        # Patterns
        patterns_frame = ttk.LabelFrame(self.dialog, text="Filter Patterns")
        patterns_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        ttk.Label(patterns_frame, text="Include Patterns (one per line):").pack(anchor=tk.W, padx=5, pady=2)
        self.include_text = tk.Text(patterns_frame, height=6, wrap=tk.WORD)
        self.include_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        ttk.Label(patterns_frame, text="Exclude Patterns (one per line):").pack(anchor=tk.W, padx=5, pady=2)
        self.exclude_text = tk.Text(patterns_frame, height=4, wrap=tk.WORD)
        self.exclude_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        # Length constraints
        length_frame = ttk.LabelFrame(self.dialog, text="Length Constraints")
        length_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(length_frame, text="Min Length:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.min_length_var = tk.IntVar(value=filter_obj.min_length if filter_obj else 50)
        ttk.Entry(length_frame, textvariable=self.min_length_var, width=10).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(length_frame, text="Max Length:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.max_length_var = tk.IntVar(value=filter_obj.max_length if filter_obj else 5000)
        ttk.Entry(length_frame, textvariable=self.max_length_var, width=10).grid(row=0, column=3, padx=5, pady=2)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel_clicked).pack(side=tk.RIGHT)
        
        # Populate existing data
        if filter_obj:
            self.include_text.insert(tk.END, '\n'.join(filter_obj.include_patterns))
            self.exclude_text.insert(tk.END, '\n'.join(filter_obj.exclude_patterns))
    
    def ok_clicked(self):
        """Handle OK button click"""
        try:
            include_patterns = [line.strip() for line in self.include_text.get("1.0", tk.END).strip().split('\n') if line.strip()]
            exclude_patterns = [line.strip() for line in self.exclude_text.get("1.0", tk.END).strip().split('\n') if line.strip()]
            
            self.result = SubsectionFilter(
                name=self.name_var.get(),
                description=self.desc_var.get(),
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                min_length=self.min_length_var.get(),
                max_length=self.max_length_var.get()
            )
            
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Invalid filter configuration: {e}")
    
    def cancel_clicked(self):
        """Handle Cancel button click"""
        self.dialog.destroy()


def create_domain_config_template(domain_name: str, output_file: str):
    """Create a domain configuration template file"""
    config = DomainConfig(
        domain_name=domain_name,
        description=f"Template configuration for {domain_name} domain",
        file_types=[".pdf", ".docx", ".doc", ".txt"],
        section_patterns=[
            r'^(SECTION\s+\d+.*)',
            r'^(PART\s+[IVX\d]+.*)',
            r'^(\d+\.?\d*\.?\d*\s+[A-Z].*)',
        ],
        subsection_patterns=[
            r'^(\d+\.\d+\s+.*)',
            r'^([A-Z]\.\s+.*)',
        ],
        question_types=["definition", "procedure", "specification", "compliance"],
        system_prompt=f"Generate questions that test understanding of {domain_name} concepts, procedures, and requirements.",
        model_name=f"{domain_name.replace(' ', '')}-Expert"
    )
    
    with open(output_file, 'w') as f:
        json.dump(asdict(config), f, indent=2)
    
    print(f"✅ Domain configuration template created: {output_file}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="🔷 Domain Indexer & Fine-Tuning Template")
    parser.add_argument("--config", "-c", help="Domain configuration file")
    parser.add_argument("--create-config", help="Create domain config template")
    parser.add_argument("--domain-name", default="Custom Domain", help="Domain name for config template")
    
    args = parser.parse_args()
    
    if args.create_config:
        create_domain_config_template(args.domain_name, args.create_config)
        return
    
    # Launch GUI application
    app = DomainIndexerApp(args.config)
    app.run()


if __name__ == "__main__":
    main()