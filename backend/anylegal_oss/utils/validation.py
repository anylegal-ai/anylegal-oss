#!/usr/bin/env python3
"""
URL Validation System for legal-content sources
Validates that URLs actually contain the expected legal content
"""

import requests
import logging
import re
from typing import Dict, Tuple, Optional
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

class URLValidator:
    """Validates URLs to ensure they contain expected legal content."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AnyLegal-URL-Validator/1.0'
        })

    def extract_law_identifiers(self, content: str) -> Dict[str, str]:
        """Extract law identifiers from content."""
        identifiers = {}

        law_pattern = r'Federal\s+(?:Decree-?)?Law\s+No\.?\s*\(?(\d+)\)?\s+of\s+(\d{4})'
        match = re.search(law_pattern, content, re.IGNORECASE)
        if match:
            identifiers['law_number'] = match.group(1)
            identifiers['year'] = match.group(2)

        title_patterns = [
            r'Federal\s+(?:Decree-?)?Law\s+No\.?\s*\(?\d+\)?\s+of\s+\d{4}\s+(?:on|concerning|regarding)\s+(.+?)(?:\n|$)',
            r'# Federal\s+(?:Decree-?)?Law\s+No\.?\s*\(?\d+\)?\s+of\s+\d{4}\s*(.*?)(?:\n|##)',
        ]

        for pattern in title_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                identifiers['title'] = match.group(1).strip()
                break

        return identifiers

    def validate_url_content(self, url: str, expected_law_name: str) -> Tuple[bool, Dict]:
        """
        Validate that a URL contains the expected law content.

        Returns:
            (is_valid, validation_info)
        """
        validation_info = {
            'url': url,
            'expected_law': expected_law_name,
            'actual_content': None,
            'match_score': 0.0,
            'error': None,
            'checked_at': datetime.now().isoformat()
        }

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            content = response.text

            expected_identifiers = self.extract_law_identifiers(expected_law_name)

            actual_identifiers = self.extract_law_identifiers(content)
            validation_info['actual_content'] = actual_identifiers

            match_score = self.calculate_match_score(expected_identifiers, actual_identifiers)
            validation_info['match_score'] = match_score

            is_valid = match_score > 0.8

            if not is_valid:
                validation_info['error'] = f"Content mismatch. Expected: {expected_law_name}, Found: {actual_identifiers}"

            return is_valid, validation_info

        except Exception as e:
            validation_info['error'] = str(e)
            return False, validation_info

    def calculate_match_score(self, expected: Dict, actual: Dict) -> float:
        """Calculate similarity score between expected and actual identifiers."""
        if not expected or not actual:
            return 0.0

        score = 0.0
        total_weight = 0.0

        if 'law_number' in expected and 'law_number' in actual:
            if expected['law_number'] == actual['law_number']:
                score += 0.4
            total_weight += 0.4

        if 'year' in expected and 'year' in actual:
            if expected['year'] == actual['year']:
                score += 0.3
            total_weight += 0.3

        if 'title' in expected and 'title' in actual:
            title_score = self.calculate_title_similarity(expected['title'], actual['title'])
            score += title_score * 0.3
            total_weight += 0.3

        return score / total_weight if total_weight > 0 else 0.0

    def calculate_title_similarity(self, expected: str, actual: str) -> float:
        """Calculate title similarity using word overlap."""
        expected_words = set(re.findall(r'\w+', expected.lower()))
        actual_words = set(re.findall(r'\w+', actual.lower()))

        if not expected_words or not actual_words:
            return 0.0

        intersection = expected_words.intersection(actual_words)
        union = expected_words.union(actual_words)

        return len(intersection) / len(union)

def validate_links_file(links_file_path: str) -> Dict:
    """Validate all URLs in the links.txt file."""
    validator = URLValidator()
    validation_results = {
        'total_checked': 0,
        'valid_urls': 0,
        'invalid_urls': 0,
        'failed_urls': 0,
        'results': []
    }

    try:
        with open(links_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        current_law = None
        for line in lines:
            line = line.strip()

            if line and not line.startswith('['):
                current_law = line
                continue

            if line.startswith('[English Version]') and current_law:
                url_match = re.search(r'\(([^)]+)\)', line)
                if url_match:
                    url = url_match.group(1)

                    logger.info(f"Validating: {current_law}")
                    is_valid, info = validator.validate_url_content(url, current_law)

                    validation_results['total_checked'] += 1
                    if info.get('error'):
                        validation_results['failed_urls'] += 1
                    elif is_valid:
                        validation_results['valid_urls'] += 1
                    else:
                        validation_results['invalid_urls'] += 1

                    validation_results['results'].append(info)

                    if not is_valid:
                        logger.warning(f"URL validation failed for {current_law}: {info.get('error')}")

    except Exception as e:
        logger.error(f"Error validating links file: {e}")

    return validation_results

