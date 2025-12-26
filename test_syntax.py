#!/usr/bin/env python3
"""
Simple syntax validation test for broker implementations.
Does not require external dependencies.
"""
import sys
import ast
from pathlib import Path

def validate_python_file(file_path):
    """Validate Python file syntax."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def main():
    """Run syntax validation on key files."""
    print("=" * 60)
    print("SYNTAX VALIDATION TEST")
    print("=" * 60)
    print()
    
    files_to_check = [
        "brokers/kite_broker.py",
        "brokers/kotak_neo_broker.py",
        "config/config.py",
        "core/base_broker.py",
        "main.py"
    ]
    
    all_valid = True
    
    for file_path in files_to_check:
        full_path = Path(__file__).parent / file_path
        
        if not full_path.exists():
            print(f"⚠️  {file_path} - File not found")
            all_valid = False
            continue
        
        valid, error = validate_python_file(full_path)
        
        if valid:
            print(f"✅ {file_path} - Valid syntax")
        else:
            print(f"❌ {file_path} - Syntax error:")
            print(f"   {error}")
            all_valid = False
    
    print()
    print("=" * 60)
    
    if all_valid:
        print("✅ All files have valid Python syntax")
        print()
        print("Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Configure .env file with broker credentials")
        print("3. Test broker connection:")
        print("   - Kite: python main.py --broker kite --test-broker")
        print("   - KOTAK: python main.py --broker kotak --test-broker")
        return 0
    else:
        print("❌ Some files have syntax errors")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
