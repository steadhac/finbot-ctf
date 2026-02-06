import re
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
        self.results: List[Dict] = []

        # Get credentials from environment
        creds_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google-credentials.json')
        sheets_id = os.getenv('GOOGLE_SHEETS_ID')

        if not sheets_id:
            raise ValueError("GOOGLE_SHEETS_ID not set in environment")

        # Authenticate with Google Sheets
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        credentials = Credentials.from_service_account_file(creds_file, scopes=scopes)
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

    def save_results(self):
        """Save all accumulated results to the worksheet."""
        if not self.results:
            return

        # ── KEY FIX: fetch column A once instead of N individual find() calls ──
        # This avoids gspread find() returning None on whitespace / format mismatches
        try:
            col_a_values = self.worksheet.col_values(1)  # all of column A
        except Exception as e:
            print(f"⚠ Could not read column A for '{self.worksheet_name}': {e}")
            col_a_values = []

        # Build a lookup: stripped test_code → 1-based row number
        # If duplicates exist, first match wins (header row is index 0 → row 1)
        code_to_row: Dict[str, int] = {}
        for idx, cell_value in enumerate(col_a_values):
            stripped = (cell_value or "").strip()
            if stripped and stripped not in code_to_row:
                code_to_row[stripped] = idx + 1  # gspread rows are 1-based

        for result in self.results:
            self._update_or_append_result(result, code_to_row)

        self.results = []

    def _update_or_append_result(self, result: list, code_to_row: Dict[str, int]):
        """Find test code in column A and update K, L, M. If not found, append."""
        test_code = result[0].strip()
        status = result[2]
        message = result[5]
        timestamp = datetime.now().isoformat()

        # ── Primary path: lookup from pre-fetched column A ──
        row = code_to_row.get(test_code)
        if row:
            try:
                self.worksheet.update(
                    f'K{row}:M{row}',
                    [[status, message, timestamp]]
                )
                print(f"  ✓ K{row}:M{row} ← {status} for '{test_code}'")
                return
            except Exception as e:
                print(f"  ⚠ Failed to update K{row}:M{row} for '{test_code}': {e}")

        # ── Fallback: gspread find() in case col_values missed it ──
        try:
            cell = self.worksheet.find(test_code, in_column=1)
            if cell:
                try:
                    self.worksheet.update(
                        f'K{cell.row}:M{cell.row}',
                        [[status, message, timestamp]]
                    )
                    print(f"  ✓ K{cell.row}:M{cell.row} ← {status} for '{test_code}' (via find)")
                    return
                except Exception as e:
                    print(f"  ⚠ Failed to update K{cell.row}:M{cell.row} for '{test_code}': {e}")
        except gspread.exceptions.CellNotFound:
            pass
        except Exception as e:
            print(f"  ⚠ find() error for '{test_code}': {e}")

        # ── Last resort: append as new row at bottom ──
        print(f"  ⚠ '{test_code}' not found in column A — appending new row")
        self.worksheet.append_row(result)

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
    """Extract test code from docstring (ISO-*, SSM-*, SAI-*, etc.)."""
    if not docstring:
        return None
    # Match patterns like: ISO-DAT-001, SSM-HMC-001, BAF-SSN-001, SAI-INV-001,
    # SAI-EDGE-001, SAI-GSI-001, etc.
    match = re.search(r'([A-Z][A-Z0-9]*-[A-Z0-9]+-\d+)', docstring)
    return match.group(1) if match else None


def detect_test_category(item) -> str:
    """Detect which Google Sheets worksheet a test belongs to based on file path."""
    fspath = str(item.fspath).lower()

    # List of tuples maintains order — check specific paths first
    # NOTE: 'specialized' must come before 'agents' so specialized agent tests
    #       route to their own tab instead of falling into Base Agent Framework
    path_worksheet_map = [
        ('specialized', 'Specialized Business Agents'),
        ('agents', 'Base Agent Framework'),
        ('vendor', 'Isolation Testing Framework TCs'),
        ('auth', 'Secure Session Management'),
        ('security', 'Security Penetration Testing'),
        ('performance', 'Performance Testing'),
        ('browser', 'Cross_Browser'),
        ('e2e', 'End-To-End'),
        ('integration', 'End-To-End'),
        ('ctf', 'CTF Challenge Validation'),
        ('summary', 'Summary')
    ]

    for keyword, worksheet in path_worksheet_map:
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
                'Base Agent Framework',
                'Specialized Business Agents',
                'End-To-End',
                'Summary',
            ]

            for worksheet_name in worksheets:
                try:
                    self.reporters[worksheet_name] = GoogleSheetsReporter(worksheet_name)
                    self.results_by_worksheet[worksheet_name] = []
                except Exception as e:
                    print(f"⚠ Could not initialize worksheet '{worksheet_name}': {e}")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        """Hook to capture test results and update Google Sheets."""
        outcome = yield
        report = outcome.get_result()

        # Only process the actual test call (not setup/teardown)
        if report.when == "call" and self.config.getoption("--google-sheets"):
            test_code = extract_iso_code(item.obj.__doc__)
            worksheet_name = detect_test_category(item)

            status = "PASSED" if report.passed else "FAILED"
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

    def pytest_sessionfinish(self, session, exitstatus):
        """Hook called after all tests complete."""
        if not self.config.getoption("--google-sheets"):
            return

        print("\n" + "=" * 80)
        print("Google Sheets Test Results Summary")
        print("=" * 80)

        # Calculate overall stats
        total_tests = 0
        passed_tests = 0

        # Save results to each worksheet (except Summary)
        worksheet_count = 0
        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                worksheet_count += 1
                passed_count = sum(1 for r in results if r['status'] == 'PASSED')
                total_count = len(results)
                passed_tests += passed_count
                total_tests += total_count

                # Save to worksheet
                if worksheet_name in self.reporters:
                    try:
                        for result in results:
                            self.reporters[worksheet_name].record_result(
                                result['code'],
                                result['name'],
                                result['status'],
                                result['duration'],
                                result['message']
                            )
                        self.reporters[worksheet_name].save_results()
                        print(f"✓ Saved {total_count} results to '{worksheet_name}' ({passed_count}/{total_count} passed)")
                    except Exception as e:
                        print(f"✗ ERROR saving to '{worksheet_name}': {e}")

        # Save Summary ONCE with all results at the end
        if "Summary" in self.results_by_worksheet and self.reporters.get("Summary"):
            try:
                self.reporters["Summary"].save_summary_results(self.results_by_worksheet["Summary"])
                summary_results = self.results_by_worksheet["Summary"]
                print(f"✓ Saved Summary ({len(summary_results)} total tests)")
            except Exception as e:
                print(f"✗ ERROR saving to Summary: {e}")

        # Calculate pass rate
        if total_tests > 0:
            pass_rate = (passed_tests / total_tests) * 100
            print(f"\nOverall: {passed_tests}/{total_tests} passed ({pass_rate:.1f}%)")

        print("\nWorksheet Breakdown:")
        print("=" * 80)
        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                passed = sum(1 for r in results if r['status'] == 'PASSED')
                print(f"  ✓ {worksheet_name}: {passed}/{len(results)} passed")

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