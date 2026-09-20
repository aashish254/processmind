#!/bin/bash
# ProcessMind — Show Everything
# Opens the artifact browser and key outputs

BASE="/Users/aashish/Migrated_Caps/MASTERS CAP1"

echo "Opening ProcessMind artifact browser..."
open "$BASE/outputs/index.html"

echo ""
echo "All artifacts in outputs/demo/:"
ls -la "$BASE/outputs/demo/" | head -20
echo "... (52 files total)"

echo ""
echo "Thesis documents:"
ls -la "$BASE/thesis/"*.md "$BASE/thesis/"*.pdf "$BASE/thesis/"*.docx 2>/dev/null

echo ""
echo "To run the demo again:"
echo "  cd '$BASE'"
echo "  make demo"