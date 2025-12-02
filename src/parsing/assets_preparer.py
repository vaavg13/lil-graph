import os
import shutil
from pathlib import Path
from typing import List

def copy_assets(source_dir: Path, assets_output_dir: Path, image_paths: List[str]) -> None:
    """
    Copy referenced assets from the source directory to the assets output directory.
    
    Args:
        source_dir: The directory containing the original source files (and images).
        assets_output_dir: The directory to copy assets to.
        image_paths: List of relative image paths extracted from the AST.
    """
    if not assets_output_dir.exists():
        assets_output_dir.mkdir(parents=True, exist_ok=True)

    candidate_exts = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg"]
    
    for rel_path in image_paths:
        # Resolve potential extensions
        candidates = []
        path_obj = Path(rel_path)
        
        if path_obj.suffix:
             candidates.append(rel_path)
        else:
            # Try adding extensions
            for ext in candidate_exts[1:]:
                candidates.append(rel_path + ext)
        
        found_src: Path | None = None
        
        for candidate in candidates:
            # check directly relative to source_dir
            src = source_dir / candidate
            if src.exists():
                found_src = src
                break
            
            # check if it's just the filename in root (flattened structure sometimes)
            src_flat = source_dir / Path(candidate).name
            if src_flat.exists():
                found_src = src_flat
                break
        
        if found_src:
            # Determine destination
            # We preserve the relative directory structure if possible
            # e.g. figures/fig1.png -> assets/figures/fig1.png
            dest = assets_output_dir / rel_path
            if not dest.suffix and found_src.suffix:
                dest = dest.with_suffix(found_src.suffix)
                
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                shutil.copy2(found_src, dest)
            except Exception as e:
                print(f"Warning: Failed to copy asset {found_src} to {dest}: {e}")
        else:
            print(f"Warning: Asset not found: {rel_path} (checked in {source_dir})")
