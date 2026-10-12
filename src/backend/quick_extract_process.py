"""Wait for lifecycle containment before importing any document parser."""

import sys

if __name__ == "__main__" and sys.stdin.buffer.read(1) == b"G":
    from src.backend.quick_extract import main

    main()
