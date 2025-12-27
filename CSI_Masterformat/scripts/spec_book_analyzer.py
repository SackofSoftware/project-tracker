#!/usr/bin/env python3
"""
Specification Book Structure Analyzer
Specialized version of domain indexer focused on spec book organization,
formatting, cross-references, standards, and manufacturer analysis
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# Import the base template
from domain_indexer_template import (
    DomainConfig, SubsectionFilter, DocumentProcessor, 
    TrainingDataGenerator, DomainIndexerApp
)


class SpecBookStructureAnalyzer(DocumentProcessor):
    """Specialized processor for analyzing spec book structure and organization"""
    
    def __init__(self):
        # Common spec book patterns
        self.section_patterns = [
            r'^(SECTION\s+\d{2}\s*\d{2}\s*\d{2}.*)',  # CSI format
            r'^(DIVISION\s+\d{1,2}.*)',                # Division headers
            r'^(PART\s+[123]\s*[-:]?\s*\w+.*)',       # Part 1, 2, 3
            r'^(\d+\.\d+\s+[A-Z].*)',                 # Numbered subsections
            r'^([A-Z]{3,}\s+[A-Z].*)'                 # ALL CAPS headers
        ]
        
        self.structure_indicators = [
            r'(SUBMITTALS?:?)',
            r'(QUALITY ASSURANCE:?)',
            r'(PRODUCTS?:?)',
            r'(MATERIALS?:?)',
            r'(EXECUTION:?)',
            r'(INSTALLATION:?)',
            r'(PERFORMANCE:?)',
            r'(WARRANTY:?)'
        ]
        
        self.cross_reference_patterns = [
            r'(refer\s+to\s+section\s+[\d\s]+)',
            r'(see\s+section\s+[\d\s]+)',
            r'(coordinate\s+with\s+[\w\s]+)',
            r'(division\s+\d+)',
            r'(specification\s+section\s+[\d\s]+)',
            r'(drawing\s+[\w\d\-]+)',
            r'(detail\s+[\w\d\-]+)',
            r'(schedule\s+[\w\d\-]+)'
        ]
        
        self.standard_patterns = [
            r'(ASTM\s+[A-Z]\s*\d+)',
            r'(ANSI\s+[A-Z]*\d+)',
            r'(AAMA\s+\d+)',
            r'(IGMA\s+[\w\d\-]+)',
            r'(AWS\s+[A-Z]*\d+)',
            r'(UL\s+\d+)',
            r'(IBC\s+[\d\s]*)',
            r'(NFPA\s+\d+)',
            r'(IEEE\s+\d+)',
            r'(ASHRAE\s+[\d\-]+)'
        ]
        
        self.manufacturer_patterns = [
            r'(basis\s+of\s+design:?\s*([\w\s,]+))',
            r'(manufacturer:?\s*([\w\s,]+))',
            r'(or\s+equal\s+by\s*([\w\s,]+))',
            r'(approved\s+manufacturers?:?\s*([\w\s,]+))',
            r'(model\s+no\.?\s*:?\s*([\w\d\-]+))',
            r'(catalog\s+no\.?\s*:?\s*([\w\d\-]+))',
            r'(substitution\s+criteria)',
            r'(pre\-approved\s+[\w\s]+)'
        ]
    
    def extract_text(self, file_path: str) -> str:
        """Extract text from spec documents"""
        return super().extract_text(file_path)
    
    def analyze_document_structure(self, text: str) -> Dict[str, Any]:
        """Analyze the overall structure of a spec document"""
        analysis = {
            'numbering_system': self._identify_numbering_system(text),
            'organizational_pattern': self._identify_organizational_pattern(text),
            'section_count': 0,
            'division_structure': {},
            'cross_references': [],
            'standards_cited': [],
            'manufacturers_mentioned': [],
            'formatting_patterns': []
        }
        
        # Count sections and analyze structure
        sections = self.identify_sections(text, self.section_patterns)
        analysis['section_count'] = len(sections)
        
        # Extract cross-references
        analysis['cross_references'] = self._extract_cross_references(text)
        
        # Extract standards
        analysis['standards_cited'] = self._extract_standards(text)
        
        # Extract manufacturers
        analysis['manufacturers_mentioned'] = self._extract_manufacturers(text)
        
        # Analyze formatting patterns
        analysis['formatting_patterns'] = self._analyze_formatting(text)
        
        return analysis
    
    def _identify_numbering_system(self, text: str) -> str:
        """Identify the numbering system used in the spec"""
        csi_pattern = r'SECTION\s+\d{2}\s*\d{2}\s*\d{2}'
        decimal_pattern = r'^\d+\.\d+'
        alpha_pattern = r'^[A-Z]\.'
        
        if re.search(csi_pattern, text):
            return "CSI MasterFormat"
        elif re.search(decimal_pattern, text, re.MULTILINE):
            return "Decimal Numbering"
        elif re.search(alpha_pattern, text, re.MULTILINE):
            return "Alphabetic Subsections"
        else:
            return "Custom/Mixed"
    
    def _identify_organizational_pattern(self, text: str) -> str:
        """Identify the organizational pattern (3-part, etc.)"""
        part_pattern = r'PART\s+[123]'
        matches = re.findall(part_pattern, text)
        
        if len(set(matches)) >= 3:
            return "3-Part CSI Format"
        elif len(set(matches)) >= 2:
            return "2-Part Format"
        else:
            return "Custom Organization"
    
    def _extract_cross_references(self, text: str) -> List[Dict[str, str]]:
        """Extract cross-references to other sections/drawings"""
        references = []
        
        for pattern in self.cross_reference_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                references.append({
                    'type': self._classify_reference_type(match.group(1)),
                    'reference': match.group(1).strip(),
                    'context': self._get_context(text, match.start(), match.end())
                })
        
        return references
    
    def _extract_standards(self, text: str) -> List[Dict[str, str]]:
        """Extract industry standards and codes"""
        standards = []
        
        for pattern in self.standard_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                standard_code = match.group(1).strip()
                standards.append({
                    'standard': standard_code,
                    'organization': self._classify_standard_org(standard_code),
                    'context': self._get_context(text, match.start(), match.end())
                })
        
        return standards
    
    def _extract_manufacturers(self, text: str) -> List[Dict[str, str]]:
        """Extract manufacturer information and product specifications"""
        manufacturers = []
        
        for pattern in self.manufacturer_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                manufacturers.append({
                    'type': self._classify_manufacturer_reference(match.group(0)),
                    'manufacturer': match.groups()[-1] if len(match.groups()) > 1 else match.group(1),
                    'context': self._get_context(text, match.start(), match.end())
                })
        
        return manufacturers
    
    def _analyze_formatting(self, text: str) -> List[str]:
        """Analyze formatting patterns in the document"""
        patterns = []
        
        # Check for consistent indentation
        lines = text.split('\n')
        indent_pattern = self._analyze_indentation(lines)
        if indent_pattern:
            patterns.append(f"Consistent indentation: {indent_pattern}")
        
        # Check for numbering consistency
        numbering_consistency = self._check_numbering_consistency(lines)
        if numbering_consistency:
            patterns.append(f"Numbering pattern: {numbering_consistency}")
        
        # Check for header formatting
        header_pattern = self._analyze_header_formatting(lines)
        if header_pattern:
            patterns.append(f"Header format: {header_pattern}")
        
        return patterns
    
    def _classify_reference_type(self, reference: str) -> str:
        """Classify the type of cross-reference"""
        reference_lower = reference.lower()
        
        if 'section' in reference_lower:
            return "Section Reference"
        elif 'division' in reference_lower:
            return "Division Reference"
        elif 'drawing' in reference_lower:
            return "Drawing Reference"
        elif 'coordinate' in reference_lower:
            return "Coordination Requirement"
        else:
            return "General Reference"
    
    def _classify_standard_org(self, standard: str) -> str:
        """Classify the standards organization"""
        prefix = standard.split()[0].upper()
        
        org_mapping = {
            'ASTM': 'American Society for Testing and Materials',
            'ANSI': 'American National Standards Institute',
            'AAMA': 'American Architectural Manufacturers Association',
            'IGMA': 'Insulating Glass Manufacturers Alliance',
            'AWS': 'American Welding Society',
            'UL': 'Underwriters Laboratories',
            'IBC': 'International Building Code',
            'NFPA': 'National Fire Protection Association',
            'IEEE': 'Institute of Electrical and Electronics Engineers',
            'ASHRAE': 'American Society of Heating, Refrigerating and Air-Conditioning Engineers'
        }
        
        return org_mapping.get(prefix, 'Unknown Organization')
    
    def _classify_manufacturer_reference(self, reference: str) -> str:
        """Classify the type of manufacturer reference"""
        reference_lower = reference.lower()
        
        if 'basis of design' in reference_lower:
            return "Basis of Design"
        elif 'or equal' in reference_lower:
            return "Approved Equal"
        elif 'approved' in reference_lower:
            return "Approved Manufacturer"
        elif 'model' in reference_lower:
            return "Product Model"
        elif 'substitution' in reference_lower:
            return "Substitution Criteria"
        else:
            return "General Manufacturer"
    
    def _get_context(self, text: str, start: int, end: int, context_size: int = 100) -> str:
        """Get context around a match"""
        context_start = max(0, start - context_size)
        context_end = min(len(text), end + context_size)
        return text[context_start:context_end].strip()
    
    def _analyze_indentation(self, lines: List[str]) -> Optional[str]:
        """Analyze indentation patterns"""
        # Simplified indentation analysis
        indent_levels = []
        for line in lines:
            if line.strip():
                leading_spaces = len(line) - len(line.lstrip())
                if leading_spaces > 0:
                    indent_levels.append(leading_spaces)
        
        if indent_levels:
            common_indent = max(set(indent_levels), key=indent_levels.count)
            return f"{common_indent} spaces"
        return None
    
    def _check_numbering_consistency(self, lines: List[str]) -> Optional[str]:
        """Check for consistent numbering patterns"""
        numbered_lines = []
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.', line):
                numbered_lines.append("decimal")
            elif re.match(r'^[A-Z]\.', line):
                numbered_lines.append("alpha")
            elif re.match(r'^\d+\)', line):
                numbered_lines.append("parenthetical")
        
        if numbered_lines:
            most_common = max(set(numbered_lines), key=numbered_lines.count)
            return f"{most_common} numbering"
        return None
    
    def _analyze_header_formatting(self, lines: List[str]) -> Optional[str]:
        """Analyze header formatting patterns"""
        header_patterns = []
        
        for line in lines:
            line = line.strip()
            if line.isupper() and len(line.split()) > 1:
                header_patterns.append("all caps")
            elif line and line[0].isupper() and ':' in line:
                header_patterns.append("title case with colon")
        
        if header_patterns:
            most_common = max(set(header_patterns), key=header_patterns.count)
            return most_common
        return None
    
    def identify_sections(self, text: str, patterns: List[str]) -> List[Dict]:
        """Enhanced section identification with structure analysis"""
        sections = super().identify_sections(text, patterns)
        
        # Enhance each section with structural analysis
        for section in sections:
            section['structure_analysis'] = self._analyze_section_structure(section['content'])
            section['cross_references'] = self._extract_cross_references(section['content'])
            section['standards'] = self._extract_standards(section['content'])
            section['manufacturers'] = self._extract_manufacturers(section['content'])
        
        return sections
    
    def _analyze_section_structure(self, content: str) -> Dict[str, Any]:
        """Analyze the internal structure of a section"""
        analysis = {
            'has_submittals': bool(re.search(r'SUBMITTALS?:?', content, re.IGNORECASE)),
            'has_quality_assurance': bool(re.search(r'QUALITY ASSURANCE:?', content, re.IGNORECASE)),
            'has_products': bool(re.search(r'PRODUCTS?:?', content, re.IGNORECASE)),
            'has_execution': bool(re.search(r'EXECUTION:?', content, re.IGNORECASE)),
            'subsection_count': len(re.findall(r'^\s*[A-Z]\.\s+', content, re.MULTILINE)),
            'list_items': len(re.findall(r'^\s*\d+\.\s+', content, re.MULTILINE))
        }
        
        # Determine section type based on content
        if analysis['has_submittals'] or analysis['has_quality_assurance']:
            analysis['section_type'] = "General Requirements"
        elif analysis['has_products']:
            analysis['section_type'] = "Products"
        elif analysis['has_execution']:
            analysis['section_type'] = "Execution"
        else:
            analysis['section_type'] = "Mixed/Custom"
        
        return analysis
    
    def filter_subsections(self, sections: List[Dict], filters: List[SubsectionFilter]) -> List[Dict]:
        """Enhanced filtering with structure-aware logic"""
        filtered_sections = []
        
        for section in sections:
            title = section['title']
            content = section['content']
            structure = section.get('structure_analysis', {})
            
            for filter_obj in filters:
                # Enhanced matching logic considering structure
                include_match = self._enhanced_pattern_matching(
                    title, content, structure, filter_obj.include_patterns
                )
                
                exclude_match = self._enhanced_pattern_matching(
                    title, content, structure, filter_obj.exclude_patterns
                )
                
                content_length = len(content)
                length_ok = filter_obj.min_length <= content_length <= filter_obj.max_length
                
                if include_match and not exclude_match and length_ok:
                    section_copy = section.copy()
                    section_copy['filter_matched'] = filter_obj.name
                    section_copy['match_score'] = self._calculate_match_score(
                        title, content, structure, filter_obj
                    )
                    filtered_sections.append(section_copy)
                    break
        
        return filtered_sections
    
    def _enhanced_pattern_matching(self, title: str, content: str, structure: Dict, patterns: List[str]) -> bool:
        """Enhanced pattern matching considering document structure"""
        if not patterns:
            return True
        
        # Standard text matching
        text_match = any(
            re.search(pattern, title, re.IGNORECASE) or re.search(pattern, content, re.IGNORECASE)
            for pattern in patterns
        )
        
        # Structure-based matching
        structure_match = False
        for pattern in patterns:
            pattern_lower = pattern.lower()
            if pattern_lower in ['submittals', 'submittal'] and structure.get('has_submittals'):
                structure_match = True
            elif pattern_lower in ['quality assurance', 'qa'] and structure.get('has_quality_assurance'):
                structure_match = True
            elif pattern_lower in ['products', 'materials'] and structure.get('has_products'):
                structure_match = True
            elif pattern_lower in ['execution', 'installation'] and structure.get('has_execution'):
                structure_match = True
        
        return text_match or structure_match
    
    def _calculate_match_score(self, title: str, content: str, structure: Dict, filter_obj: SubsectionFilter) -> float:
        """Calculate a match score for ranking filtered sections"""
        score = 0.0
        
        # Pattern match strength
        for pattern in filter_obj.include_patterns:
            title_matches = len(re.findall(pattern, title, re.IGNORECASE))
            content_matches = len(re.findall(pattern, content, re.IGNORECASE))
            score += (title_matches * 2 + content_matches) * 0.1
        
        # Structure relevance
        if structure.get('section_type') in ['General Requirements', 'Products', 'Execution']:
            score += 0.2
        
        # Content richness
        cross_ref_count = len(structure.get('cross_references', []))
        standards_count = len(structure.get('standards', []))
        score += (cross_ref_count * 0.05 + standards_count * 0.05)
        
        return min(score, 1.0)  # Cap at 1.0


class SpecAnalysisTrainingGenerator(TrainingDataGenerator):
    """Specialized training data generator for spec book structure analysis"""
    
    def __init__(self, ollama_url: str = "http://10.0.0.36:11434", model_name: str = "qwen2.5-coder:7b"):
        super().__init__(ollama_url, model_name)
        
    def generate_structure_questions(self, section: Dict, domain_config: DomainConfig) -> List[Dict]:
        """Generate questions focused on document structure and organization"""
        
        title = section['title']
        content = section['content'][:1500]  # Limit content for context
        structure = section.get('structure_analysis', {})
        cross_refs = section.get('cross_references', [])
        standards = section.get('standards', [])
        manufacturers = section.get('manufacturers', [])
        
        # Create context-aware prompt
        prompt = f"""Analyze this specification section for its STRUCTURE, ORGANIZATION, and CROSS-REFERENCES rather than technical content.

Section: {title}
Content Preview: {content}

Structure Analysis:
- Section Type: {structure.get('section_type', 'Unknown')}
- Has Submittals: {structure.get('has_submittals', False)}
- Has Products: {structure.get('has_products', False)}
- Cross-References Found: {len(cross_refs)}
- Standards Cited: {len(standards)}
- Manufacturers Mentioned: {len(manufacturers)}

Generate 2-3 questions about:
1. DOCUMENT STRUCTURE: How is this section organized? What format does it follow?
2. CROSS-REFERENCES: What other sections/drawings/standards does it reference?
3. MANUFACTURER/STANDARDS: How are products specified? What standards apply?

Focus on the META-ASPECTS of specification writing, not the technical content.

Format:
Q1: [Structure/Organization Question]
A1: [Analysis of document structure and formatting]

Q2: [Cross-Reference/Coordination Question]  
A2: [Analysis of references and coordination requirements]

Q3: [Standards/Manufacturer Question]
A3: [Analysis of how standards and products are specified]"""

        response = self.call_llm(prompt)
        qa_pairs = self._parse_qa_response(response, section)
        
        # Enhance Q&A pairs with metadata
        for qa in qa_pairs:
            qa['analysis_type'] = self._classify_question_type(qa['instruction'])
            qa['structural_elements'] = {
                'cross_references': len(cross_refs),
                'standards': len(standards), 
                'manufacturers': len(manufacturers),
                'section_type': structure.get('section_type')
            }
        
        return qa_pairs
    
    def _classify_question_type(self, question: str) -> str:
        """Classify the type of structural analysis question"""
        question_lower = question.lower()
        
        if any(word in question_lower for word in ['organize', 'structure', 'format', 'part']):
            return "structure_analysis"
        elif any(word in question_lower for word in ['reference', 'coordinate', 'section', 'drawing']):
            return "cross_reference"
        elif any(word in question_lower for word in ['standard', 'astm', 'code', 'performance']):
            return "standards_analysis"
        elif any(word in question_lower for word in ['manufacturer', 'product', 'model', 'equal']):
            return "manufacturer_analysis"
        elif any(word in question_lower for word in ['submittal', 'approval', 'documentation']):
            return "process_requirements"
        else:
            return "general_analysis"


class SpecBookAnalyzerApp(DomainIndexerApp):
    """Specialized GUI for spec book structure analysis"""
    
    def __init__(self, config_file: str = None):
        # Set up specialized configuration
        self.spec_config = DomainConfig(
            domain_name="Specification Book Structure Analysis",
            description="Analyze spec book organization, cross-references, and formatting",
            file_types=[".pdf", ".docx", ".doc", ".txt"],
            section_patterns=[
                r'^(SECTION\s+\d{2}\s*\d{2}\s*\d{2}.*)',
                r'^(DIVISION\s+\d{1,2}.*)',
                r'^(PART\s+[123]\s*[-:]?\s*\w+.*)',
            ],
            subsection_patterns=[
                r'^([A-Z]\.\s+.*)',
                r'^(\d+\.\d+\s+.*)',
            ],
            question_types=[
                "structure_analysis", "cross_reference", "standards_analysis",
                "manufacturer_analysis", "process_requirements"
            ],
            system_prompt="Focus on document structure, organization, cross-references, and specification patterns rather than technical content.",
            model_name="SpecStructure-Analyst"
        )
        
        super().__init__(config_file)
        
        # Override with specialized components
        self.processor = SpecBookStructureAnalyzer()
        self.generator = SpecAnalysisTrainingGenerator()
        self.config = self.spec_config
        
        # Set up specialized filters
        self.filters = self._get_specialized_filters()
        self.update_filters_display()
    
    def _get_specialized_filters(self) -> List[SubsectionFilter]:
        """Get specialized filters for spec book analysis"""
        return [
            SubsectionFilter(
                name="Cross-References and Coordination",
                description="Sections with references to other specs or coordination requirements",
                include_patterns=["refer to", "see section", "coordinate with", "division", "specification"],
                exclude_patterns=["warranty", "contact information", "end of section"],
                min_length=100,
                max_length=2000
            ),
            SubsectionFilter(
                name="Standards and Code References", 
                description="Sections citing industry standards and building codes",
                include_patterns=["ASTM", "ANSI", "AAMA", "IGMA", "standard", "code", "testing"],
                exclude_patterns=["warranty", "contact", "manufacturer contact"],
                min_length=50,
                max_length=1500
            ),
            SubsectionFilter(
                name="Manufacturer and Product Specifications",
                description="Sections specifying manufacturers, models, and substitutions", 
                include_patterns=["manufacturer", "basis of design", "or equal", "approved", "model"],
                exclude_patterns=["warranty", "maintenance", "contact information"],
                min_length=100,
                max_length=2000
            ),
            SubsectionFilter(
                name="Document Structure and Organization",
                description="Sections showing spec organization and formatting patterns",
                include_patterns=["part 1", "part 2", "part 3", "submittals", "products", "execution"],
                exclude_patterns=["end of section", "related sections"],
                min_length=200,
                max_length=3000
            ),
            SubsectionFilter(
                name="Submittal and Process Requirements",
                description="Requirements for approvals, documentation, and processes",
                include_patterns=["submittal", "shop drawing", "product data", "sample", "approval"],
                exclude_patterns=["warranty", "contact", "payment"],
                min_length=100,
                max_length=1500
            )
        ]
    
    def process_documents(self):
        """Enhanced document processing with structure analysis"""
        try:
            total_files = len(self.selected_files)
            self.progress_bar['maximum'] = total_files
            self.training_data = []
            
            self.log_message(f"🚀 Starting spec book structure analysis of {total_files} documents")
            
            for i, file_path in enumerate(self.selected_files):
                if not self.is_processing:
                    break
                
                self.log_message(f"📄 Analyzing: {Path(file_path).name}")
                
                try:
                    # Extract text
                    text = self.processor.extract_text(file_path)
                    if not text:
                        self.log_message(f"⚠️  No text extracted from {Path(file_path).name}")
                        continue
                    
                    # Analyze document structure
                    doc_analysis = self.processor.analyze_document_structure(text)
                    self.log_message(f"📋 Document uses {doc_analysis['numbering_system']} with {doc_analysis['section_count']} sections")
                    self.log_message(f"🔗 Found {len(doc_analysis['cross_references'])} cross-references, {len(doc_analysis['standards_cited'])} standards")
                    
                    # Identify sections with enhanced analysis
                    sections = self.processor.identify_sections(text, self.config.section_patterns)
                    
                    # Filter subsections
                    filtered_sections = self.processor.filter_subsections(sections, self.filters)
                    self.log_message(f"🔍 {len(filtered_sections)} sections match structural analysis filters")
                    
                    # Generate structure-focused training data
                    for section in filtered_sections:
                        if not self.is_processing:
                            break
                        
                        qa_pairs = self.generator.generate_structure_questions(section, self.config)
                        self.training_data.extend(qa_pairs)
                        
                        analysis_types = [qa.get('analysis_type', 'unknown') for qa in qa_pairs]
                        self.log_message(f"💡 Generated {len(qa_pairs)} structure Q&A pairs: {', '.join(set(analysis_types))}")
                        
                        time.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    self.log_message(f"❌ Error processing {Path(file_path).name}: {e}")
                
                # Update progress
                self.progress_bar['value'] = i + 1
                self.root.update_idletasks()
            
            # Analyze generated training data
            self._analyze_training_data()
            self.log_message(f"✅ Structure analysis complete! Generated {len(self.training_data)} specialized Q&A pairs")
            self.update_results_display()
            
        except Exception as e:
            self.log_message(f"❌ Processing error: {e}")
        finally:
            self.is_processing = False
            self.process_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
    
    def _analyze_training_data(self):
        """Analyze the generated training data for quality and coverage"""
        if not self.training_data:
            return
        
        analysis_types = {}
        for qa in self.training_data:
            analysis_type = qa.get('analysis_type', 'unknown')
            analysis_types[analysis_type] = analysis_types.get(analysis_type, 0) + 1
        
        self.log_message("📊 Training Data Analysis:")
        for analysis_type, count in sorted(analysis_types.items()):
            self.log_message(f"   {analysis_type}: {count} questions")


def create_spec_analysis_config():
    """Create a configuration file for spec book analysis"""
    config = DomainConfig(
        domain_name="Specification Book Structure Analysis",
        description="AI model specialized in analyzing spec book organization, formatting, cross-references, and structural patterns",
        file_types=[".pdf", ".docx", ".doc", ".txt"],
        section_patterns=[
            r'^(SECTION\s+\d{2}\s*\d{2}\s*\d{2}.*)',
            r'^(DIVISION\s+\d{1,2}.*)',
            r'^(PART\s+[123]\s*[-:]?\s*\w+.*)',
            r'^(\d+\.\d+\s+[A-Z].*)',
            r'^([A-Z]{3,}:?\s*$)'
        ],
        subsection_patterns=[
            r'^([A-Z]\.\s+.*)',
            r'^(\d+\.\d+\.\d+\s+.*)',
            r'^(SUBMITTALS?:?)',
            r'^(QUALITY ASSURANCE:?)',
            r'^(PRODUCTS?:?)',
            r'^(EXECUTION:?)'
        ],
        question_types=[
            "structure_analysis",
            "cross_reference", 
            "standards_analysis",
            "manufacturer_analysis",
            "process_requirements",
            "formatting_patterns"
        ],
        system_prompt="Analyze specification documents for their structural organization, cross-references, standards citations, manufacturer requirements, and formatting patterns. Focus on HOW specifications are written and organized rather than WHAT they specify.",
        model_name="SpecStructureAnalyst"
    )
    
    config_file = "spec_structure_analysis_config.json"
    with open(config_file, 'w') as f:
        json.dump(asdict(config), f, indent=2)
    
    print(f"✅ Spec structure analysis configuration created: {config_file}")
    return config_file


def main():
    """Main entry point for spec book analyzer"""
    import argparse
    
    parser = argparse.ArgumentParser(description="📋 Specification Book Structure Analyzer")
    parser.add_argument("--config", "-c", help="Configuration file")
    parser.add_argument("--create-config", action="store_true", help="Create spec analysis config")
    
    args = parser.parse_args()
    
    if args.create_config:
        create_spec_analysis_config()
        return
    
    # Launch specialized GUI
    app = SpecBookAnalyzerApp(args.config)
    app.run()


if __name__ == "__main__":
    main()