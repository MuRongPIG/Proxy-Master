#!/usr/bin/env python3
"""
Proxy Pipeline Runner
Executes getproxy.py to scrape proxies, then runs proxy_benchmark.py to test them.
This script combines both operations into a single pipeline.
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def run_script(script_name, description):
    """Run a Python script and return success status."""
    print(f"\n{'='*60}")
    print(f"Starting: {description}")
    print(f"Script: {script_name}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        # Run the script
        result = subprocess.run([sys.executable, script_name], 
                              capture_output=False, 
                              text=True, 
                              check=True)
        
        elapsed = time.time() - start_time
        print(f"\n✅ {description} completed successfully in {elapsed:.2f}s")
        return True
        
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print(f"\n❌ {description} failed after {elapsed:.2f}s")
        print(f"Exit code: {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n❌ Script not found: {script_name}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ Unexpected error in {description} after {elapsed:.2f}s: {e}")
        return False

def check_required_files():
    """Check if required files exist after getproxy.py runs."""
    required_files = ['http.txt', 'socks4.txt', 'socks5.txt']
    missing_files = []
    
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"\n⚠️  Warning: Missing required files: {', '.join(missing_files)}")
        print("This may cause proxy_benchmark.py to skip some proxy types.")
        return False
    
    print(f"\n✅ All required proxy files found: {', '.join(required_files)}")
    return True

def check_output_files():
    """Check if output files were created in the Output folder."""
    output_dir = Path('Output')
    if not output_dir.exists():
        print(f"\n❌ Output directory not found: {output_dir}")
        return False
    
    expected_files = [
        'MBProxies.txt',
        'proxy_benchmark_results.csv', 
        'proxy_history.csv'
    ]
    
    found_files = []
    missing_files = []
    
    for file in expected_files:
        file_path = output_dir / file
        if file_path.exists():
            size = file_path.stat().st_size
            found_files.append(f"  ✅ {file} ({size} bytes)")
        else:
            missing_files.append(f"  ❌ {file} (not found)")
    
    print(f"\nOutput files in {output_dir}/:")
    for file_info in found_files:
        print(file_info)
    
    if missing_files:
        print("\nMissing files:")
        for file_info in missing_files:
            print(file_info)
        return False
    
    return True

def main():
    """Main pipeline execution."""
    print("🚀 Proxy Pipeline Starting...")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    # Step 1: Run getproxy.py
    if not run_script("getproxy.py", "Proxy Scraping"):
        print("\n❌ Pipeline failed at proxy scraping step. Exiting.")
        sys.exit(1)
    
    # Check if required files were created
    check_required_files()
    
    # Step 2: Run proxy_benchmark.py
    if not run_script("proxy_benchmark.py", "Proxy Benchmarking"):
        print("\n❌ Pipeline failed at proxy benchmarking step.")
        print("Proxy files were created, but benchmarking failed.")
        sys.exit(1)
    
    # Check if output files were created
    if not check_output_files():
        print("\n⚠️  Warning: Some expected output files are missing.")
        print("The pipeline may not have completed fully.")
    
    # Pipeline completed successfully
    print(f"\n{'='*60}")
    print("🎉 Proxy Pipeline Completed Successfully!")
    print(f"{'='*60}")
    print(f"\nPipeline completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
