#!/usr/bin/env python3
"""
Enhanced script to extract checklists from the SR22T-Checklists.txt file and generate a JSON file.

Line patterns:
 #SECTION like #NORMAL, #ABNORMAL and #EMERGENCY are section headers single # followed by all caps
 ##title are sub section headers 
 ###title are checklists
 1. description ....... ACTION are checklist item
 a. description .... ACTION are sub checklist item
 (1)  description .... ACTION are sub sub checklist item
 Line in all caps followed by Caution or Advisory are CAS messages, the following line in all cap is the cas message repeated
 line of the form: PFD Alerts Window: "text description" provide the text description for the current CAS message relevant for that checklist
 line of text that don't have normal text during a checklist are comments for the checklist

 items spans multiple line, until the next pattern they should be merged.
"""

import json
import re
import os
import uuid
import argparse
import logging
import traceback
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, asdict, field

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the input and output files
INPUT_FILE = "SR22T-Checklists.txt"
OUTPUT_FILE = "SR22TG6-Checklists.json"

@dataclass
class ChecklistStep:
    id: str
    instruction: str
    action: str
    is_conditional: bool
    indent_level: int
    step_number: Optional[str]
    sub_steps: List['ChecklistStep'] = field(default_factory=list)

@dataclass
class Checklist:
    id: str
    title: str
    section: str
    subsection: Optional[str]
    cas: Optional[str] = None
    cas_type: Optional[str] = None
    cas_description: Optional[str] = None
    alert_message: Optional[str] = None
    steps: List[ChecklistStep] = field(default_factory=list)

def parse_checklist(file_path: str, output_path: str, verbose: bool = False) -> None:
    """
    Parse the checklist file and generate a JSON output.
    
    Args:
        file_path: Path to the input text file
        output_path: Path where the JSON file will be saved
        verbose: Whether to print detailed information about the parsing process
    """
    checklists: List[Checklist] = []
    current_checklist: Optional[Checklist] = None
    current_section: Optional[str] = None
    current_subsection: Optional[str] = None
    pending_cas: Optional[str] = None
    pending_cas_type: Optional[str] = None
    pending_cas_description: Optional[str] = None
    pending_pfd_alert: Optional[str] = None
    line_count = 0
    
    # Define regex patterns
    section_pattern = re.compile(r"^#([A-Z][A-Z0-9 ]+)$")
    subsection_pattern = re.compile(r"^##([A-Z].+)$")
    checklist_pattern = re.compile(r"^###(.+)$")
    item_pattern = re.compile(r"^(\s*)(?:(\d+)\.|\((\d+)\)|([a-z])\.)\s+(.+?)(?:\.\.\.\s*(.+))?$")
    cas_message_pattern = re.compile(r"^([A-Z][A-Z0-9 ]+)(?:\s+\(([^)]+)\))?(?:\s*-\s*(.+))?$")
    cas_message_line_pattern = re.compile(r"^([A-Z][A-Z0-9 ]+)(?:\s+Caution|Advisory)?$")
    pfd_alert_pattern = re.compile(r'^PFD Alerts Window: [""]([^""]+)[""]$')
    
    if verbose:
        logger.info(f"Opening input file: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error(f"Input file not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error reading input file: {str(e)}")
        raise
        
    # Process lines
    i = 0
    while i < len(lines):
        try:
            line = lines[i].rstrip()
            line_count += 1
            i += 1
            
            # Skip empty lines
            if not line:
                continue
            
            # Check for section header (#EMERGENCY, #ABNORMAL, #NORMAL)
            section_match = section_pattern.match(line)
            if section_match:
                current_section = section_match.group(1)
                if verbose:
                    logger.info(f"Found section: {current_section} at line {line_count}")
                continue
            
            # Check for subsection header
            subsection_match = subsection_pattern.match(line)
            if subsection_match:
                current_subsection = subsection_match.group(1)
                if verbose:
                    logger.info(f"Found subsection: {current_subsection} at line {line_count}")
                continue
            
            # Check for checklist title
            checklist_match = checklist_pattern.match(line)
            if checklist_match:
                # Add the previous checklist to the list if it exists
                if current_checklist and current_checklist.steps:
                    checklists.append(current_checklist)
                
                # Create new checklist
                current_checklist = Checklist(
                    id=str(uuid.uuid4()),
                    title=checklist_match.group(1).strip(),
                    section=current_section or "",
                    subsection=current_subsection,
                    steps=[],
                    cas=pending_cas,
                    cas_type=pending_cas_type,
                    cas_description=pending_cas_description,
                    alert_message=pending_pfd_alert
                )
                
                # Reset pending values after they've been assigned to a checklist
                if pending_cas or pending_pfd_alert:
                    if verbose:
                        logger.info(f"Associated CAS: {pending_cas} and PFD Alert: {pending_pfd_alert} with checklist: {current_checklist.title}")
                    pending_cas = None
                    pending_cas_type = None
                    pending_cas_description = None
                    pending_pfd_alert = None
                
                if verbose:
                    logger.info(f"Found checklist: {current_checklist.title} at line {line_count}")
                continue
            
            # Check for PFD Alerts Window message
            pfd_alert_match = pfd_alert_pattern.match(line)
            if pfd_alert_match:
                pending_pfd_alert = pfd_alert_match.group(1).strip()
                
                # If we already have a current checklist, associate the alert with it
                if current_checklist:
                    current_checklist.alert_message = pending_pfd_alert
                    if verbose:
                        logger.info(f"Associated PFD Alert: {pending_pfd_alert} with current checklist: {current_checklist.title}")
                    pending_pfd_alert = None
                else:
                    if verbose:
                        logger.info(f"Found PFD Alert: {pending_pfd_alert} at line {line_count} (pending association)")
                continue
            
            # Check for CAS message
            cas_match = cas_message_line_pattern.match(line)
            if cas_match and (not current_checklist or not item_pattern.match(line)):
                pending_cas = cas_match.group(1).strip()
                
                # Look ahead for CAS type (Caution/Advisory) if not in the current line
                if "Caution" in line:
                    pending_cas_type = "Caution"
                elif "Advisory" in line:
                    pending_cas_type = "Advisory"
                else:
                    # Check next line for CAS description or type
                    if i < len(lines):
                        next_line = lines[i].strip()
                        if next_line == pending_cas:
                            # Skip the repeated CAS line
                            i += 1
                        elif "Caution" in next_line:
                            pending_cas_type = "Caution"
                            i += 1
                        elif "Advisory" in next_line:
                            pending_cas_type = "Advisory"
                            i += 1
                
                # If we already have a current checklist, associate the CAS with it
                if current_checklist:
                    current_checklist.cas = pending_cas
                    current_checklist.cas_type = pending_cas_type
                    if verbose:
                        logger.info(f"Associated CAS: {pending_cas} ({pending_cas_type}) with current checklist: {current_checklist.title}")
                    pending_cas = None
                    pending_cas_type = None
                else:
                    if verbose:
                        logger.info(f"Found CAS message: {pending_cas} ({pending_cas_type}) at line {line_count} (pending association)")
                continue
            
            # Check for checklist step
            step_match = item_pattern.match(line)
            if step_match and current_checklist:
                indent, num1, num2, letter, content, action = step_match.groups()
                
                # Calculate indent level (2 spaces = 1 level)
                indent_level = len(indent) // 2 if indent else 0
                
                # Split content into instruction and action
                instruction = content.strip()
                action = action.strip() if action else ""
                
                # Check for continuation lines (look ahead)
                j = i
                while j < len(lines):
                    next_line = lines[j].rstrip()
                    # Skip empty lines
                    if not next_line:
                        j += 1
                        continue
                    
                    # If the next line starts a new pattern, break
                    if (section_pattern.match(next_line) or 
                        subsection_pattern.match(next_line) or 
                        checklist_pattern.match(next_line) or 
                        item_pattern.match(next_line) or 
                        cas_message_line_pattern.match(next_line) or 
                        pfd_alert_pattern.match(next_line)):
                        break
                    
                    # Otherwise, it's a continuation of the current step
                    if "..." in next_line:
                        # This is likely an action continuation
                        parts = next_line.split("...")
                        if len(parts) > 1:
                            if instruction and not "..." in instruction:
                                instruction += " " + parts[0].strip()
                            if action:
                                action += " " + parts[1].strip()
                            else:
                                action = parts[1].strip()
                    else:
                        # This is likely an instruction continuation
                        instruction += " " + next_line.strip()
                    
                    j += 1
                    i += 1
                
                # Remove dots from action text
                if action:
                    action = re.sub(r'\.+', '', action).strip()
                
                # Check if step is conditional
                is_conditional = instruction.lower().startswith(('if', 'when', 'verify'))
                
                # Determine step number format
                step_number = None
                if num1:  # "1", "2", etc.
                    step_number = num1
                    indent_level = 0
                elif num2:  # "(1)", "(2)", etc.
                    step_number = f"({num2})"
                    indent_level = 2
                elif letter:  # "a", "b", etc.
                    step_number = letter
                    indent_level = 1
                
                new_step = ChecklistStep(
                    id=str(uuid.uuid4()),
                    instruction=instruction,
                    action=action,
                    is_conditional=is_conditional,
                    indent_level=indent_level,
                    step_number=step_number,
                    sub_steps=[]
                )
                
                # Add step to appropriate parent based on indentation
                add_step_to_hierarchy(current_checklist, new_step, indent_level)
                
                if verbose:
                    logger.info(f"Found step: {step_number} - {instruction} at line {line_count}")
                continue
        except Exception as e:
            logger.error(f"Error processing line {line_count}: {line}")
            logger.error(f"Error details: {str(e)}")
            logger.debug(traceback.format_exc())
            # Continue processing the next line
            continue
    
    # Add the last checklist
    if current_checklist and current_checklist.steps:
        checklists.append(current_checklist)
    
    if verbose:
        logger.info(f"\nProcessing complete:")
        logger.info(f"Total lines processed: {line_count}")
        logger.info(f"Total checklists found: {len(checklists)}")
        logger.info(f"Writing output to: {output_path}")
    
    # Validate checklists
    validate_checklists(checklists, verbose)
    
    # Convert dataclasses to dictionaries for JSON serialization
    checklists_dict = dataclass_to_dict(checklists)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(checklists_dict, json_file, indent=4)
    except Exception as e:
        logger.error(f"Error writing output file: {str(e)}")
        raise

def add_step_to_hierarchy(checklist: Checklist, new_step: ChecklistStep, indent_level: int) -> None:
    """
    Add a step to the appropriate place in the checklist hierarchy based on its indent level.
    
    Args:
        checklist: The current checklist
        new_step: The new step to add
        indent_level: The indentation level of the new step
    """
    if indent_level == 0:
        # Top-level step
        checklist.steps.append(new_step)
        return
    
    # Find the appropriate parent step
    if not checklist.steps:
        # If no steps exist yet, add as top-level (shouldn't happen with well-formed input)
        logger.warning(f"Adding step with indent level {indent_level} as top-level because no parent steps exist")
        checklist.steps.append(new_step)
        return
    
    # Start with the most recent steps and work backwards
    for i in range(len(checklist.steps) - 1, -1, -1):
        if find_parent_and_add_step(checklist.steps[i], new_step, indent_level):
            return
    
    # If no appropriate parent found, add as top-level
    logger.warning(f"No appropriate parent found for step with indent level {indent_level}, adding as top-level")
    checklist.steps.append(new_step)

def find_parent_and_add_step(potential_parent: ChecklistStep, new_step: ChecklistStep, target_indent: int) -> bool:
    """
    Recursively find the appropriate parent step and add the new step as a sub-step.
    
    Args:
        potential_parent: A potential parent step
        new_step: The new step to add
        target_indent: The indentation level of the new step
        
    Returns:
        bool: True if the step was added, False otherwise
    """
    # Check if this is the direct parent (indent level should be exactly one less)
    if potential_parent.indent_level == target_indent - 1:
        potential_parent.sub_steps.append(new_step)
        return True
    
    # Check sub-steps in reverse order (most recent first)
    for i in range(len(potential_parent.sub_steps) - 1, -1, -1):
        if find_parent_and_add_step(potential_parent.sub_steps[i], new_step, target_indent):
            return True
    
    return False

def validate_checklists(checklists: List[Checklist], verbose: bool = False) -> None:
    """
    Validate the parsed checklists and log any issues.
    
    Args:
        checklists: List of parsed checklists
        verbose: Whether to print detailed validation information
    """
    issues_found = 0
    
    for checklist in checklists:
        # Check for missing essential fields
        if not checklist.title:
            logger.warning(f"Checklist with ID {checklist.id} is missing a title")
            issues_found += 1
        
        if not checklist.section:
            logger.warning(f"Checklist '{checklist.title}' is missing a section")
            issues_found += 1
        
        if not checklist.steps:
            logger.warning(f"Checklist '{checklist.title}' has no steps")
            issues_found += 1
        
        # Validate steps recursively
        issues_found += validate_steps(checklist.steps, checklist.title)
    
    if verbose:
        if issues_found:
            logger.warning(f"Validation complete: {issues_found} issues found")
        else:
            logger.info("Validation complete: No issues found")

def validate_steps(steps: List[ChecklistStep], checklist_title: str) -> int:
    """
    Recursively validate checklist steps and log any issues.
    
    Args:
        steps: List of steps to validate
        checklist_title: Title of the parent checklist for reference
        
    Returns:
        int: Number of issues found
    """
    issues_found = 0
    
    for step in steps:
        # Check for missing essential fields
        if not step.instruction:
            logger.warning(f"Step {step.step_number} in checklist '{checklist_title}' is missing an instruction")
            issues_found += 1
        
        # Check for inconsistent indentation
        if step.sub_steps and any(sub.indent_level <= step.indent_level for sub in step.sub_steps):
            logger.warning(f"Step {step.step_number} in checklist '{checklist_title}' has sub-steps with inconsistent indentation")
            issues_found += 1
        
        # Validate sub-steps recursively
        if step.sub_steps:
            issues_found += validate_steps(step.sub_steps, checklist_title)
    
    return issues_found

def dataclass_to_dict(obj):
    """
    Convert dataclasses to dictionaries for JSON serialization.
    
    Args:
        obj: The object to convert
        
    Returns:
        The converted object
    """
    if isinstance(obj, (Checklist, ChecklistStep)):
        return {k: dataclass_to_dict(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, list):
        return [dataclass_to_dict(item) for item in obj]
    return obj

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract checklists from SR22T-Checklists.txt and generate a JSON file.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-i', '--input', help='Input file path (default: SR22T-Checklists.txt)')
    parser.add_argument('-o', '--output', help='Output file path (default: SR22TG6-Checklists.json)')
    
    args = parser.parse_args()
    
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not script_dir:  # If script is run from current directory
        script_dir = os.getcwd()
    
    # Use command line arguments or defaults
    input_file = args.input or INPUT_FILE
    output_file = args.output or OUTPUT_FILE
    
    # Construct full paths
    input_path = os.path.join(script_dir, input_file)
    output_path = os.path.join(script_dir, output_file)
    
    # Check if input file exists
    if not os.path.exists(input_path):
        logger.error(f"Error: Input file '{input_file}' not found in {script_dir}")
        return
    
    try:
        logger.info(f"Processing {input_file}...")
        parse_checklist(input_path, output_path, args.verbose)
        logger.info(f"Successfully generated {output_file}")
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        logger.debug(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    main()
