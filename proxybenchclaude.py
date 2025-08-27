#!/usr/bin/env python3
"""
Proxy Pipeline Coordinator
Runs the complete proxy collection and benchmarking pipeline
"""

import sys
import subprocess
import time
import os
from pathlib import Path

def run_command(command, description, timeout_minutes=30):
    """Run a command with timeout and error handling."""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        # Run with timeout
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ {description} completed successfully in {elapsed:.1f}s")
            if result.stdout.strip():
                print("📋 Output:")
                print(result.stdout.strip())
            return True
        else:
            print(f"❌ {description} failed (exit code: {result.returncode})")
            if result.stderr.strip():
                print("🚨 Error output:")
                print(result.stderr.strip())
            if result.stdout.strip():
                print("📋 Standard output:")
                print(result.stdout.strip())
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} timed out after {timeout_minutes} minutes")
        return False
    except Exception as e:
        print(f"💥 {description} failed with exception: {e}")
        return False

def check_proxy_files():
    """Check if proxy files exist and show counts."""
    proxy_files = ['http.txt', 'socks5.txt', 'socks4.txt']
    total_proxies = 0
    
    print("\n📊 Proxy file status:")
    for file in proxy_files:
        if os.path.exists(file):
            try:
                with open(file, 'r') as f:
                    count = sum(1 for line in f if line.strip())
                print(f"   ✅ {file}: {count:,} proxies")
                total_proxies += count
            except Exception as e:
                print(f"   ❌ {file}: Error reading file - {e}")
        else:
            print(f"   ❌ {file}: File not found")
    
    print(f"   📈 Total proxies: {total_proxies:,}")
    return total_proxies > 0

def check_benchmark_results():
    """Check benchmark results and show summary."""
    output_dir = Path("Output")
    
    if not output_dir.exists():
        print("❌ Output directory not found")
        return False
    
    print(f"\n📊 Benchmark results:")
    
    # Check key output files
    files_to_check = [
        ("MBProxies.txt", "Final proxy list"),
        ("MBProxiesAll.txt", "All working proxies"),
        ("proxy_benchmark_results.csv", "Detailed results"),
        ("proxy_history.csv", "Historical data")
    ]
    
    results_found = False
    
    for filename, description in files_to_check:
        filepath = output_dir / filename
        if filepath.exists():
            try:
                if filename.endswith('.txt'):
                    with open(filepath, 'r') as f:
                        count = sum(1 for line in f if line.strip())
                    print(f"   ✅ {filename}: {count:,} entries ({description})")
                else:
                    size = filepath.stat().st_size
                    print(f"   ✅ {filename}: {size:,} bytes ({description})")
                results_found = True
            except Exception as e:
                print(f"   ⚠️  {filename}: Error reading - {e}")
        else:
            print(f"   ❌ {filename}: Not found ({description})")
    
    return results_found

def main():
    """Main pipeline execution."""
    print("🎯 Proxy Collection and Benchmarking Pipeline")
    print("=" * 50)
    
    pipeline_start = time.time()
    
    # Check Python version
    python_version = sys.version_info
    print(f"🐍 Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 8):
        print("⚠️  Warning: Python 3.8+ recommended for optimal performance")
    
    # Create output directory
    output_dir = Path("Output")
    output_dir.mkdir(exist_ok=True)
    print(f"📁 Output directory: {output_dir.absolute()}")
    
    # Step 1: Collect proxies
    print(f"\n{'🌐 STEP 1: PROXY COLLECTION':=^60}")
    
    if not run_command("python getproxy.py", "Proxy Collection", timeout_minutes=25):
        print("❌ Proxy collection failed - aborting pipeline")
        return 1
    
    # Verify proxy files were created
    if not check_proxy_files():
        print("❌ No proxy files were created - aborting pipeline")
        return 1
    
    # Step 2: Benchmark proxies
    print(f"\n{'⚡ STEP 2: PROXY BENCHMARKING':=^60}")
    
    if not run_command("python proxy_benchmark.py", "Proxy Benchmarking", timeout_minutes=35):
        print("❌ Proxy benchmarking failed")
        # Don't exit here - we might have partial results
    
    # Step 3: Verify results
    print(f"\n{'📊 STEP 3: RESULTS VERIFICATION':=^60}")
    
    if not check_benchmark_results():
        print("⚠️  Benchmark results incomplete or missing")
        return 1
    
    # Pipeline summary
    total_elapsed = time.time() - pipeline_start
    print(f"\n{'🎉 PIPELINE COMPLETE':=^60}")
    print(f"⏱️  Total execution time: {total_elapsed:.1f} seconds ({total_elapsed/60:.1f} minutes)")
    
    # Show final proxy counts
    mb_proxies_file = output_dir / "MBProxies.txt"
    mb_all_file = output_dir / "MBProxiesAll.txt"
    
    if mb_proxies_file.exists():
        with open(mb_proxies_file, 'r') as f:
            final_count = sum(1 for line in f if line.strip())
        print(f"🎯 Final proxy list: {final_count} proxies")
        
        if mb_all_file.exists():
            with open(mb_all_file, 'r') as f:
                all_count = sum(1 for line in f if line.strip())
            print(f"📊 Total working proxies: {all_count}")
            
            if all_count > 0:
                efficiency = (final_count / all_count) * 100
                print(f"⚡ Selection efficiency: {efficiency:.1f}% (quality filtered)")
    
    print(f"📁 All results saved to: {output_dir.absolute()}")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Pipeline failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)