"""
Skill validation service for validating skill zip files.

This module handles:
- Extracting and parsing SKILL.md frontmatter
- Validating skill structure and metadata
- Extracting pip requirements
"""

import io
import logging
import re
import zipfile
from typing import List, Optional, Tuple

import yaml

from langconnect.models.skill import (
    SkillMetadata,
    SkillValidationResult,
    SKILL_NAME_PATTERN,
    FORBIDDEN_WORDS,
)

log = logging.getLogger(__name__)


# YAML frontmatter regex: matches content between --- markers at the start of the file
FRONTMATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n',
    re.DOTALL
)


def extract_frontmatter(content: str) -> Tuple[Optional[dict], str]:
    """
    Extract YAML frontmatter from markdown content.

    Args:
        content: The full markdown content

    Returns:
        Tuple of (frontmatter dict or None, remaining content)
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, content

    try:
        frontmatter = yaml.safe_load(match.group(1))
        remaining = content[match.end():]
        return frontmatter, remaining
    except yaml.YAMLError as e:
        log.warning(f"Failed to parse YAML frontmatter: {e}")
        return None, content


def validate_skill_name(name: str) -> List[str]:
    """
    Validate a skill name and return list of errors.

    Args:
        name: The skill name to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not name:
        errors.append("Skill name is required")
        return errors

    if len(name) > 64:
        errors.append("Skill name must be 64 characters or less")

    if not SKILL_NAME_PATTERN.match(name):
        errors.append("Skill name must contain only lowercase letters, numbers, and hyphens")

    for word in FORBIDDEN_WORDS:
        if word in name.lower():
            errors.append(f"Skill name cannot contain reserved word: '{word}'")

    return errors


def validate_skill_description(description: str) -> List[str]:
    """
    Validate a skill description and return list of errors.

    Args:
        description: The skill description to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not description:
        errors.append("Skill description is required")
        return errors

    if len(description) > 1024:
        errors.append("Skill description must be 1024 characters or less")

    if len(description) < 10:
        errors.append("Skill description should be at least 10 characters")

    return errors


def validate_pip_requirements(requirements: Optional[List[str]]) -> List[str]:
    """
    Validate pip requirements list.

    Args:
        requirements: List of pip package names

    Returns:
        List of validation error messages (empty if valid)
    """
    if requirements is None:
        return []

    errors = []

    if not isinstance(requirements, list):
        errors.append("pip_requirements must be a list")
        return errors

    for req in requirements:
        if not isinstance(req, str):
            errors.append(f"Invalid pip requirement: {req} (must be a string)")
        elif not req.strip():
            errors.append("Empty pip requirement found")

    return errors


async def validate_skill_zip(file_content: bytes) -> SkillValidationResult:
    """
    Validate a skill zip file and extract metadata.

    The zip file must contain:
    - SKILL.md at the root with valid YAML frontmatter containing:
      - name: Skill name (required)
      - description: Skill description (required)
      - pip_requirements: List of pip packages (optional)

    Args:
        file_content: Raw bytes of the zip file

    Returns:
        SkillValidationResult with validation status and extracted metadata
    """
    errors: List[str] = []
    files: List[str] = []
    name: Optional[str] = None
    description: Optional[str] = None
    pip_requirements: Optional[List[str]] = None

    # Check if valid zip file
    try:
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zf:
            files = zf.namelist()

            # Check for SKILL.md at root
            skill_md_path = None
            for f in files:
                # Handle both "SKILL.md" and "folder/SKILL.md" patterns
                # We want SKILL.md at root (no directory prefix, or single top-level directory)
                parts = f.split('/')
                if parts[-1] == 'SKILL.md':
                    # Accept if it's at root or one level deep (common with zip extraction)
                    if len(parts) <= 2:
                        skill_md_path = f
                        break

            if not skill_md_path:
                errors.append("SKILL.md not found at root of zip file")
                return SkillValidationResult(
                    valid=False,
                    files=files,
                    errors=errors
                )

            # Read and parse SKILL.md
            try:
                skill_md_content = zf.read(skill_md_path).decode('utf-8')
            except Exception as e:
                errors.append(f"Failed to read SKILL.md: {e}")
                return SkillValidationResult(
                    valid=False,
                    files=files,
                    errors=errors
                )

            # Extract frontmatter
            frontmatter, _ = extract_frontmatter(skill_md_content)

            if frontmatter is None:
                errors.append("SKILL.md must have YAML frontmatter at the start (between --- markers)")
                return SkillValidationResult(
                    valid=False,
                    files=files,
                    errors=errors
                )

            # Extract and validate name
            name = frontmatter.get('name')
            if name:
                name_errors = validate_skill_name(name)
                errors.extend(name_errors)
            else:
                errors.append("SKILL.md frontmatter must contain 'name' field")

            # Extract and validate description
            description = frontmatter.get('description')
            if description:
                desc_errors = validate_skill_description(description)
                errors.extend(desc_errors)
            else:
                errors.append("SKILL.md frontmatter must contain 'description' field")

            # Extract and validate pip_requirements (optional)
            pip_requirements = frontmatter.get('pip_requirements')
            if pip_requirements is not None:
                pip_errors = validate_pip_requirements(pip_requirements)
                errors.extend(pip_errors)

    except zipfile.BadZipFile:
        errors.append("Invalid zip file format")
        return SkillValidationResult(
            valid=False,
            files=[],
            errors=errors
        )
    except Exception as e:
        errors.append(f"Failed to process zip file: {e}")
        return SkillValidationResult(
            valid=False,
            files=[],
            errors=errors
        )

    return SkillValidationResult(
        valid=len(errors) == 0,
        name=name,
        description=description,
        pip_requirements=pip_requirements,
        files=files,
        errors=errors
    )


def extract_skill_metadata(file_content: bytes) -> Optional[SkillMetadata]:
    """
    Extract SkillMetadata from a validated skill zip file.

    This should only be called after validate_skill_zip returns valid=True.

    Args:
        file_content: Raw bytes of the validated zip file

    Returns:
        SkillMetadata if extraction successful, None otherwise
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zf:
            # Find SKILL.md
            for f in zf.namelist():
                parts = f.split('/')
                if parts[-1] == 'SKILL.md' and len(parts) <= 2:
                    content = zf.read(f).decode('utf-8')
                    frontmatter, _ = extract_frontmatter(content)

                    if frontmatter:
                        return SkillMetadata(
                            name=frontmatter.get('name', ''),
                            description=frontmatter.get('description', ''),
                            pip_requirements=frontmatter.get('pip_requirements')
                        )
    except Exception as e:
        log.error(f"Failed to extract skill metadata: {e}")

    return None
