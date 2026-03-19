import argparse
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

def parse_arguments():
    parser = argparse.ArgumentParser(
        description = 'Run Verilator linting and capture output'
    )

    parser.add_argument(
        '--input', '-i',
        type=str
        required=True
        help=' Path to input Verilog file'
    )

    parser.add_argument(
        '--ouput-dir', '-o'
        type=str
        required = True
        help='Path to output directory for results'
    )

    parser.add_argument(
        "--flags",
        type=str
        default ='-Wall',
        help='Additional Verilator flags (default: -Wall)'
    )

    parser.add_argument(
        '--verbose', '-v'
        action ='store_true'
        help ='Print verbose output'
    )

    return parser.parse_args()

def validate_inputs(input_file, output_dir):
    ''' Validate input file and output directory 
    Returns (success: bool, error_message: str or None)'''

    # Check if input file exists
    if not input_file.exists():
        return False, f"Input file does not exist: {input_file}"
    
    if not input_file.is_file():
        return False, f"Input path is not a file: {input_file}"

    #Check file extension
    if input_file.suffix not in ['.v', '.verilog', '.vh', '.vlg', '.sv', '.svh']:
        return False, f"Input file must be Verilog (e.g. .v, .verilog, .vh, .vlg, .sv, .svh): {input_file}"
    
    #Create output directory if it does not exist
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Cannot create output directory: {e}"

    #Check if we can write to output directory
    if not output_dir.is_dir():
        return False, f"Output path is not a directory: {output_dir}"

    test_file = output_dir / '.write_test'
    try:
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        return False, f"Output directory is not writable: {e}"
    
    return True, None

def run_verilator(input_file, flags, verbose= False):
    # Build command
    command = ['verilator', '--lint-only']
    
    # Add flags
    flag_list = flags.split()
    command.extend(flag_list)
    
    # Add input file
    command.append(str(input_file))
    
    if verbose:
        print(f"Executing: {' '.join(command)}", file=sys.stderr)
    
    # Record start time
    start_time = datetime.now()
    
    # Execute command
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'execution_time': execution_time,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'command': ' '.join(command)
        }
    
    except subprocess.TimeoutExpired:
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': 'ERROR: Verilator execution timed out (300s limit)',
            'execution_time': execution_time,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'command': ' '.join(command),
            'timeout': True
        }
    
    except Exception as e:
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        return {
            'returncode': -1,
            'stdout': '',
            'stderr': f'ERROR: Failed to execute Verilator: {str(e)}',
            'execution_time': execution_time,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'command': ' '.join(command),
            'error': str(e)
        }

def write_results(input_file, output_dir, results, verbose=False):
    #returns True on success, False on failure

    log_file = output_dir / 'results.log'
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write("VERILATOR LINT RESULTS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Input File:      {input_file}\n")
            f.write(f"Start Time:      {results.get('start_time', 'N/A')}\n")
            f.write(f"End Time:        {results.get('end_time', 'N/A')}\n")
            f.write(f"Execution Time:  {results.get('execution_time', 0):.3f}s\n")
            f.write(f"Command:         {results.get('command', 'N/A')}\n")
            f.write(f"Exit Code:       {results['returncode']}\n")
            f.write("=" * 80 + "\n\n")
            
            # Write stdout
            if results['stdout']:
                f.write("STDOUT:\n")
                f.write("-" * 80 + "\n")
                f.write(results['stdout'])
                f.write("\n" + "-" * 80 + "\n\n")
            else:
                f.write("STDOUT: (empty)\n\n")
            
            # Write stderr
            if results['stderr']:
                f.write("STDERR:\n")
                f.write("-" * 80 + "\n")
                f.write(results['stderr'])
                f.write("\n" + "-" * 80 + "\n\n")
            else:
                f.write("STDERR: (empty)\n\n")
            
            # Write summary
            f.write("=" * 80 + "\n")
            if results['returncode'] == 0:
                f.write("RESULT: SUCCESS - No errors or warnings found\n")
            else:
                f.write("RESULT: FAILURE - Errors or warnings detected\n")
            f.write("=" * 80 + "\n")
        
        if verbose:
            print(f"Results written to: {log_file}", file=sys.stderr)
        
        return True
    
    except Exception as e:
        print(f"ERROR: Failed to write results: {e}", file=sys.stderr)
        return False

def write_json_results(input_file, output_dir, results, verbose=False):
    #returns True on success, False on failure
    json_file = output_dir / 'results.json'
    
    try:
        output_data = {
            'input_file': str(input_file),
            'exit_code': results['returncode'],
            'success': results['returncode'] == 0,
            'stdout': results['stdout'],
            'stderr': results['stderr'],
            'execution_time': results.get('execution_time', 0),
            'start_time': results.get('start_time'),
            'end_time': results.get('end_time'),
            'command': results.get('command'),
            'timeout': results.get('timeout', False),
            'error': results.get('error')
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)
        
        if verbose:
            print(f"JSON results written to: {json_file}", file=sys.stderr)
        
        return True
    
    except Exception as e:
        print(f"WARNING: Failed to write JSON results: {e}", file=sys.stderr)
        return False

def main():
    ''' Main entry point '''
# Parse arguments
    args = parse_arguments()
    
    # Convert to Path objects
    input_file = Path(args.input)
    output_dir = Path(args.output_dir)
    
    if args.verbose:
        print(f"Input file:   {input_file}", file=sys.stderr)
        print(f"Output dir:   {output_dir}", file=sys.stderr)
        print(f"Flags:        {args.flags}", file=sys.stderr)
    
    # Validate inputs
    valid, error_msg = validate_inputs(input_file, output_dir)
    if not valid:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print("Validation passed", file=sys.stderr)
    
    # Run Verilator
    results = run_verilator(input_file, args.flags, args.verbose)
    
    # Write results
    success = write_results(output_dir, input_file, results, args.verbose)
    if not success:
        print("ERROR: Failed to write results", file=sys.stderr)
        sys.exit(1)
    
    # Also write JSON results for machine parsing
    write_json_results(output_dir, input_file, results, args.verbose)
    
    # Print summary to stderr (so stdout is clean)
    if args.verbose:
        print("\n" + "=" * 80, file=sys.stderr)
        if results['returncode'] == 0:
            print("✓ SUCCESS: Linting completed without errors", file=sys.stderr)
        else:
            print("✗ FAILURE: Linting found errors or warnings", file=sys.stderr)
        print(f"Execution time: {results.get('execution_time', 0):.3f}s", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
    
    # Exit with appropriate code
    # 0 = success (no errors/warnings)
    # 1 = failure (errors or warnings found)
    sys.exit(0 if results['returncode'] == 0 else 1)


if __name__ == '__main__':
    main()