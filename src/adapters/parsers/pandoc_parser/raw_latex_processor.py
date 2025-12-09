import re
from typing import Dict, List, Optional


class RawLatexProcessor:
    """
    Processes raw LaTeX blocks that Pandoc couldn't convert.
    Identifies content by what it contains, not by environment names.
    """
    
    def process_raw_block(self, latex_content: str) -> Dict:
        """
        Process a raw LaTeX block and extract metadata.
        
        Strategy: Check for actual content (includegraphics, etc.), 
        not environment tags (which could contain anything).
        
        Args:
            latex_content: The raw LaTeX string
            
        Returns:
            Dictionary with metadata including:
            - env_type: 'figure', 'unknown'
            - labels: List of extracted labels
            - images: List of image paths (for figures)
            - caption: Extracted caption text
            - should_create_asset: Whether to create dedicated asset node
        """
        # Check for includegraphics - this is what makes it a figure with an asset
        images = self._extract_images(latex_content)
        
        if images:
            # Has includegraphics → figure environment with image asset
            return self._process_figure(latex_content, images)
        else:
            # No image asset → keep as raw latex (could be TikZ, custom env, etc.)
            return self._process_unknown(latex_content)
    
    # ========== Processing Methods ==========
    
    def _process_figure(self, content: str, images: List[str]) -> Dict:
        """
        Process content that contains includegraphics.
        This should create a FigureNode with the image asset.
        """
        return {
            'env_type': 'figure',
            'labels': self._extract_labels(content),
            'images': images,
            'caption': self._extract_caption(content),
            'should_create_asset': True  # Create FigureNode
        }
    
    def _process_unknown(self, content: str) -> Dict:
        """
        Process unknown content (TikZ, custom environments, etc.).
        Keep as RawLatexNode to preserve information.
        """
        return {
            'env_type': 'unknown',
            'labels': self._extract_labels(content),
            'images': [],
            'caption': self._extract_caption(content),
            'should_create_asset': False  # Keep as RawLatexNode
        }
    
    # ========== Extraction Utilities ==========
    
    def _extract_labels(self, content: str) -> List[str]:
        """
        Extract all \label{...} commands.
        
        Returns:
            List of label strings (without \label{} wrapper)
        """
        return re.findall(r'\\label\{([^}]+)\}', content)
    
    def _extract_caption(self, content: str) -> Optional[str]:
        """
        Extract caption text from \caption{...} command.
        
        Returns:
            Caption text if found, None otherwise
        """
        match = re.search(r'\\caption\{([^}]+)\}', content)
        return match.group(1) if match else None
    
    def _extract_images(self, content: str) -> List[str]:
        """
        Extract all \includegraphics{...} paths.
        This is what determines if content has an image asset.
        
        Returns:
            List of image file paths
        """
        pattern = r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}'
        return re.findall(pattern, content)
