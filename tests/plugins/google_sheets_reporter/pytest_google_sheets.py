import re
import json
import gspread
from datetime import datetime
from typing import Optional, Dict, List
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import pytest

# Load environment variables at module level
load_dotenv()


class GoogleSheetsReporter:
    """Handles updating a specific Google Sheets worksheet with test results."""
    
    def __init__(self, worksheet_name: str):
        """Initialize connection to a specific worksheet."""
        self.worksheet_name = worksheet_name
        self.results: List[List[str]] = []
        
        # Get credentials from environment
        credentials_json = os.getenv('GOOGLE_CREDENTIALS')
        sheets_id = os.getenv('GOOGLE_SHEETS_ID')

        if not sheets_id:
            raise ValueError("GOOGLE_SHEETS_ID not set in environment")

        # Authenticate with Google Sheets
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        if credentials_json:
            # JSON string from environment (CI/CD)
            credentials = Credentials.from_service_account_info(json.loads(credentials_json), scopes=scopes)
        else:
            # Credentials file (local development)
            credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google-credentials.json')
            credentials = Credentials.from_service_account_file(credentials_file, scopes=scopes)
        self.client = gspread.authorize(credentials)
        self.sheet = self.client.open_by_key(sheets_id)
        
        # Get or create worksheet
        try:
            self.worksheet = self.sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            self.worksheet = self.sheet.add_worksheet(title=worksheet_name, rows=1000, cols=13)
            self._initialize_headers()
    
    def _initialize_headers(self):
        """Set up column headers if worksheet is new."""
        if self.worksheet_name == "Summary":
            headers = [
                'Timestamp',
                'Test Suite',
                'Total Tests',
                'Passed',
                'Failed',
                'Pass Rate',
                'Duration (s)',
                'Test Details',
                'Statuses'
            ]
        else:
            headers = [
                'Test Code',
                'Test Name',
                'Status',
                'Duration (s)',
                'Timestamp',
                'Message'
            ]
        self.worksheet.append_row(headers)
    
    def record_result(self, test_code: str, test_name: str, status: str, duration: float, message: str = ""):
        """Record a single test result."""
        row = [
            test_code,
            test_name,
            status,
            f"{duration:.2f}",
            datetime.now().isoformat(),
            message
        ]
        self.results.append(row)
    
    def _find_row(self, col_a: list, test_code: str, test_name: str) -> Optional[int]:
        """Return 1-indexed row number in col_a matching test_code or test_name, or None."""
        for query in [test_code, test_name]:
            if not query:
                continue
            for i, cell_value in enumerate(col_a):
                if cell_value and query.strip().lower() in str(cell_value).strip().lower():
                    return i + 1
        return None

    def save_results(self):
        """Save all accumulated results to the worksheet in a single batch.

        Reads column A once, matches every result to a row, then writes all
        K/L/M cells in one update_cells call — avoids rate-limiting from
        making two API calls per test result.
        """
        if not self.results:
            return

        col_a = self.worksheet.col_values(1)
        cells_to_update = []
        timestamp = datetime.now().isoformat()

        for result in self.results:
            test_code = result[0]
            test_name = result[1]
            status = result[2]
            message = result[5]

            row = self._find_row(col_a, test_code, test_name)
            if row is None:
                print(
                    f"  [sheets] no match for '{test_code}' / '{test_name}' "
                    f"in '{self.worksheet_name}' col A: {col_a[:10]}"
                )
                continue

            cells_to_update.extend([
                gspread.Cell(row, 11, status),
                gspread.Cell(row, 12, message),
                gspread.Cell(row, 13, timestamp),
            ])

        if cells_to_update:
            self.worksheet.update_cells(cells_to_update)

        self.results = []
    
    def save_summary_results(self, results_dicts: list):
        """Save summary with one row per test suite."""
        if not results_dicts:
            return
        
        # Group results by worksheet
        results_by_worksheet = {}
        for result in results_dicts:
            ws = result.get('worksheet', 'Unknown')
            if ws not in results_by_worksheet:
                results_by_worksheet[ws] = []
            results_by_worksheet[ws].append(result)
        
        # Create a summary row for each worksheet
        for worksheet_name, worksheet_results in results_by_worksheet.items():
            self._save_summary_row_for_worksheet(worksheet_name, worksheet_results)
    
    def _save_summary_row_for_worksheet(self, worksheet_name: str, results: list):
        """Create summary row for a specific worksheet."""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r['status'] == 'PASSED')
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        total_duration = sum(float(r['duration']) for r in results)
        
        test_names = "\n".join([
            f"{r['code']}: {r['name']} ({r['duration']:.2f}s)"
            for r in results
        ])
        
        statuses_str = "\n".join([r['status'] for r in results])
        
        # Create row for this worksheet
        summary_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_tests,
            passed_tests,
            failed_tests,
            f"{pass_rate:.1f}%",
            f"{total_duration:.2f}",
            worksheet_name,
            test_names,
            statuses_str
        ]
        self.worksheet.insert_row(summary_row, index=2)
    
    

def extract_iso_code(docstring: Optional[str]) -> Optional[str]:
    """Extract test code from docstring (ISO-*, SSM-*, etc.)."""
    if not docstring:
        return None
    # Match patterns like: ISO-DAT-001, SSM-HMC-001, LLM-OLLA-GSI-001, LLM-CTX-ERR-001, etc.
    match = re.search(r'([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)', docstring)
    return match.group(1) if match else None


def detect_test_category(item) -> str:
    """Detect which Google Sheets worksheet a test belongs to based on file path."""
    fspath = str(item.fspath).lower()

    # LLM-specific detection — checked first to avoid matching generic keywords
    if '/llm/' in fspath or '\\llm\\' in fspath:
        if 'test_llm_client' in fspath:
            return 'LLM Client'
        if 'test_mock_client' in fspath:
            return 'LLM Mock Client'
        if 'test_ollama_client' in fspath:
            return 'LLM Ollama Client'
        if 'test_openai_client' in fspath:
            return 'LLM OpenAI Client'
        if 'test_contextual_client' in fspath:
            return 'LLM Contextual Client'

    path_worksheet_map = {
        'vendor': 'Isolation Testing Framework TCs',
        'auth': 'Secure Session Management',
        'security': 'Security Penetration Testing',
        'ctf': 'CTF Challenge Validation',
        'performance': 'Performance Testing',
        'browser': 'Cross_Browser',
        'e2e': 'End-To-End',
        'integration': 'End-To-End',
        'summary': 'Summary'
    }

    for keyword, worksheet in path_worksheet_map.items():
        if keyword in fspath:
            return worksheet

    return 'Isolation Testing Framework TCs'


class GoogleSheetsPlugin:
    """Pytest plugin for automatic Google Sheets test result reporting."""
    
    def __init__(self, config):
        self.config = config
        self.reporters: Dict[str, GoogleSheetsReporter] = {}
        self.results_by_worksheet: Dict[str, List] = {}
        self.session_start_time = datetime.now()
        
        if config.getoption("--google-sheets"):
            # List of worksheets to initialize
            worksheets = [
                'Isolation Testing Framework TCs',
                'Secure Session Management',
                'Security Penetration Testing',
                'CTF Challenge Validation',
                'Performance Testing',
                'Cross_Browser',
                'End-To-End',
                'LLM Client',
                'LLM Mock Client',
                'LLM Ollama Client',
                'LLM OpenAI Client',
                'LLM Contextual Client',
                'Summary',
            ]
            
            for worksheet_name in worksheets:
                try:
                    self.reporters[worksheet_name] = GoogleSheetsReporter(worksheet_name)
                    self.results_by_worksheet[worksheet_name] = []
                except Exception as e:
                    print(f"⚠️  Could not initialize worksheet '{worksheet_name}': {e}")
    
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        """Hook to capture test results and update Google Sheets."""
        outcome = yield
        report = outcome.get_result()
        
        # Only process the actual test call (not setup/teardown)
        if report.when == "call" and self.config.getoption("--google-sheets"):
            test_code = extract_iso_code(item.obj.__doc__)
            worksheet_name = detect_test_category(item)
            
            if report.passed:
                status = "PASSED"
            elif report.skipped:
                status = "SKIPPED"
            else:
                status = "FAILED"
            duration = report.duration
            message = str(report.longrepr) if report.longrepr else ""
            
            result = {
                'code': test_code or item.name,
                'name': item.name,
                'status': status,
                'duration': duration,
                'message': message,
                'worksheet': worksheet_name
            }
            
            # Track result for the specific worksheet
            if worksheet_name in self.results_by_worksheet:
                self.results_by_worksheet[worksheet_name].append(result)
            
            # Also add to Summary
            if 'Summary' in self.results_by_worksheet:
                self.results_by_worksheet['Summary'].append(result)
    
    def _flush_worksheet(self, worksheet_name: str, results: list) -> tuple:
        """Record and save results for one worksheet. Returns (passed_count, total_count)."""
        total_count = len(results)
        passed_count = sum(1 for r in results if r['status'] == 'PASSED')
        if worksheet_name not in self.reporters:
            return passed_count, total_count
        try:
            for result in results:
                self.reporters[worksheet_name].record_result(
                    result['code'], result['name'], result['status'],
                    result['duration'], result['message']
                )
            self.reporters[worksheet_name].save_results()
            print(f"✓ Saved {total_count} results to '{worksheet_name}' ({passed_count}/{total_count} passed)")
        except Exception as e:
            print(f"✗ ERROR saving to '{worksheet_name}': {e}")
        return passed_count, total_count

    def _print_breakdown(self) -> None:
        """Print per-worksheet pass/fail counts."""
        print("\nWorksheet Breakdown:")
        print("=" * 80)
        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                passed = sum(1 for r in results if r['status'] == 'PASSED')
                print(f"✓ {worksheet_name}: {passed}/{len(results)} passed")

    def pytest_sessionfinish(self):
        """Hook called after all tests complete."""
        if not self.config.getoption("--google-sheets"):
            return

        print("\n" + "=" * 80)
        print("Google Sheets Test Results Summary")
        print("=" * 80)

        total_tests = 0
        passed_tests = 0
        worksheet_count = 0

        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                worksheet_count += 1
                passed_count, total_count = self._flush_worksheet(worksheet_name, results)
                passed_tests += passed_count
                total_tests += total_count

        if "Summary" in self.results_by_worksheet and self.reporters.get("Summary"):
            try:
                self.reporters["Summary"].save_summary_results(self.results_by_worksheet["Summary"])
                print(f"✓ Saved Summary ({len(self.results_by_worksheet['Summary'])} total tests)")
            except Exception as e:
                print(f"✗ ERROR saving to Summary: {e}")

        if total_tests > 0:
            pass_rate = (passed_tests / total_tests) * 100
            print(f"\nOverall: {passed_tests}/{total_tests} passed ({pass_rate:.1f}%)")

        self._print_breakdown()
        print(f"✓ Results saved to {worksheet_count} worksheet(s)")


# Module-level pytest hooks (NOT indented)
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--google-sheets",
        action="store_true",
        default=False,
        help="Enable automatic Google Sheets test result reporting"
    )


def pytest_configure(config):
    """Register the plugin."""
    config.addinivalue_line(
        "markers", "google_sheets: mark test to report to Google Sheets"
    )
    if config.getoption("--google-sheets"):
        plugin = GoogleSheetsPlugin(config)
        config.pluginmanager.register(plugin)